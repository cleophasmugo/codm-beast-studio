"""ExportManager: output geometry and encoder settings for each export format."""

from __future__ import annotations

from dataclasses import dataclass

from ..schemas import ProjectSettings
from .ffmpeg import available_encoders

SHORT_SIDE = {"720p": 720, "1080p": 1080, "1440p": 1440, "2160p": 2160}
ASPECT = {"16:9": (16, 9), "9:16": (9, 16), "1:1": (1, 1), "4:5": (4, 5)}
EXT = {"mp4_h264": "mp4", "mp4_h265": "mp4", "webm_vp9": "webm"}


def even(x: float) -> int:
    return max(2, int(round(x / 2)) * 2)


@dataclass
class OutputSpec:
    width: int
    height: int
    fps: int
    format: str
    ext: str
    video_args: list[str]
    audio_args: list[str]
    intermediate_crf: int


class ExportManager:
    def supported_formats(self) -> dict[str, bool]:
        enc = available_encoders()
        return {
            "mp4_h264": "libx264" in enc,
            "mp4_h265": "libx265" in enc,
            "webm_vp9": "libvpx-vp9" in enc and "libopus" in enc,
        }

    def geometry(self, s: ProjectSettings, source_wh: tuple[int, int] | None, preview: bool) -> tuple[int, int]:
        aw, ah = ASPECT[s.aspect]
        if preview:
            short = 540
        elif s.resolution == "source":
            short = min(source_wh) if source_wh else 1080
            short = min(max(short, 360), 2160)
        else:
            short = SHORT_SIDE[s.resolution]
        if aw >= ah:
            return even(short * aw / ah), even(short)
        return even(short), even(short * ah / aw)

    def spec(self, s: ProjectSettings, source_wh: tuple[int, int] | None, source_fps: float | None,
             preview: bool = False, x264_preset: str = "veryfast") -> OutputSpec:
        w, h = self.geometry(s, source_wh, preview)
        fps = s.fps or int(round(min(max(source_fps or 30, 24), 60)))
        if preview:
            fps = min(fps, 30)
        fmt = "mp4_h264" if preview else s.format
        if not self.supported_formats().get(fmt, False):
            fmt = "mp4_h264"
        q = "draft" if preview else s.quality
        gop = str(fps * 2)
        if fmt == "mp4_h264":
            crf = {"draft": 26, "standard": 20, "high": 17}[q]
            preset = "ultrafast" if preview else x264_preset
            v = ["-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p",
                 "-profile:v", "high", "-g", gop, "-movflags", "+faststart"]
            a = ["-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
        elif fmt == "mp4_h265":
            crf = {"draft": 30, "standard": 24, "high": 21}[q]
            v = ["-c:v", "libx265", "-preset", "fast", "-crf", str(crf), "-pix_fmt", "yuv420p", "-tag:v", "hvc1",
                 "-g", gop, "-x265-params", "log-level=error", "-movflags", "+faststart"]
            a = ["-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
        else:
            crf = {"draft": 40, "standard": 33, "high": 28}[q]
            v = ["-c:v", "libvpx-vp9", "-crf", str(crf), "-b:v", "0", "-row-mt", "1", "-deadline", "good",
                 "-cpu-used", "6" if q == "draft" else "4", "-pix_fmt", "yuv420p", "-g", gop]
            a = ["-c:a", "libopus", "-b:a", "160k", "-ar", "48000"]
        inter_crf = {"draft": 23, "standard": 17, "high": 14}[q]
        return OutputSpec(w, h, fps, fmt, EXT[fmt], v, a, inter_crf)
