"""Pydantic request/response models and the timeline document format."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Aspect = Literal["16:9", "9:16", "1:1", "4:5"]
Resolution = Literal["source", "720p", "1080p", "1440p", "2160p"]
OutputFormat = Literal["mp4_h264", "mp4_h265", "webm_vp9"]
Quality = Literal["draft", "standard", "high"]
Transition = Literal["cut", "flash", "fade", "zoom", "glitch", "whip"]
Reframe = Literal["smart_crop", "blur_fill", "center_crop"]
GameAudio = Literal["keep", "reduce", "mute"]
TextAnimation = Literal["none", "fade", "pop", "slide_left", "slide_up", "bounce"]
PresetName = Literal["beast", "cinematic", "esports", "smooth", "neon", "tiktok", "youtube", "shorts", "showcase"]
Look = Literal["none", "beast", "cinematic", "esports", "clean", "neon", "warm", "cold", "vintage", "bw"]


# --------------------------------------------------------------------------- effects / color
class EffectToggles(BaseModel):
    """Every visual effect can be switched off individually."""

    auto_enhance: bool = True
    sharpen: bool = True
    denoise: bool = True
    vignette: bool = False
    glow: bool = False
    motion_blur: bool = False
    speed_ramps: bool = False
    punch_in: bool = False
    shake: bool = False
    flash: bool = False
    light_leaks: bool = False
    chromatic: bool = False
    letterbox: bool = False


class ColorAdjust(BaseModel):
    """Manual colour controls. None means "use the automatic value"."""

    brightness: float | None = Field(None, ge=-0.3, le=0.3)
    contrast: float | None = Field(None, ge=0.5, le=1.8)
    saturation: float | None = Field(None, ge=0.0, le=2.0)
    gamma: float | None = Field(None, ge=0.6, le=1.6)
    shadows: float = Field(0.0, ge=-0.2, le=0.2)
    highlights: float = Field(0.0, ge=-0.2, le=0.2)
    sharpen_amount: float | None = Field(None, ge=0.0, le=1.2)


class HighlightWeights(BaseModel):
    motion: float = Field(1.0, ge=0, le=5)
    audio: float = Field(1.0, ge=0, le=5)
    transients: float = Field(1.2, ge=0, le=5)
    scene: float = Field(0.6, ge=0, le=5)
    flash: float = Field(0.5, ge=0, le=5)
    clarity: float = Field(0.4, ge=0, le=5)
    variety: float = Field(0.5, ge=0, le=5)


# --------------------------------------------------------------------------- overlays
class Keyframe(BaseModel):
    t: float = Field(ge=0)  # seconds relative to the overlay start
    x: float = Field(0.5, ge=-0.5, le=1.5)
    y: float = Field(0.5, ge=-0.5, le=1.5)
    opacity: float = Field(1.0, ge=0, le=1)


class Overlay(BaseModel):
    id: str
    type: Literal["text", "sticker", "counter"] = "text"
    text: str = ""
    media_id: str | None = None  # sticker image (PNG/GIF)
    start: float = Field(0.0, ge=0)
    end: float = Field(3.0, ge=0)
    x: float = Field(0.5, ge=-0.5, le=1.5)  # centre, relative to frame width
    y: float = Field(0.15, ge=-0.5, le=1.5)
    scale: float = Field(1.0, gt=0, le=5)  # text: relative font size; sticker: fraction of frame width * 0.25
    rotation: float = Field(0.0, ge=-180, le=180)
    opacity: float = Field(1.0, ge=0, le=1)
    color: str = "#FFFFFF"
    outline: str = "#000000"
    animation: TextAnimation = "pop"
    keyframes: list[Keyframe] = Field(default_factory=list)
    layer: int = 0

    @field_validator("color", "outline")
    @classmethod
    def _hex(cls, v: str) -> str:
        v = v.strip()
        if not (len(v) == 7 and v.startswith("#") and all(c in "0123456789abcdefABCDEF" for c in v[1:])):
            raise ValueError("colour must look like #RRGGBB")
        return v.upper()


# --------------------------------------------------------------------------- timeline
class SpeedRamp(BaseModel):
    at: float = Field(ge=0)  # offset into the clip's source range, seconds
    duration: float = Field(gt=0, le=5)
    speed: float = Field(0.5, ge=0.25, le=1.0)


class Clip(BaseModel):
    id: str
    kind: Literal["video", "image", "card"] = "video"
    media_id: str | None = None
    start: float = Field(0.0, ge=0)  # source in-point (video)
    end: float = Field(0.0, ge=0)  # source out-point (video)
    duration: float = Field(0.0, ge=0)  # output duration (image/card); computed for video
    ramp: SpeedRamp | None = None
    transition: Transition = "cut"
    punch_in: bool = False
    shake: bool = False
    motion: Literal["none", "zoom_in", "zoom_out", "pan_left", "pan_right"] = "zoom_in"
    crop_x: float | None = Field(None, ge=0, le=1)  # horizontal crop centre for reframing
    text: str = ""  # card title
    subtitle: str = ""
    score: float = 0.0
    reasons: list[str] = Field(default_factory=list)
    muted: bool = False

    def output_duration(self) -> float:
        if self.kind != "video":
            return self.duration
        src = max(0.0, self.end - self.start)
        if self.ramp:
            d = min(self.ramp.duration, max(0.0, src - self.ramp.at))
            return src - d + d / self.ramp.speed
        return src


class MusicTrack(BaseModel):
    media_id: str
    offset: float = Field(0.0, ge=0)  # where in the song the montage starts
    volume: float = Field(0.8, ge=0, le=2)
    fade_in: float = Field(0.5, ge=0, le=10)
    fade_out: float = Field(1.5, ge=0, le=10)


class Timeline(BaseModel):
    version: int = 1
    clips: list[Clip] = Field(default_factory=list)
    overlays: list[Overlay] = Field(default_factory=list)
    music: MusicTrack | None = None
    bpm: float | None = None
    notes: list[str] = Field(default_factory=list)

    def duration(self) -> float:
        return sum(c.output_duration() for c in self.clips)


# --------------------------------------------------------------------------- project settings
class ProjectSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    preset: PresetName = "beast"
    target_duration: int | None = Field(30, ge=5, le=600)  # None = automatic
    aspect: Aspect = "16:9"
    reframe: Reframe = "smart_crop"
    resolution: Resolution = "1080p"
    fps: int | None = Field(30, ge=15, le=120)  # None = source
    quality: Quality = "standard"
    format: OutputFormat = "mp4_h264"
    look: Look = "beast"
    look_strength: float = Field(1.0, ge=0, le=1.5)
    color: ColorAdjust = Field(default_factory=ColorAdjust)
    effects: EffectToggles = Field(default_factory=EffectToggles)
    weights: HighlightWeights = Field(default_factory=HighlightWeights)
    beats_per_clip: int = Field(2, ge=1, le=16)
    transition: Transition | Literal["auto"] = "auto"
    finale_last: bool = True  # put the strongest moment at the end

    music_id: str | None = None
    music_volume: float = Field(0.8, ge=0, le=2)
    game_audio: GameAudio = "reduce"
    ducking: bool = True
    duck_amount: float = Field(0.5, ge=0, le=1)  # 0 = no ducking, 1 = strongest
    normalize_audio: bool = True
    transition_sfx: bool = False

    image_duration: float = Field(2.5, ge=0.5, le=10)
    title: str = Field("", max_length=80)
    subtitle: str = Field("", max_length=120)
    outro_text: str = Field("", max_length=80)
    watermark_text: str = Field("", max_length=60)
    watermark_media_id: str | None = None
    watermark_position: Literal["top_left", "top_right", "bottom_left", "bottom_right"] = "bottom_right"
    watermark_opacity: float = Field(0.7, ge=0.05, le=1)
    clip_counter: bool = False


# --------------------------------------------------------------------------- API models
class MediaOut(BaseModel):
    id: str
    kind: str
    name: str
    folder: str
    original_filename: str
    mime: str
    size_bytes: int
    source: str
    license: str
    info: dict[str, Any]
    has_analysis: bool
    created_at: datetime
    url: str
    thumb_url: str | None
    contact_sheet_url: str | None


class OnlineTrack(BaseModel):
    id: str
    title: str
    creator: str
    duration: float
    license: str
    license_url: str
    attribution: str
    genres: list[str]
    preview_url: str
    page_url: str
    source: str
    imported_media_id: str | None = None


class OnlineMusicSearch(BaseModel):
    results: list[OnlineTrack]
    page: int
    page_count: int
    result_count: int


class OnlineMusicImport(BaseModel):
    track_id: str = Field(min_length=1, max_length=64)


class MediaUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    folder: str | None = Field(None, max_length=100)


class ProjectCreate(BaseModel):
    name: str = Field("My Montage", min_length=1, max_length=200)
    media_ids: list[str] = Field(default_factory=list)
    settings: ProjectSettings | None = None
    preset: PresetName | None = None  # apply this preset's style; music/titles/export from `settings` are kept


class ProjectUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    media_ids: list[str] | None = None
    settings: ProjectSettings | None = None


class ProjectOut(BaseModel):
    id: str
    name: str
    media_ids: list[str]
    settings: ProjectSettings
    timeline: Timeline | None
    highlights: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
    revision_count: int
    latest_export: dict[str, Any] | None = None


class TimelineSave(BaseModel):
    timeline: Timeline
    note: str = Field("Manual edit", max_length=200)


class RevisionOut(BaseModel):
    id: str
    note: str
    created_at: datetime
    clip_count: int
    duration: float


class JobOut(BaseModel):
    id: str
    project_id: str | None
    kind: str
    status: str
    stage: str
    progress: float
    message: str
    eta_seconds: float | None
    result: dict[str, Any] | None
    error: str | None
    attempts: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class AutoEditRequest(BaseModel):
    settings: ProjectSettings | None = None
    render: bool = True


class RenderRequest(BaseModel):
    preview: bool = False


class ExportOut(BaseModel):
    id: str
    project_id: str | None
    kind: str
    name: str
    format: str
    width: int
    height: int
    duration: float
    size_bytes: int
    settings: dict[str, Any]
    created_at: datetime
    url: str
    download_url: str
    thumb_url: str | None


class QuickMontageRequest(BaseModel):
    """One-click: create a project from media and immediately auto-edit + render it."""

    media_ids: list[str] = Field(min_length=1)
    preset: PresetName = "beast"
    target_duration: int | None = Field(None, ge=5, le=600)
    music_id: str | None = None
    name: str = Field("My Montage", max_length=200)


# --------------------------------------------------------------------------- image studio
class ImageLayer(BaseModel):
    type: Literal["text", "sticker"]
    text: str = Field("", max_length=200)
    media_id: str | None = None
    x: float = Field(0.5, ge=-0.5, le=1.5)
    y: float = Field(0.5, ge=-0.5, le=1.5)
    scale: float = Field(1.0, gt=0, le=6)
    rotation: float = Field(0.0, ge=-180, le=180)
    opacity: float = Field(1.0, ge=0, le=1)
    color: str = "#FFFFFF"
    outline: str = "#000000"
    shadow: bool = True


class ImageEdit(BaseModel):
    crop: tuple[float, float, float, float] | None = None  # x, y, w, h relative 0..1
    rotate: float = Field(0.0, ge=-180, le=180)
    flip_h: bool = False
    aspect: Literal["original", "16:9", "9:16", "1:1", "4:5", "4:3"] = "original"
    aspect_mode: Literal["crop", "blur_fill"] = "crop"
    max_size: int = Field(2160, ge=128, le=8192)
    auto_enhance: bool = False
    brightness: float = Field(1.0, ge=0.3, le=2.0)
    contrast: float = Field(1.0, ge=0.3, le=2.0)
    saturation: float = Field(1.0, ge=0.0, le=2.5)
    sharpness: float = Field(1.0, ge=0.0, le=3.0)
    gamma: float = Field(1.0, ge=0.5, le=2.0)
    warmth: float = Field(0.0, ge=-1, le=1)
    look: Look = "none"
    vignette: float = Field(0.0, ge=0, le=1)
    background_blur: float = Field(0.0, ge=0, le=1)  # radial focus blur around the centre
    frame: Literal["none", "thin", "neon", "polaroid"] = "none"
    frame_color: str = "#22D3EE"
    layers: list[ImageLayer] = Field(default_factory=list)


class ImageRenderRequest(BaseModel):
    edit: ImageEdit
    format: Literal["png", "jpeg"] = "png"
    quality: int = Field(92, ge=40, le=100)
    save: bool = True
    name: str | None = Field(None, max_length=200)


class AddToMontageRequest(BaseModel):
    project_id: str
    media_id: str
    duration: float = Field(2.5, ge=0.5, le=10)
    transition: Transition = "flash"
    motion: Literal["none", "zoom_in", "zoom_out", "pan_left", "pan_right"] = "zoom_in"
    position: int | None = None  # index in the clip list; None = spread automatically / append
    snap_to_beats: bool = True
