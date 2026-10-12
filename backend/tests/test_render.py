"""Real FFmpeg renders, checked with ffprobe."""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import probe
from PIL import Image

from app.presets import preset_settings
from app.schemas import Clip, ImageEdit, ImageLayer, Overlay, SpeedRamp, Timeline
from app.services.auto_color import ColorCorrection
from app.services.export import ExportManager
from app.services.image_studio import analyze_image, apply_edit
from app.services.media_inspector import MediaInspector
from app.services.renderer import FFmpegRenderer, SourceMedia


def _media(samples: Path) -> dict[str, SourceMedia]:
    ins = MediaInspector()
    v = samples / "sample_gameplay.mp4"
    return {
        "v": SourceMedia("v", "video", v, ins.inspect(v).info, ColorCorrection(gamma=1.1, sharpen=0.4)),
        "img": SourceMedia("img", "image", samples / "sample_screenshot.jpg",
                           ins.inspect(samples / "sample_screenshot.jpg").info),
        "stk": SourceMedia("stk", "sticker", samples / "sample_sticker.png",
                           ins.inspect(samples / "sample_sticker.png").info),
    }


def _render(tmp_path, samples, settings, tl, preview=True, name="out"):
    spec = ExportManager().spec(settings, (1280, 720), 30, preview=preview, x264_preset="ultrafast")
    r = FFmpegRenderer(settings, spec, tmp_path / "work", _media(samples), tmp_path / "assets", preview=preview,
                       x264_preset="ultrafast")
    out = tmp_path / f"{name}.{spec.ext}"
    info = r.render(tl, out)
    r.cleanup()
    return out, info


@pytest.mark.parametrize("preset", ["beast", "cinematic", "neon", "tiktok"])
def test_render_presets(tmp_path, samples, preset):
    s = preset_settings(preset, title="GG", clip_counter=True, watermark_text="@me")
    tl = Timeline(clips=[
        Clip(id="1", media_id="v", start=7.5, end=9.0, transition="flash", punch_in=True, shake=True),
        Clip(id="2", media_id="v", start=19.5, end=21.0, transition="glitch",
             ramp=SpeedRamp(at=0.4, duration=0.5, speed=0.5)),
        Clip(id="3", kind="image", media_id="img", duration=1.0, transition="zoom", motion="pan_left"),
        Clip(id="4", kind="card", text="THANKS", duration=1.0, transition="fade"),
    ], overlays=[
        Overlay(id="t", text="TITLE", start=0, end=1.5, animation="pop"),
        Overlay(id="s", type="sticker", media_id="stk", start=0.5, end=3, x=0.8, y=0.2, animation="bounce",
                rotation=15),
        Overlay(id="k", text="MOVE", start=1, end=3, animation="none",
                keyframes=[{"t": 0, "x": 0.2, "y": 0.8}, {"t": 1.5, "x": 0.8, "y": 0.8}]),
    ])
    out, info = _render(tmp_path, samples, s, tl)
    p = probe(out)
    v = next(x for x in p["streams"] if x["codec_type"] == "video")
    a = next(x for x in p["streams"] if x["codec_type"] == "audio")
    expected = 1.5 + (1.5 - 0.5 + 1.0) + 1.0 + 1.0
    assert abs(float(p["format"]["duration"]) - expected) < 0.15
    assert v["codec_name"] == "h264" and a["codec_name"] == "aac"
    w, h = (960, 540) if s.aspect == "16:9" else (540, 960) if s.aspect == "9:16" else (540, 676)
    assert (int(v["width"]), int(v["height"])) == (w, h)
    assert info["clip_boundaries"][-1] == pytest.approx(expected, abs=0.05)


def test_full_quality_webm_and_music(tmp_path, samples):
    from app.services.sound_library import generate_library_track
    s = preset_settings("smooth", format="webm_vp9", resolution="720p", music_id="m", transition_sfx=True)
    media_music = tmp_path / "m.wav"
    generate_library_track("neon", media_music)
    tl = Timeline(clips=[Clip(id="1", media_id="v", start=8, end=10, transition="zoom"),
                         Clip(id="2", media_id="v", start=20, end=22, transition="flash")],
                  music={"media_id": "m", "offset": 2.0, "volume": 0.8})
    spec = ExportManager().spec(s, (1280, 720), 30)
    media = _media(samples)
    media["m"] = SourceMedia("m", "audio", media_music, MediaInspector().inspect(media_music).info)
    r = FFmpegRenderer(s, spec, tmp_path / "w", media, tmp_path / "assets", x264_preset="ultrafast")
    out = tmp_path / "o.webm"
    r.render(tl, out)
    p = probe(out)
    names = {x["codec_name"] for x in p["streams"]}
    assert names == {"vp9", "opus"}
    assert abs(float(p["format"]["duration"]) - 4.0) < 0.15


def test_copy_path_when_no_overlays(tmp_path, samples):
    s = preset_settings("esports", resolution="720p", clip_counter=False)
    tl = Timeline(clips=[Clip(id="1", media_id="v", start=8, end=9.5)])
    out, info = _render(tmp_path, samples, s, tl, preview=False)
    assert info["width"] == 1280 and abs(info["duration"] - 1.5) < 0.1


def test_cancel_stops_render(tmp_path, samples):
    from app.services.ffmpeg import Cancelled
    s = preset_settings("beast")
    tl = Timeline(clips=[Clip(id="1", media_id="v", start=0, end=30)])
    spec = ExportManager().spec(s, (1280, 720), 30)
    r = FFmpegRenderer(s, spec, tmp_path / "w", _media(samples), tmp_path / "a", should_cancel=lambda: True)
    with pytest.raises(Cancelled):
        r.render(tl, tmp_path / "x.mp4")


# ---------------------------------------------------------------- Image Studio
def test_image_auto_enhance_brightens(samples):
    src = samples / "sample_screenshot.jpg"
    with Image.open(src) as im:
        before = analyze_image(im)
    out, info = apply_edit(src, ImageEdit(auto_enhance=True))
    after = analyze_image(out)
    assert after["brightness"] > before["brightness"] + 0.03
    assert after["contrast"] > before["contrast"]
    assert info["auto"]["reasons"]
    assert after["clip_high"] < 0.05


def test_image_layout_and_layers(samples):
    edit = ImageEdit(aspect="9:16", aspect_mode="blur_fill", look="neon", vignette=0.5, frame="neon",
                     background_blur=0.5,
                     layers=[ImageLayer(type="text", text="CLUTCH", y=0.2, rotation=-8),
                             ImageLayer(type="sticker", media_id="s", x=0.95, y=0.95, scale=1.5)])
    out, _ = apply_edit(samples / "sample_screenshot.jpg", edit, {"s": samples / "sample_sticker.png"})
    assert abs(out.width / out.height - 9 / 16) < 0.01
    crop, _ = apply_edit(samples / "sample_screenshot.jpg", ImageEdit(crop=(0.25, 0.25, 0.5, 0.5), rotate=90))
    assert crop.size == (540, 960)
