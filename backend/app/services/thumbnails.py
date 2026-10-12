"""ThumbnailGenerator: poster frames, contact sheets and audio waveforms."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps

from .ffmpeg import run_ffmpeg_simple


class ThumbnailGenerator:
    def __init__(self, width: int = 480):
        self.width = width

    def video_thumb(self, src: Path, dst: Path, duration: float) -> Path:
        t = max(0.0, min(duration * 0.2, duration - 0.1))
        run_ffmpeg_simple(["-ss", f"{t:.3f}", "-i", src, "-frames:v", "1",
                           "-vf", f"scale={self.width}:-2", "-q:v", "4", dst])
        return dst

    def frame_at(self, src: Path, dst: Path, t: float, vf: str | None = None, width: int = 960) -> Path:
        chain = f"scale={width}:-2" + (f",{vf}" if vf else "")
        run_ffmpeg_simple(["-ss", f"{max(0.0, t):.3f}", "-i", src, "-frames:v", "1", "-vf", chain, "-q:v", "3", dst])
        return dst

    def contact_sheet(self, src: Path, dst: Path, duration: float, cols: int = 4, rows: int = 3) -> Path:
        n = cols * rows
        step = max(duration / n, 0.04)
        vf = f"fps=1/{step:.4f},scale=320:-2,tile={cols}x{rows}:padding=4:margin=4:color=0x0b0b12"
        run_ffmpeg_simple(["-i", src, "-vf", vf, "-frames:v", "1", "-q:v", "4", dst])
        return dst

    def waveform(self, src: Path, dst: Path) -> Path:
        run_ffmpeg_simple(["-i", src, "-filter_complex",
                           "aformat=channel_layouts=mono,showwavespic=s=640x120:colors=0x22d3ee",
                           "-frames:v", "1", dst])
        return dst

    def image_thumb(self, src: Path, dst: Path) -> Path:
        with Image.open(src) as im:
            im = ImageOps.exif_transpose(im)
            im.thumbnail((self.width, self.width))
            if dst.suffix.lower() in (".jpg", ".jpeg"):
                bg = Image.new("RGB", im.size, (11, 11, 18))
                rgba = im.convert("RGBA")
                bg.paste(rgba, mask=rgba.split()[-1])
                bg.save(dst, quality=85)
            else:
                im.save(dst)
        return dst
