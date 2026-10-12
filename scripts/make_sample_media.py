#!/usr/bin/env python3
"""Generate safe, synthetic test media that behaves like CODM gameplay for the analysers.

Output (in the target directory, default ./samples):
  sample_gameplay.mp4   40 s, 1280x720 @30 fps. Calm walking sections plus three action
                        bursts (fast camera moves, muzzle flashes, gunfire-like audio) at
                        about 7-11 s, 19-23 s and 31-35 s.
  sample_screenshot.jpg A dim, flat 1920x1080 "screenshot" for the Auto Enhance test.
  sample_sticker.png    Transparent PNG overlay.

Nothing here is copied from the game; it is all drawn with numpy.

Usage: python scripts/make_sample_media.py [out_dir] [--seconds 40] [--fps 30]
"""

from __future__ import annotations

import argparse
import subprocess
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

W, H = 1280, 720
BURSTS = [(7.0, 11.0), (19.0, 23.0), (31.0, 35.0)]
SR = 48000


def in_burst(t: float) -> bool:
    return any(a <= t < b for a, b in BURSTS)


def world(width: int, height: int, rng: np.random.Generator) -> np.ndarray:
    """A wide 'map' texture the camera pans across."""
    y, x = np.mgrid[0:height, 0:width].astype(np.float32)
    sky = np.clip(1 - y / (height * 0.45), 0, 1)[..., None] * np.array([90, 120, 150], np.float32)
    ground = np.clip((y - height * 0.45) / (height * 0.55), 0, 1)[..., None] * np.array([70, 80, 55], np.float32)
    img = sky + ground + 30
    # buildings / cover blocks
    for _ in range(60):
        bx, bw = rng.integers(0, width - 200), rng.integers(60, 220)
        by, bh = rng.integers(int(height * 0.25), int(height * 0.6)), rng.integers(80, 300)
        shade = rng.integers(40, 110)
        img[by:by + bh, bx:bx + bw] = np.array([shade, shade * 0.95, shade * 0.85])
        img[by:by + 6, bx:bx + bw] += 25
    img += rng.normal(0, 4, img.shape).astype(np.float32)
    return np.clip(img, 0, 255).astype(np.uint8)


def hud(frame: Image.Image, t: float, kills: int) -> None:
    d = ImageDraw.Draw(frame)
    d.rectangle((20, 20, 200, 160), outline=(220, 220, 220), width=3)  # minimap
    d.ellipse((104, 84, 116, 96), fill=(80, 200, 255))
    d.rectangle((W - 230, H - 90, W - 30, H - 40), fill=(0, 0, 0))
    d.text((W - 215, H - 80), f"AMMO 30/120   {kills}", fill=(255, 255, 255))
    cx, cy = W // 2, H // 2  # crosshair
    for dx, dy in ((-18, 0), (18, 0), (0, -18), (0, 18)):
        d.line((cx + dx * 0.4, cy + dy * 0.4, cx + dx, cy + dy), fill=(255, 255, 255), width=2)


def make_video(out: Path, seconds: float, fps: int) -> None:
    rng = np.random.default_rng(42)
    big = world(W * 3, H, rng)
    n = int(seconds * fps)
    audio_path = out.with_suffix(".wav")
    make_audio(audio_path, seconds)
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(fps), "-i", "pipe:0", "-i", str(audio_path),
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    camx = float(W)
    vel = 0.0
    kills = 0
    enemies = [[rng.uniform(0.2, 0.8) * W, rng.uniform(0.4, 0.6) * H, rng.uniform(-6, 6)] for _ in range(3)]
    assert proc.stdin is not None
    for i in range(n):
        t = i / fps
        action = in_burst(t)
        if action:
            vel = 0.8 * vel + rng.normal(0, 28)
        else:
            vel = 0.9 * vel + 0.6  # slow steady walk
        camx = float(np.clip(camx + vel, 0, W * 2 - 1))
        x0 = int(camx)
        frame = big[:, x0:x0 + W].copy()
        if action:
            shake = rng.integers(-8, 9, size=2)
            frame = np.roll(frame, tuple(shake), axis=(0, 1))
        img = Image.fromarray(frame)
        d = ImageDraw.Draw(img)
        if action:
            for e in enemies:
                e[0] = (e[0] + e[2] * 3) % W
                d.rectangle((e[0] - 20, e[1] - 60, e[0] + 20, e[1] + 60), fill=(150, 40, 40))
            if (i % 3) == 0:  # muzzle flash
                d.ellipse((W * 0.62 - 60, H * 0.72 - 60, W * 0.62 + 60, H * 0.72 + 60), fill=(255, 240, 180))
            if i % int(fps * 1.3) == 0:
                kills += 1
        hud(img, t, kills)
        proc.stdin.write(np.asarray(img, np.uint8).tobytes())
    proc.stdin.close()
    proc.wait()
    audio_path.unlink(missing_ok=True)
    if proc.returncode:
        raise SystemExit("ffmpeg failed to encode the sample video")


def make_audio(path: Path, seconds: float) -> None:
    rng = np.random.default_rng(7)
    n = int(seconds * SR)
    y = rng.normal(0, 0.01, n)  # ambience
    steps = np.arange(0, seconds, 0.55)
    for s in steps:  # footsteps
        i = int(s * SR)
        k = np.arange(min(1500, n - i))
        y[i:i + len(k)] += 0.05 * np.sin(2 * np.pi * 90 * k / SR) * np.exp(-k / 300)
    for a, b in BURSTS:  # gunfire: rapid sharp broadband transients
        t = a
        while t < b:
            i = int(t * SR)
            k = np.arange(min(4000, n - i))
            shot = rng.normal(0, 1, len(k)) * np.exp(-k / 500) * 0.8
            shot += 0.5 * np.sin(2 * np.pi * 60 * k / SR) * np.exp(-k / 1500)
            y[i:i + len(k)] += shot
            t += rng.uniform(0.08, 0.16) if rng.random() > 0.15 else 0.6
    y = np.clip(y / max(1e-9, np.abs(y).max()) * 0.9, -1, 1)
    pcm = (np.stack([y, y], 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def make_screenshot(path: Path) -> None:
    rng = np.random.default_rng(5)
    img = Image.fromarray(world(1920, 1080, rng))
    d = ImageDraw.Draw(img)
    d.rectangle((900, 450, 960, 640), fill=(150, 40, 40))
    # make it dim and flat, like a dark in-game capture
    arr = np.asarray(img).astype(np.float32)
    arr = 40 + (arr - arr.mean()) * 0.55 + arr.mean() * 0.35
    Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).save(path, quality=90)


def make_sticker(path: Path) -> None:
    img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((16, 16, 240, 240), outline=(163, 230, 53, 255), width=14)
    d.line((128, 30, 128, 226), fill=(163, 230, 53, 255), width=10)
    d.line((30, 128, 226, 128), fill=(163, 230, 53, 255), width=10)
    img.save(path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir", nargs="?", default="samples")
    ap.add_argument("--seconds", type=float, default=40.0)
    ap.add_argument("--fps", type=int, default=30)
    a = ap.parse_args()
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    make_video(out / "sample_gameplay.mp4", a.seconds, a.fps)
    make_screenshot(out / "sample_screenshot.jpg")
    make_sticker(out / "sample_sticker.png")
    print(f"Wrote samples to {out.resolve()}")


if __name__ == "__main__":
    main()
