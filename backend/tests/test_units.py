"""Unit tests for the analysis, selection, effects and export modules."""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import pytest

from app.core.security import clean_display_name, safe_join
from app.presets import PRESETS, preset_settings
from app.schemas import Clip, ColorAdjust, ProjectSettings, SpeedRamp, Timeline
from app.services.audio_analysis import AudioAnalyzer, decode_audio
from app.services.auto_color import AutoColorCorrector, ColorStats
from app.services.effects import EffectsComposer, Frame
from app.services.export import ExportManager
from app.services.highlights import Candidate, HighlightAnalyzer
from app.services.media_inspector import InspectionError, MediaInspector
from app.services.sound_library import generate_library_track
from app.services.timeline import ClipSelector, MediaMeta, TimelineBuilder
from app.services.video_analysis import SceneDetector, sample_frames

BURSTS = [(7.0, 11.0), (19.0, 23.0), (31.0, 35.0)]


@pytest.fixture(scope="module")
def analysed(samples):
    p = samples / "sample_gameplay.mp4"
    ins = MediaInspector().inspect(p)
    vs = sample_frames(p, ins.info["duration"], ins.info["width"], ins.info["height"], 6.0)
    au = AudioAnalyzer().features(decode_audio(p))
    return p, ins, vs, au


# ---------------------------------------------------------------- MediaInspector
def test_inspector_video(analysed):
    _, ins, _, _ = analysed
    assert ins.kind == "video"
    assert ins.info["width"] == 1280 and ins.info["height"] == 720
    assert abs(ins.info["duration"] - 40) < 0.2
    assert ins.info["fps"] == 30 and ins.info["has_audio"] and ins.info["video_codec"] == "h264"


def test_inspector_images(samples):
    assert MediaInspector().inspect(samples / "sample_screenshot.jpg").kind == "image"
    st = MediaInspector().inspect(samples / "sample_sticker.png")
    assert st.kind == "sticker" and st.info["has_alpha"]


def test_inspector_rejects_bad_files(tmp_path):
    bad = tmp_path / "fake.mp4"
    bad.write_bytes(b"this is not a video" * 100)
    with pytest.raises(InspectionError):
        MediaInspector().inspect(bad)
    exe = tmp_path / "evil.exe"
    exe.write_bytes(b"MZ")
    with pytest.raises(InspectionError):
        MediaInspector().inspect(exe)


# ---------------------------------------------------------------- SceneDetector
def test_scene_detector_finds_hard_cuts(tmp_path):
    out = tmp_path / "cuts.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=red:s=320x180:d=2:r=30",
                    "-f", "lavfi", "-i", "color=c=blue:s=320x180:d=2:r=30", "-f", "lavfi",
                    "-i", "color=c=green:s=320x180:d=2:r=30", "-filter_complex", "[0][1][2]concat=n=3:v=1",
                    str(out)], check=True)
    vs = sample_frames(out, 6.0, 320, 180, 6.0)
    cuts = SceneDetector().cut_times(vs)
    assert len(cuts) == 2
    assert abs(cuts[0] - 2.0) < 0.35 and abs(cuts[1] - 4.0) < 0.35


# ---------------------------------------------------------------- AudioAnalyzer
def test_audio_transients_are_in_bursts(analysed):
    *_, au = analysed
    assert len(au.transient_times) >= 20
    inside = [t for t in au.transient_times if any(a - 0.3 <= t <= b + 0.3 for a, b in BURSTS)]
    assert len(inside) / len(au.transient_times) > 0.8


def test_music_beats_match_tempo(tmp_path):
    wav = generate_library_track("beast", tmp_path / "beast.wav")
    m = AudioAnalyzer().analyze_music(wav)
    assert abs(m.bpm - 140) < 4 or abs(m.bpm - 70) < 2
    assert len(m.beats) > 50 and len(m.downbeats) >= len(m.beats) // 4 - 1
    gaps = np.diff(m.beats)
    assert abs(float(np.median(gaps)) - 60 / 140) < 0.03 or abs(float(np.median(gaps)) - 120 / 140) < 0.05
    assert 0 <= m.suggested_offset < m.duration / 2


# ---------------------------------------------------------------- HighlightAnalyzer
def test_highlights_land_in_action_bursts(analysed):
    _, ins, vs, au = analysed
    cands, summary = HighlightAnalyzer.for_pacing(None, 2).candidates("m", ins.info["duration"], vs, au, [])
    assert len(cands) >= 3
    for c in cands:
        assert any(a - 1 <= c.peak <= b + 1 for a, b in BURSTS), c
        assert c.evidence == "heuristic" and c.reasons
    covered = {i for i, (a, b) in enumerate(BURSTS) for c in cands if a - 1 <= c.peak <= b + 1}
    assert covered == {0, 1, 2}
    # calm stretches are reported as quiet (shortenable)
    assert any(q[1] - q[0] >= 3 and q[1] <= 8 for q in summary["quiet_sections"])
    assert all(not (a < q[0] < b) for q in summary["quiet_sections"] for a, b in BURSTS)


# ---------------------------------------------------------------- AutoColorCorrector
def test_auto_color_is_conservative():
    dark = AutoColorCorrector().correct(ColorStats(0.2, 0.08, 0.15, 100, 0.005, 0.01, 0))
    assert 1.0 < dark.gamma <= 1.35 and dark.contrast <= 1.2 and dark.saturation <= 1.3 and dark.reasons
    clipped = AutoColorCorrector().correct(ColorStats(0.5, 0.3, 0.4, 900, 0.005, 0.0, 0.1))
    assert clipped.contrast < 1.0
    noisy = AutoColorCorrector().correct(ColorStats(0.45, 0.22, 0.42, 900, 0.03, 0, 0))
    assert noisy.denoise and noisy.sharpen <= 0.35


# ---------------------------------------------------------------- ClipSelector / TimelineBuilder
def _cands():
    return [Candidate("v", a, a + 3, a + 2, s, s, 0.8, ["x"], {}) for a, s in
            [(5, 0.9), (6, 0.85), (15, 0.7), (25, 0.95), (35, 0.2), (45, 0.6)]]


def test_selector_avoids_overlap_and_weak_clips():
    sel = ClipSelector().select(_cands(), 12, 2.0, ["v"])
    for i, a in enumerate(sel):
        for b in sel[i + 1:]:
            assert not (a.start < b.end and b.start < a.end)
    assert all(c.score >= 0.3 * 0.95 for c in sel)
    assert [c.peak for c in sel] == sorted(c.peak for c in sel)  # chronological


def test_timeline_cuts_on_beats():
    s = preset_settings("beast", target_duration=12, music_id="mus")
    music = {"bpm": 120.0, "beats": [i * 0.5 for i in range(200)], "offset": 1.0}
    sel = ClipSelector().select(_cands(), 12, 1.0, ["v"])
    tl = TimelineBuilder(s).build(sel, {"v": MediaMeta("v", "video", 60)}, ["img"], music)
    t = 0.0
    for c in tl.clips:
        t += c.output_duration()
        assert abs(t / 0.5 - round(t / 0.5)) < 1e-6, "every cut should land on a beat"
    assert tl.duration() <= 12 + 0.5 + 1e-6
    assert any(c.kind == "image" for c in tl.clips)
    assert tl.music and tl.music.offset == 1.0
    for c in tl.clips:
        if c.kind == "video":
            assert 0 <= c.start < c.end <= 60


def test_timeline_reports_short_footage():
    s = preset_settings("smooth", target_duration=60)
    cands = [Candidate("v", 2, 6, 4, 1.0, 1.0, 0.8, ["x"], {})]
    tl = TimelineBuilder(s).build(cands, {"v": MediaMeta("v", "video", 10)}, [])
    assert tl.duration() < 60 and any("shorter" in n for n in tl.notes)


def test_speed_ramp_duration_maths():
    c = Clip(id="a", media_id="v", start=0, end=3, ramp=SpeedRamp(at=1, duration=1, speed=0.5))
    assert c.output_duration() == pytest.approx(4.0)
    assert Timeline(clips=[c, Clip(id="b", kind="image", media_id="i", duration=2)]).duration() == pytest.approx(6)


# ---------------------------------------------------------------- EffectsComposer
def test_effect_toggles_are_respected():
    s = ProjectSettings()
    s.effects.sharpen = False
    s.effects.auto_enhance = False
    s.look = "none"
    chain = EffectsComposer(s).grade(None)
    assert not any(f.startswith("unsharp") for f in chain)
    s2 = ProjectSettings(color=ColorAdjust(contrast=1.3, saturation=1.2), look="none")
    chain2 = ",".join(EffectsComposer(s2).grade(None))
    assert "contrast=1.3" in chain2 and "saturation=1.2" in chain2
    s3 = preset_settings("cinematic")
    fin = EffectsComposer(s3).finish(Clip(id="c", media_id="v", end=2, transition="fade"), 2.0,
                                     Frame(1920, 1080, 30), False, True)
    assert any("drawbox" in f for f in fin) and any("fade=t=out" in f for f in fin)
    s4 = preset_settings("esports")
    fin4 = EffectsComposer(s4).finish(Clip(id="c", media_id="v", end=2, transition="cut", shake=True), 2.0,
                                      Frame(1920, 1080, 30), False, False)
    assert not any("sin(" in f for f in fin4), "shake is off in the esports preset"


def test_all_presets_validate():
    for name in PRESETS:
        s = preset_settings(name)
        assert s.preset == name


# ---------------------------------------------------------------- ExportManager
@pytest.mark.parametrize("aspect,res,wh", [("16:9", "1080p", (1920, 1080)), ("9:16", "1080p", (1080, 1920)),
                                          ("1:1", "720p", (720, 720)), ("4:5", "1080p", (1080, 1350)),
                                          ("16:9", "2160p", (3840, 2160))])
def test_export_geometry(aspect, res, wh):
    s = ProjectSettings(aspect=aspect, resolution=res)
    assert ExportManager().geometry(s, (1280, 720), False) == wh


def test_export_specs():
    em = ExportManager()
    s = ProjectSettings(format="webm_vp9")
    sp = em.spec(s, (1280, 720), 60)
    assert sp.ext == "webm" and "libvpx-vp9" in sp.video_args
    prev = em.spec(ProjectSettings(), (1280, 720), 60, preview=True)
    assert prev.height == 540 and prev.fps == 30 and "ultrafast" in prev.video_args


# ---------------------------------------------------------------- security helpers
def test_safe_join_blocks_traversal(tmp_path):
    assert safe_join(tmp_path, "a/b.txt") == (tmp_path / "a" / "b.txt").resolve()
    for bad in ("../x", "a/../../x", "/etc/passwd"):
        with pytest.raises(ValueError):
            safe_join(tmp_path, bad)


def test_clean_display_name():
    assert clean_display_name("../../etc/passwd") == "passwd"
    assert clean_display_name("my clip; rm -rf ~.mp4") == "my clip_ rm -rf _.mp4"
    assert clean_display_name("") == "untitled"
    assert "/" not in clean_display_name("a/b\\c")


def test_inspector_handles_path_names(tmp_path: Path, samples):
    # The display name decides the extension check, never the stored path.
    ins = MediaInspector().inspect(samples / "sample_screenshot.jpg", "../../shot.jpg")
    assert ins.kind == "image"


def test_loudness_signal_counts_negative_db():
    # Loudness is in dB (always below 0); max-binning must not clamp it to 0.
    from app.services.highlights import _bin
    out = _bin(np.array([0.0, 0.1, 0.6]), np.array([-30.0, -12.0, -40.0]), 3, "max")
    assert out[0] == -12.0 and out[2] == -40.0 and np.isfinite(out).all()


def test_flash_ignores_tiny_brightness_wobble():
    from app.services.highlights import MIN_SCALE, robust_z
    wobble = np.abs(np.random.default_rng(0).normal(0, 0.0005, 400))
    assert (np.clip(robust_z(wobble, MIN_SCALE["flash"]), 0, 4) / 4 < 0.5).all()
    spike = wobble.copy()
    spike[200] = 0.15  # a real muzzle flash or explosion
    assert np.clip(robust_z(spike, MIN_SCALE["flash"]), 0, 4)[200] == 4
