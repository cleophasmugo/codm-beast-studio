"""Image Studio: screenshot enhancement, layout and layers (Pillow)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

from ..schemas import ImageEdit
from . import graphics

ASPECTS = {"16:9": 16 / 9, "9:16": 9 / 16, "1:1": 1.0, "4:5": 0.8, "4:3": 4 / 3}

# look -> (r, g, b multipliers for shadows-ish tint, saturation, contrast)
IMAGE_LOOKS = {
    "none": ((1, 1, 1), 1.0, 1.0),
    "beast": ((1.04, 0.99, 0.95), 1.15, 1.1),
    "cinematic": ((1.03, 1.0, 0.97), 0.9, 1.06),
    "esports": ((1.0, 1.0, 1.03), 1.18, 1.06),
    "clean": ((1, 1, 1), 1.05, 1.03),
    "neon": ((1.05, 0.92, 1.12), 1.3, 1.1),
    "warm": ((1.07, 1.0, 0.92), 1.05, 1.02),
    "cold": ((0.94, 1.0, 1.08), 1.0, 1.02),
    "vintage": ((1.06, 1.02, 0.88), 0.8, 0.95),
    "bw": ((1, 1, 1), 0.0, 1.1),
}


def analyze_image(im: Image.Image) -> dict:
    a = np.asarray(im.convert("RGB").resize((256, max(1, int(256 * im.height / im.width)))), np.float32) / 255
    lum = a @ np.array([0.299, 0.587, 0.114], np.float32)
    mx, mn = a.max(axis=2), a.min(axis=2)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    gray = (lum * 255).astype(np.uint8)
    lap = np.asarray(Image.fromarray(gray).filter(ImageFilter.FIND_EDGES), np.float32)
    return {"brightness": float(lum.mean()), "contrast": float(lum.std()), "saturation": float(sat.mean()),
            "sharpness": float(lap.var()), "clip_high": float((lum > 0.97).mean()), "clip_low": float((lum < 0.03).mean())}


def auto_enhance_params(stats: dict) -> dict:
    """Conservative automatic settings, explained."""
    p = {"brightness": 1.0, "contrast": 1.0, "saturation": 1.0, "sharpness": 1.0, "gamma": 1.0, "reasons": []}
    b = stats["brightness"]
    if b < 0.42:
        p["gamma"] = float(np.clip(1 + (0.46 - b) * 1.8, 1.0, 1.5))
        p["reasons"].append(f"brightened midtones (exposure {b:.2f})")
    elif b > 0.62:
        p["gamma"] = float(np.clip(1 - (b - 0.55) * 1.2, 0.8, 1.0))
        p["reasons"].append(f"darkened midtones (exposure {b:.2f})")
    if stats["contrast"] < 0.2 and stats["clip_high"] < 0.02:
        p["contrast"] = float(np.clip(0.22 / max(stats["contrast"], 0.05), 1.0, 1.35))
        p["reasons"].append("added contrast")
    if stats["saturation"] < 0.35:
        p["saturation"] = float(np.clip(0.4 / max(stats["saturation"], 0.08), 1.0, 1.4))
        p["reasons"].append("boosted colour")
    if stats["sharpness"] < 400:
        p["sharpness"] = 1.6
        p["reasons"].append("sharpened soft detail")
    else:
        p["sharpness"] = 1.2
    return p


def _gamma(im: Image.Image, g: float) -> Image.Image:
    if abs(g - 1) < 1e-3:
        return im
    inv = 1.0 / g
    lut = [min(255, int(((i / 255.0) ** inv) * 255 + 0.5)) for i in range(256)]
    return im.point(lut * len(im.getbands()))


def _vignette(im: Image.Image, strength: float) -> Image.Image:
    w, h = im.size
    y, x = np.ogrid[0:h, 0:w]
    r = np.sqrt(((x - w / 2) / (w / 2)) ** 2 + ((y - h / 2) / (h / 2)) ** 2)
    mask = np.clip(1 - strength * 0.6 * np.clip(r - 0.4, 0, 1) ** 1.5 * 1.6, 0, 1)
    a = np.asarray(im, np.float32) * mask[..., None]
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def _focus_blur(im: Image.Image, amount: float) -> Image.Image:
    """Blur the edges and keep the centre sharp (portrait-style background blur)."""
    blurred = im.filter(ImageFilter.GaussianBlur(2 + amount * 12))
    w, h = im.size
    y, x = np.ogrid[0:h, 0:w]
    r = np.sqrt(((x - w / 2) / (w / 2)) ** 2 + ((y - h / 2) / (h / 2)) ** 2)
    mask = np.clip((r - 0.35) / 0.5, 0, 1) * 255
    return Image.composite(blurred, im, Image.fromarray(mask.astype(np.uint8)))


def _frame(im: Image.Image, kind: str, color: str) -> Image.Image:
    if kind == "none":
        return im
    rgb = graphics.hex_rgb(color)
    w, h = im.size
    short = min(w, h)
    if kind == "thin":
        return ImageOps.expand(im, border=max(4, short // 80), fill=rgb)
    if kind == "polaroid":
        b = max(8, short // 30)
        return ImageOps.expand(ImageOps.expand(im, border=b, fill=(250, 250, 245)),
                               border=(0, 0, 0, b * 3), fill=(250, 250, 245))
    # neon: glowing inner border
    out = im.convert("RGBA")
    glow = Image.new("RGBA", out.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(glow)
    t = max(3, short // 120)
    inset = t * 4
    d.rounded_rectangle((inset, inset, w - inset, h - inset), radius=short // 30, outline=(*rgb, 255), width=t)
    halo = glow.filter(ImageFilter.GaussianBlur(t * 3))
    out = Image.alpha_composite(out, halo)
    out = Image.alpha_composite(out, halo)
    out = Image.alpha_composite(out, glow)
    return out.convert("RGB")


def apply_edit(src: Path, edit: ImageEdit, sticker_paths: dict[str, Path] | None = None) -> tuple[Image.Image, dict]:
    """Apply an ImageEdit to the source image. Returns (image, info about automatic choices)."""
    info: dict = {}
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        if getattr(im, "n_frames", 1) > 1:
            im.seek(0)
        im = im.convert("RGBA")
        bg = Image.new("RGBA", im.size, (11, 11, 18, 255))
        im = Image.alpha_composite(bg, im).convert("RGB")
    # geometry
    if edit.crop:
        x, y, w, h = edit.crop
        W, H = im.size
        box = (int(max(0, x) * W), int(max(0, y) * H), int(min(1, x + w) * W), int(min(1, y + h) * H))
        if box[2] - box[0] > 4 and box[3] - box[1] > 4:
            im = im.crop(box)
    if edit.rotate:
        im = im.rotate(-edit.rotate, resample=Image.BICUBIC, expand=True, fillcolor=(11, 11, 18))
    if edit.flip_h:
        im = ImageOps.mirror(im)
    if edit.aspect != "original":
        ta = ASPECTS[edit.aspect]
        W, H = im.size
        if edit.aspect_mode == "crop":
            if W / H > ta:
                nw = int(H * ta)
                im = im.crop(((W - nw) // 2, 0, (W - nw) // 2 + nw, H))
            else:
                nh = int(W / ta)
                im = im.crop((0, (H - nh) // 2, W, (H - nh) // 2 + nh))
        else:
            tw, th = (W, int(W / ta)) if W / H > ta else (int(H * ta), H)
            back = ImageOps.fit(im, (max(1, tw // 4), max(1, th // 4))).filter(ImageFilter.GaussianBlur(6)).resize((tw, th))
            back = ImageEnhance.Brightness(back).enhance(0.8)
            back.paste(im, ((tw - W) // 2, (th - H) // 2))
            im = back
    if max(im.size) > edit.max_size:
        im.thumbnail((edit.max_size, edit.max_size), Image.LANCZOS)
    # tone
    b, c, s, sh, g = edit.brightness, edit.contrast, edit.saturation, edit.sharpness, edit.gamma
    if edit.auto_enhance:
        stats = analyze_image(im)
        auto = auto_enhance_params(stats)
        info["auto"] = {**auto, "stats": {k: round(v, 3) for k, v in stats.items()}}
        b *= auto["brightness"]
        c *= auto["contrast"]
        s *= auto["saturation"]
        sh *= auto["sharpness"]
        g *= auto["gamma"]
    im = _gamma(im, g)
    if abs(b - 1) > 1e-3:
        im = ImageEnhance.Brightness(im).enhance(b)
    look_rgb, look_s, look_c = IMAGE_LOOKS[edit.look]
    if abs(c * look_c - 1) > 1e-3:
        im = ImageEnhance.Contrast(im).enhance(c * look_c)
    if abs(s * look_s - 1) > 1e-3:
        im = ImageEnhance.Color(im).enhance(s * look_s)
    if edit.look != "none" or abs(edit.warmth) > 1e-3:
        r, gg, bb = look_rgb
        r *= 1 + 0.08 * edit.warmth
        bb *= 1 - 0.08 * edit.warmth
        a = np.asarray(im, np.float32) * np.array([r, gg, bb], np.float32)
        im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    if abs(sh - 1) > 1e-3:
        im = ImageEnhance.Sharpness(im).enhance(min(sh, 3.0))
    if edit.background_blur > 0:
        im = _focus_blur(im, edit.background_blur)
    if edit.vignette > 0:
        im = _vignette(im, edit.vignette)
    # layers, in order (later layers on top)
    canvas = im.convert("RGBA")
    W, H = canvas.size
    short = min(W, H)
    for layer in edit.layers:
        if layer.type == "text":
            if not layer.text.strip():
                continue
            ov = graphics.text_image(layer.text, int(short * 0.08 * layer.scale), layer.color, layer.outline,
                                     shadow=layer.shadow, rotation=layer.rotation, opacity=layer.opacity)
        else:
            p = (sticker_paths or {}).get(layer.media_id or "")
            if not p:
                continue
            ov = graphics.scaled_overlay(p, int(W * 0.25 * layer.scale), layer.rotation, layer.opacity)
        _paste_clipped(canvas, ov, int(layer.x * W - ov.width / 2), int(layer.y * H - ov.height / 2))
    im = canvas.convert("RGB")
    im = _frame(im, edit.frame, edit.frame_color)
    return im, info


def _paste_clipped(canvas: Image.Image, ov: Image.Image, x: int, y: int) -> None:
    """alpha_composite with negative offsets (layer partly off-canvas)."""
    sx, sy = max(0, -x), max(0, -y)
    ex = min(ov.width, canvas.width - x)
    ey = min(ov.height, canvas.height - y)
    if sx >= ex or sy >= ey:
        return
    canvas.alpha_composite(ov.crop((sx, sy, ex, ey)), (max(0, x), max(0, y)))
