"""Frame sampling (FFmpeg decode + OpenCV measurements) and the SceneDetector.

FFmpeg decodes and downsizes frames (it handles every codec and rotation); OpenCV
computes the measurements on each small frame.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from .ffmpeg import Cancelled, FFmpegError, ffmpeg_bin

SAMPLE_WIDTH = 192


@dataclass
class FrameSamples:
    """Per-sample measurements, one entry per analysed frame."""

    fps: float
    times: np.ndarray = field(default_factory=lambda: np.zeros(0))
    motion: np.ndarray = field(default_factory=lambda: np.zeros(0))  # mean abs frame difference 0..1
    flow: np.ndarray = field(default_factory=lambda: np.zeros(0))  # mean optical-flow magnitude (px)
    centroid_x: np.ndarray = field(default_factory=lambda: np.zeros(0))  # horizontal centre of motion 0..1
    brightness: np.ndarray = field(default_factory=lambda: np.zeros(0))  # mean luma 0..1
    contrast: np.ndarray = field(default_factory=lambda: np.zeros(0))  # luma std 0..1
    saturation: np.ndarray = field(default_factory=lambda: np.zeros(0))  # mean HSV saturation 0..1
    sharpness: np.ndarray = field(default_factory=lambda: np.zeros(0))  # variance of Laplacian
    noise: np.ndarray = field(default_factory=lambda: np.zeros(0))  # high-pass residual estimate
    clip_low: np.ndarray = field(default_factory=lambda: np.zeros(0))  # fraction of crushed blacks
    clip_high: np.ndarray = field(default_factory=lambda: np.zeros(0))  # fraction of blown whites
    hist_diff: np.ndarray = field(default_factory=lambda: np.zeros(0))  # Bhattacharyya distance to previous

    def __len__(self) -> int:
        return len(self.times)


def sample_frames(path: Path, duration: float, width: int, height: int, fps: float = 6.0,
                  on_progress: Callable[[float], None] | None = None,
                  should_cancel: Callable[[], bool] | None = None) -> FrameSamples:
    sw = SAMPLE_WIDTH
    sh = max(2, int(round(sw * (height or 9) / max(width or 16, 1) / 2)) * 2)
    cmd = [ffmpeg_bin(), "-hide_banner", "-nostdin", "-loglevel", "error", "-i", str(path), "-an",
           "-vf", f"fps={fps},scale={sw}:{sh}:flags=area", "-f", "rawvideo", "-pix_fmt", "bgr24", "pipe:1"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    frame_bytes = sw * sh * 3
    rows: dict[str, list[float]] = {k: [] for k in (
        "motion", "flow", "centroid_x", "brightness", "contrast", "saturation", "sharpness", "noise",
        "clip_low", "clip_high", "hist_diff")}
    prev_gray = None
    prev_hist = None
    xs = np.linspace(0, 1, sw, dtype=np.float32)
    i = 0
    assert proc.stdout is not None
    try:
        while True:
            buf = proc.stdout.read(frame_bytes)
            if not buf or len(buf) < frame_bytes:
                break
            frame = np.frombuffer(buf, np.uint8).reshape(sh, sw, 3)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            g = gray.astype(np.float32) / 255.0
            rows["brightness"].append(float(g.mean()))
            rows["contrast"].append(float(g.std()))
            rows["saturation"].append(float(hsv[..., 1].mean() / 255.0))
            rows["clip_low"].append(float((gray < 8).mean()))
            rows["clip_high"].append(float((gray > 247).mean()))
            rows["sharpness"].append(float(cv2.Laplacian(gray, cv2.CV_32F).var()))
            blur = cv2.GaussianBlur(g, (3, 3), 0)
            rows["noise"].append(float(np.median(np.abs(g - blur))))
            hist = cv2.calcHist([hsv], [0, 1, 2], None, [16, 8, 8], [0, 180, 0, 256, 0, 256])
            cv2.normalize(hist, hist)
            if prev_gray is None:
                rows["motion"].append(0.0)
                rows["flow"].append(0.0)
                rows["centroid_x"].append(0.5)
                rows["hist_diff"].append(0.0)
            else:
                diff = cv2.absdiff(gray, prev_gray).astype(np.float32) / 255.0
                rows["motion"].append(float(diff.mean()))
                col = diff.sum(axis=0)
                tot = float(col.sum())
                rows["centroid_x"].append(float((col * xs).sum() / tot) if tot > 1e-6 else 0.5)
                flow = cv2.calcOpticalFlowFarneback(prev_gray, gray, None, 0.5, 2, 9, 2, 5, 1.1, 0)
                rows["flow"].append(float(np.linalg.norm(flow, axis=2).mean()))
                rows["hist_diff"].append(float(cv2.compareHist(prev_hist, hist, cv2.HISTCMP_BHATTACHARYYA)))
            prev_gray, prev_hist = gray, hist
            i += 1
            if i % 30 == 0:
                if on_progress and duration > 0:
                    on_progress(min(1.0, i / fps / duration))
                if should_cancel and should_cancel():
                    raise Cancelled("Job cancelled")
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait()
    if i == 0:
        err = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
        raise FFmpegError(f"Could not decode any video frames. {err.strip()[:300]}")
    out = FrameSamples(fps=fps, times=np.arange(i, dtype=np.float64) / fps)
    for k, v in rows.items():
        setattr(out, k, np.asarray(v, dtype=np.float64))
    return out


@dataclass
class Scene:
    start: float
    end: float


class SceneDetector:
    """Finds hard cuts / big visual changes from colour-histogram distance between samples."""

    def __init__(self, min_threshold: float = 0.35, sensitivity: float = 3.0, min_gap: float = 0.6):
        self.min_threshold = min_threshold
        self.sensitivity = sensitivity
        self.min_gap = min_gap

    def cut_times(self, s: FrameSamples) -> list[float]:
        d = s.hist_diff
        if len(d) < 3:
            return []
        thr = max(self.min_threshold, float(np.median(d) + self.sensitivity * (np.std(d) + 1e-6)))
        cuts: list[float] = []
        for idx in np.where(d > thr)[0]:
            t = float(s.times[idx])
            if not cuts or t - cuts[-1] >= self.min_gap:
                cuts.append(round(t, 3))
        return cuts

    def scenes(self, s: FrameSamples, duration: float) -> list[Scene]:
        bounds = [0.0, *self.cut_times(s), duration]
        return [Scene(a, b) for a, b in zip(bounds, bounds[1:]) if b - a > 0.05]
