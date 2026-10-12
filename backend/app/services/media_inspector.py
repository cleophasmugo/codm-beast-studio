"""MediaInspector: identify uploads and read their technical metadata."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

from .ffmpeg import FFmpegError, ffprobe_json

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".flv", ".ts", ".3gp", ".wmv", ".mpg", ".mpeg"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".opus", ".flac", ".wma"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
ALLOWED_EXT = VIDEO_EXT | AUDIO_EXT | IMAGE_EXT

MIME = {
    ".mp4": "video/mp4", ".m4v": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm",
    ".mkv": "video/x-matroska", ".avi": "video/x-msvideo", ".mp3": "audio/mpeg", ".wav": "audio/wav",
    ".m4a": "audio/mp4", ".aac": "audio/aac", ".ogg": "audio/ogg", ".opus": "audio/ogg", ".flac": "audio/flac",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
    ".gif": "image/gif", ".bmp": "image/bmp", ".tif": "image/tiff", ".tiff": "image/tiff",
}


class InspectionError(ValueError):
    pass


@dataclass
class Inspection:
    kind: str  # video | audio | image | sticker
    mime: str
    info: dict[str, Any]


def _fps(rate: str | None) -> float:
    try:
        num, den = (rate or "0/1").split("/")
        return round(float(num) / float(den), 3) if float(den) else 0.0
    except (ValueError, ZeroDivisionError):
        return 0.0


class MediaInspector:
    def inspect(self, path: Path, original_name: str = "") -> Inspection:
        ext = Path(original_name or path.name).suffix.lower()
        if ext not in ALLOWED_EXT:
            raise InspectionError(f"Unsupported file type '{ext or '?'}'")
        if ext in IMAGE_EXT:
            return self._image(path, ext)
        return self._av(path, ext)

    def _image(self, path: Path, ext: str) -> Inspection:
        try:
            with Image.open(path) as im:
                im.verify()
            with Image.open(path) as im:
                w, h = im.size
                mode = im.mode
                frames = getattr(im, "n_frames", 1)
                has_alpha = mode in ("RGBA", "LA", "PA") or (mode == "P" and "transparency" in im.info)
        except (UnidentifiedImageError, OSError, SyntaxError) as e:
            raise InspectionError("This file is not a readable image") from e
        animated = frames > 1
        # Transparent PNGs and animated GIFs are treated as stickers/overlays.
        kind = "sticker" if (has_alpha or animated) else "image"
        return Inspection(kind, MIME.get(ext, "image/png"), {
            "width": w, "height": h, "mode": mode, "has_alpha": has_alpha,
            "animated": animated, "frames": frames, "megapixels": round(w * h / 1e6, 2),
        })

    def _av(self, path: Path, ext: str) -> Inspection:
        try:
            data = ffprobe_json(path)
        except FFmpegError as e:
            raise InspectionError(f"FFmpeg can't read this file: {e}") from e
        streams = data.get("streams", [])
        fmt = data.get("format", {})
        v = next((s for s in streams if s.get("codec_type") == "video"
                  and not s.get("disposition", {}).get("attached_pic")), None)
        a = next((s for s in streams if s.get("codec_type") == "audio"), None)
        duration = float(fmt.get("duration") or (v or a or {}).get("duration") or 0)
        info: dict[str, Any] = {
            "duration": round(duration, 3),
            "container": fmt.get("format_name", ""),
            "bitrate": int(fmt.get("bit_rate") or 0),
            "has_audio": a is not None,
            "has_video": v is not None,
        }
        if a:
            info.update({
                "audio_codec": a.get("codec_name", ""),
                "sample_rate": int(a.get("sample_rate") or 0),
                "channels": int(a.get("channels") or 0),
            })
        if v:
            w, h = int(v.get("width") or 0), int(v.get("height") or 0)
            rotation = 0
            for sd in v.get("side_data_list", []) or []:
                if "rotation" in sd:
                    rotation = int(sd["rotation"])
            if abs(rotation) in (90, 270):
                w, h = h, w
            info.update({
                "width": w, "height": h, "rotation": rotation,
                "fps": _fps(v.get("avg_frame_rate")) or _fps(v.get("r_frame_rate")),
                "video_codec": v.get("codec_name", ""),
                "pix_fmt": v.get("pix_fmt", ""),
            })
            if duration <= 0:
                raise InspectionError("Video has no measurable duration")
            return Inspection("video", MIME.get(ext, "video/mp4"), info)
        if a:
            if duration <= 0:
                raise InspectionError("Audio has no measurable duration")
            return Inspection("audio", MIME.get(ext, "audio/mpeg"), info)
        raise InspectionError("No audio or video streams found")
