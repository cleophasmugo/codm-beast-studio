"""Pillow-rendered graphics: text overlays, title/outro cards, light leaks and built-in stickers.

Text is rasterised here (not with FFmpeg drawtext) so user text never enters a filter string,
and so rotation, outlines and shadows work the same in video and in Image Studio.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from ..core.config import find_font


def hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = find_font()
    if path:
        return ImageFont.truetype(path, max(8, size))
    return ImageFont.load_default(size=max(8, size))


def text_image(text: str, size: int, color: str = "#FFFFFF", outline: str = "#000000",
               shadow: bool = True, rotation: float = 0.0, opacity: float = 1.0,
               badge: str | None = None) -> Image.Image:
    """Render text (multi-line ok) to a tight transparent RGBA image."""
    fnt = font(size)
    stroke = max(1, size // 14)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    left, t, r, b = probe.multiline_textbbox((0, 0), text, font=fnt, stroke_width=stroke, align="center")
    pad = stroke * 2 + (size // 3 if badge else size // 8) + (size // 10 if shadow else 0)
    w, h = (r - left) + pad * 2, (b - t) + pad * 2
    img = Image.new("RGBA", (max(1, w), max(1, h)), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if badge:
        d.rounded_rectangle((0, 0, w - 1, h - 1), radius=size // 3, fill=(*hex_rgb(badge), 215))
    origin = (pad - left, pad - t)
    if shadow:
        sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).multiline_text((origin[0] + size // 18, origin[1] + size // 14), text, font=fnt,
                                          fill=(0, 0, 0, 170), align="center")
        img = Image.alpha_composite(img, sh.filter(ImageFilter.GaussianBlur(max(1, size // 16))))
        d = ImageDraw.Draw(img)
    d.multiline_text(origin, text, font=fnt, fill=(*hex_rgb(color), 255), stroke_width=stroke,
                     stroke_fill=(*hex_rgb(outline), 255), align="center")
    if rotation:
        img = img.rotate(rotation, resample=Image.BICUBIC, expand=True)
    if opacity < 1:
        a = img.getchannel("A").point(lambda v: int(v * opacity))
        img.putalpha(a)
    return img


def scaled_overlay(src: Path, target_w: int, rotation: float = 0.0, opacity: float = 1.0) -> Image.Image:
    with Image.open(src) as im:
        im = im.convert("RGBA")
        ratio = target_w / max(1, im.width)
        im = im.resize((max(1, int(im.width * ratio)), max(1, int(im.height * ratio))), Image.LANCZOS)
    if rotation:
        im = im.rotate(rotation, resample=Image.BICUBIC, expand=True)
    if opacity < 1:
        im.putalpha(im.getchannel("A").point(lambda v: int(v * opacity)))
    return im


def card_image(w: int, h: int, title: str, subtitle: str = "") -> Image.Image:
    """Dark gradient title/outro card with neon accents."""
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    cx, cy = w * 0.5, h * 0.45
    r = np.sqrt(((x - cx) / w) ** 2 + ((y - cy) / h) ** 2)
    base = np.clip(1 - r * 1.6, 0, 1)[..., None]
    c1 = np.array([124, 58, 237], np.float32)  # violet
    c2 = np.array([6, 182, 212], np.float32)  # cyan
    mix = (x / w)[..., None]
    col = (c1 * (1 - mix) + c2 * mix) * base * 0.55 + np.array([7, 7, 12], np.float32)
    img = Image.fromarray(np.clip(col, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    short = min(w, h)
    t = text_image(title, int(short * 0.11), "#FFFFFF", "#0B0B12")
    img.alpha_composite(t, ((w - t.width) // 2, int(h * 0.45 - t.height / 2)))
    if subtitle:
        s = text_image(subtitle, int(short * 0.05), "#22D3EE", "#0B0B12", shadow=False)
        img.alpha_composite(s, ((w - s.width) // 2, int(h * 0.45 + t.height / 2 + short * 0.02)))
    d = ImageDraw.Draw(img)
    lw = max(2, short // 180)
    d.line((w * 0.3, h * 0.45 + t.height / 2 + short * 0.01, w * 0.7, h * 0.45 + t.height / 2 + short * 0.01),
           fill=(163, 230, 53, 255), width=lw)
    return img.convert("RGB")


def light_leak(path: Path, w: int = 960, h: int = 540) -> Path:
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    blob1 = np.exp(-(((x - w * 0.15) / (w * 0.35)) ** 2 + ((y - h * 0.2) / (h * 0.5)) ** 2))
    blob2 = np.exp(-(((x - w * 0.95) / (w * 0.25)) ** 2 + ((y - h * 0.9) / (h * 0.45)) ** 2))
    rgb = np.zeros((h, w, 3), np.float32)
    rgb += blob1[..., None] * np.array([255, 140, 40])
    rgb += blob2[..., None] * np.array([200, 60, 255])
    alpha = np.clip((blob1 + blob2) * 0.85, 0, 1) * 255
    img = np.dstack([np.clip(rgb, 0, 255), alpha]).astype(np.uint8)
    Image.fromarray(img, "RGBA").save(path)
    return path


# --------------------------------------------------------------------------- built-in stickers
def _canvas(size: int = 512) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def _glow(img: Image.Image, color: tuple[int, int, int], radius: int = 14) -> Image.Image:
    a = img.getchannel("A").filter(ImageFilter.GaussianBlur(radius))
    g = Image.new("RGBA", img.size, (*color, 0))
    g.putalpha(a.point(lambda v: int(v * 0.9)))
    return Image.alpha_composite(g, img)


def _crosshair() -> Image.Image:
    img, d = _canvas()
    c, col = 256, (34, 211, 238, 255)
    d.ellipse((96, 96, 416, 416), outline=col, width=18)
    for a, b in (((256, 40), (256, 190)), ((256, 322), (256, 472)), ((40, 256), (190, 256)), ((322, 256), (472, 256))):
        d.line((a, b), fill=col, width=18)
    d.ellipse((c - 14, c - 14, c + 14, c + 14), fill=(163, 230, 53, 255))
    return _glow(img, (34, 211, 238))


def _bolt() -> Image.Image:
    img, d = _canvas()
    d.polygon([(290, 30), (110, 290), (240, 290), (200, 482), (400, 200), (270, 200), (330, 30)],
              fill=(250, 204, 21, 255), outline=(255, 255, 255, 255))
    return _glow(img, (250, 204, 21))


def _flame() -> Image.Image:
    img, d = _canvas()
    pts = [(256 + 170 * math.sin(t) * (1 - t / (2 * math.pi)) ** 0.6,
            470 - 400 * (t / (2 * math.pi))) for t in np.linspace(0, 2 * math.pi, 60)]
    d.polygon([(256, 480), *[(x, y) for x, y in pts if x >= 256], (256, 60)], fill=(249, 115, 22, 255))
    d.polygon([(256, 480), *[(512 - x, y) for x, y in pts if x >= 256], (256, 60)], fill=(249, 115, 22, 255))
    d.ellipse((176, 280, 336, 470), fill=(250, 204, 21, 255))
    return _glow(img, (249, 115, 22))


def _star() -> Image.Image:
    img, d = _canvas()
    pts = []
    for i in range(10):
        r = 230 if i % 2 == 0 else 95
        a = -math.pi / 2 + i * math.pi / 5
        pts.append((256 + r * math.cos(a), 256 + r * math.sin(a)))
    d.polygon(pts, fill=(168, 85, 247, 255), outline=(255, 255, 255, 255))
    return _glow(img, (168, 85, 247))


def _badge(text: str, color: str) -> Image.Image:
    t = text_image(text, 120, "#FFFFFF", "#0B0B12", shadow=False, badge=color)
    return _glow(t, hex_rgb(color), 10)


BUILTIN_STICKERS = {
    "Crosshair": _crosshair,
    "Lightning": _bolt,
    "Flame": _flame,
    "Star": _star,
    "GG badge": lambda: _badge("GG", "#7C3AED"),
    "Clutch badge": lambda: _badge("CLUTCH", "#0891B2"),
    "Beast Mode badge": lambda: _badge("BEAST MODE", "#16A34A"),
    "Subscribe badge": lambda: _badge("SUBSCRIBE", "#DC2626"),
}
