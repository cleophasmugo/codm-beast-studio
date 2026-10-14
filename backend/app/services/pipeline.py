"""The auto-edit pipeline: analyse -> select -> build timeline -> render -> export.

These functions are what background jobs call. They load rows, call the services, and write
results back to the database.
"""

from __future__ import annotations

import logging
import shutil
from datetime import UTC
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.security import clean_display_name
from ..db.models import Export, Job, Media, Project, TimelineRevision
from ..db.session import session_scope
from ..jobs.context import JobContext
from ..presets import PRESETS
from ..schemas import ProjectSettings, Timeline
from ..storage.base import get_storage
from .audio_analysis import AudioAnalyzer, AudioFeatures, decode_audio
from .auto_color import AutoColorCorrector, ColorStats
from .detectors import run_detectors
from .export import ExportManager
from .highlights import Candidate, HighlightAnalyzer
from .maintenance import LIBRARY_OWNER
from .renderer import FFmpegRenderer, SourceMedia
from .thumbnails import ThumbnailGenerator
from .timeline import ClipSelector, MediaMeta, TimelineBuilder
from .video_analysis import FrameSamples, SceneDetector, sample_frames

log = logging.getLogger(__name__)
ANALYSIS_VERSION = 3  # 3: built-in CODM kill notice detector


class PipelineError(RuntimeError):
    """An error with a message that is safe and useful to show the user."""


# --------------------------------------------------------------------------- analysis cache
def _signals_key(media_id: str) -> str:
    return f"analysis/{media_id}.npz"


def save_signals(media_id: str, vs: FrameSamples, au: AudioFeatures) -> None:
    p = get_storage().path_for(_signals_key(media_id))
    arrays: dict[str, Any] = {f"v_{k}": getattr(vs, k) for k in (
        "times", "motion", "flow", "centroid_x", "brightness", "contrast", "saturation", "sharpness", "noise",
        "clip_low", "clip_high", "hist_diff")}
    arrays.update({"v_fps": np.array([vs.fps]), "a_rate": np.array([au.frame_rate]), "a_rms": au.rms_db,
                   "a_onset": au.onset, "a_hf": au.hf_flux, "a_tr": np.array(au.transient_times),
                   "a_sil": np.array(au.silences).reshape(-1, 2), "a_dur": np.array([au.duration])})
    with open(p, "wb") as fh:
        np.savez_compressed(fh, **arrays)


def load_signals(media_id: str) -> tuple[FrameSamples, AudioFeatures] | None:
    st = get_storage()
    key = _signals_key(media_id)
    if not st.exists(key):
        return None
    with np.load(st.path_for(key)) as z:
        vs = FrameSamples(fps=float(z["v_fps"][0]))
        for k in ("times", "motion", "flow", "centroid_x", "brightness", "contrast", "saturation", "sharpness",
                  "noise", "clip_low", "clip_high", "hist_diff"):
            setattr(vs, k, z[f"v_{k}"])
        au = AudioFeatures(frame_rate=float(z["a_rate"][0]), rms_db=z["a_rms"], onset=z["a_onset"],
                           hf_flux=z["a_hf"], transient_times=[float(x) for x in z["a_tr"]],
                           silences=[(float(a), float(b)) for a, b in z["a_sil"]], duration=float(z["a_dur"][0]))
    return vs, au


def analyze_video(db: Session, m: Media, ctx: JobContext | None = None, force: bool = False) -> dict:
    """Run frame + audio analysis once per video and cache it. Returns the media's analysis summary."""
    if not force and m.analysis and m.analysis.get("version") == ANALYSIS_VERSION and load_signals(m.id):
        return m.analysis
    s = get_settings()
    path = get_storage().path_for(m.storage_key)
    info = m.info
    vs = sample_frames(path, info["duration"], info.get("width", 0), info.get("height", 0), s.analysis_fps,
                       on_progress=(lambda p: ctx.progress(p * 0.8, "Analysing video", f"Watching {m.name}"))
                       if ctx else None,
                       should_cancel=ctx.cancelled if ctx else None)
    if ctx:
        ctx.progress(0.85, "Analysing audio", f"Listening to {m.name}", force=True)
    au = AudioAnalyzer().features(decode_audio(path)) if info.get("has_audio") else AudioFeatures(frame_rate=43.07)
    cuts = SceneDetector().cut_times(vs)
    events = run_detectors(path, info["duration"])
    stats = ColorStats.from_samples(vs)
    save_signals(m.id, vs, au)
    analysis = {
        "version": ANALYSIS_VERSION, "kind": "video", "scene_cuts": cuts,
        "color_stats": stats.__dict__, "auto_color": AutoColorCorrector().correct(stats).as_dict(),
        "events": [e.__dict__ for e in events], "transient_count": len(au.transient_times),
        "silences": [list(x) for x in au.silences],
    }
    m.analysis = analysis
    db.commit()  # release the write lock before more progress updates (SQLite has one writer)
    return analysis


def analyze_music(db: Session, m: Media) -> dict:
    if m.analysis and m.analysis.get("version") == ANALYSIS_VERSION and m.analysis.get("beats") is not None:
        return m.analysis
    res = AudioAnalyzer().analyze_music(get_storage().path_for(m.storage_key)).as_dict()
    res.update({"version": ANALYSIS_VERSION, "kind": "music"})
    m.analysis = res
    db.commit()
    return res


def candidates_for(m: Media, settings: ProjectSettings) -> tuple[list[Candidate], dict]:
    sig = load_signals(m.id)
    if sig is None:
        raise PipelineError(f"{m.name} has not been analysed yet")
    vs, au = sig
    from .detectors import DetectedEvent
    events = [DetectedEvent(**e) for e in (m.analysis or {}).get("events", [])]
    an = HighlightAnalyzer.for_pacing(settings.weights, settings.beats_per_clip)
    return an.candidates(m.id, m.info["duration"], vs, au, (m.analysis or {}).get("scene_cuts", []), events)


# --------------------------------------------------------------------------- helpers
def _project_media(db: Session, p: Project) -> list[Media]:
    if not p.media_ids:
        return []
    rows = db.scalars(select(Media).where(Media.id.in_(p.media_ids), Media.owner_id.in_((p.owner_id, LIBRARY_OWNER)))).all()
    by_id = {r.id: r for r in rows}
    return [by_id[i] for i in p.media_ids if i in by_id]


def _source_media(db: Session, owner: str, ids: set[str]) -> dict[str, SourceMedia]:
    out: dict[str, SourceMedia] = {}
    if not ids:
        return out
    st = get_storage()
    from .auto_color import ColorCorrection
    for m in db.scalars(select(Media).where(Media.id.in_(ids), Media.owner_id.in_((owner, LIBRARY_OWNER)))).all():
        corr = None
        if m.kind == "video" and m.analysis and m.analysis.get("auto_color"):
            ac = m.analysis["auto_color"]
            corr = ColorCorrection(**{k: ac[k] for k in ("brightness", "contrast", "saturation", "gamma",
                                                         "sharpen", "denoise")})
        elif m.kind == "video":
            corr = ColorCorrection(sharpen=0.4)
        out[m.id] = SourceMedia(m.id, m.kind, st.path_for(m.storage_key), m.info, corr, m.source)
    return out


def save_timeline(db: Session, p: Project, tl: Timeline, note: str) -> None:
    data = tl.model_dump(mode="json")
    p.timeline = data
    db.add(TimelineRevision(project_id=p.id, note=note[:200], timeline=data))
    # keep the history bounded
    revs = db.scalars(select(TimelineRevision).where(TimelineRevision.project_id == p.id)
                      .order_by(TimelineRevision.created_at.desc())).all()
    for old in revs[100:]:
        db.delete(old)


# --------------------------------------------------------------------------- auto edit
def build_auto_timeline(db: Session, p: Project, ctx: JobContext | None = None) -> Timeline:
    settings = ProjectSettings.model_validate(p.settings or {})
    media = _project_media(db, p)
    # The reaction clip is a punchline, not gameplay: never mine it for highlights.
    videos = [m for m in media if m.kind == "video" and m.id != settings.reaction_clip_id]
    images = [m for m in media if m.kind == "image"]
    if not videos and not images:
        raise PipelineError("Add at least one gameplay video or screenshot to this project first.")
    for i, v in enumerate(videos):
        if ctx:
            ctx.span(0.0 + 0.4 * i / len(videos), 0.4 * (i + 1) / len(videos))
        analyze_video(db, v, ctx)
    if ctx:
        ctx.span(0.4, 0.45).progress(0.0, "Choosing highlights", "Ranking the best moments", force=True)
    music = None
    if settings.music_id:
        mm = db.get(Media, settings.music_id)
        if mm and mm.owner_id in (p.owner_id, LIBRARY_OWNER) and mm.kind == "audio":
            music = analyze_music(db, mm)
            music = {**music, "offset": music.get("suggested_offset", 0.0)}
        else:
            settings.music_id = None
    all_cands: list[Candidate] = []
    highlights: dict[str, Any] = {"media": {}}
    for v in videos:
        cands, summary = candidates_for(v, settings)
        all_cands += cands
        highlights["media"][v.id] = {"name": v.name, "duration": v.info["duration"],
                                     "candidates": [c.as_dict() for c in cands], **summary,
                                     "auto_color": (v.analysis or {}).get("auto_color")}
    beat = 60.0 / float((music or {}).get("bpm") or 120.0)
    est = max(1.0, settings.beats_per_clip * beat)
    selector = ClipSelector(variety=settings.weights.variety)
    selected = selector.select(all_cands, settings.target_duration, est, [v.id for v in videos])
    metas = {v.id: MediaMeta(v.id, "video", v.info["duration"]) for v in videos}
    if settings.reaction_clip_id:
        rm = db.get(Media, settings.reaction_clip_id)
        if rm and rm.owner_id == p.owner_id and rm.kind == "video":
            metas[rm.id] = MediaMeta(rm.id, "video", float(rm.info.get("duration") or 0))
    tl = TimelineBuilder(settings).build(selected, metas, [m.id for m in images], music)
    highlights["selected"] = [c.as_dict() for c in selected]
    highlights["evidence_note"] = (
        "Kills are found from CODM's yellow KNOCKED DOWN / ELIMINATED notice and always rank first; each kill clip "
        "runs from the fight to just after the notice. Other moments come from motion, sound spikes, flashes and "
        "scene changes and are heuristic guesses.")
    p.highlights = highlights
    save_timeline(db, p, tl, f"Auto edit ({PRESETS[settings.preset]['label']})")
    db.flush()
    return tl


# --------------------------------------------------------------------------- render
def render_project(db: Session, p: Project, job: Job, ctx: JobContext, preview: bool) -> dict:
    if not p.timeline:
        raise PipelineError("This project has no timeline yet. Run Auto Edit first.")
    s = get_settings()
    settings = ProjectSettings.model_validate(p.settings or {})
    tl = Timeline.model_validate(p.timeline)
    ids = {c.media_id for c in tl.clips if c.media_id} | {o.media_id for o in tl.overlays if o.media_id}
    if tl.music:
        ids.add(tl.music.media_id)
    if settings.watermark_media_id:
        ids.add(settings.watermark_media_id)
    srcs = _source_media(db, p.owner_id, ids)
    for c in tl.clips:  # make sure every video has colour analysis for auto-enhance
        if c.kind == "video" and c.media_id in srcs and not (db.get(Media, c.media_id).analysis or {}).get("auto_color"):
            analyze_video(db, db.get(Media, c.media_id))
            srcs = _source_media(db, p.owner_id, ids)
    first_video = next((srcs[c.media_id] for c in tl.clips if c.kind == "video" and c.media_id in srcs), None)
    src_wh = (first_video.info.get("width", 1920), first_video.info.get("height", 1080)) if first_video else None
    src_fps = first_video.info.get("fps") if first_video else None
    spec = ExportManager().spec(settings, src_wh, src_fps, preview=preview, x264_preset=s.x264_preset)
    work = s.dir("work") / job.id
    st = get_storage()
    key = st.new_key("exports", spec.ext)
    out_path = st.path_for(key)
    renderer = FFmpegRenderer(settings, spec, work, srcs, s.dir("assets"),
                              on_progress=lambda f_, msg: ctx.progress(f_, "Rendering", msg),
                              should_cancel=ctx.cancelled, x264_preset=s.x264_preset, preview=preview)
    try:
        info = renderer.render(tl, out_path)
    except Exception:
        st.delete(key)
        raise
    finally:
        renderer.cleanup()
    thumb_key = st.new_key("thumbs", "jpg")
    try:
        ThumbnailGenerator().frame_at(out_path, st.path_for(thumb_key), info["duration"] * 0.4, width=480)
    except Exception:
        log.warning("thumbnail failed for export", exc_info=True)
        thumb_key = None
    label = "Preview" if preview else PRESETS[settings.preset]["label"]
    ex = Export(owner_id=p.owner_id, project_id=p.id, job_id=job.id, kind="preview" if preview else "video",
                name=clean_display_name(f"{p.name} - {label}.{spec.ext}"), storage_key=key, thumb_key=thumb_key,
                format=info["format"], width=info["width"], height=info["height"], duration=info["duration"],
                size_bytes=info["size_bytes"],
                settings={"preset": settings.preset, "aspect": settings.aspect, "resolution": settings.resolution,
                          "fps": info["fps"], "quality": settings.quality, "format": info["format"],
                          "clip_count": len(tl.clips), "clip_boundaries": info["clip_boundaries"]})
    db.add(ex)
    db.flush()
    return {"export_id": ex.id, **{k: info[k] for k in ("width", "height", "duration", "format", "size_bytes")},
            "notes": tl.notes}


# --------------------------------------------------------------------------- job entry points
def run_job(job_id: str) -> None:
    """Execute one job. Safe to call from a thread or a Celery worker."""
    from datetime import datetime

    from .ffmpeg import Cancelled, FFmpegError

    ctx = JobContext(job_id)
    with session_scope() as db:
        job = db.get(Job, job_id)
        if job is None or job.status not in ("queued",):
            return
        if job.cancel_requested:
            job.status = "cancelled"
            job.finished_at = datetime.now(UTC)
            return
        job.status = "running"
        job.attempts += 1
        job.started_at = datetime.now(UTC)
        job.error = None
    try:
        with session_scope() as db:
            job = db.get(Job, job_id)
            p = db.get(Project, job.project_id) if job.project_id else None
            if p is None or p.owner_id != job.owner_id:
                raise PipelineError("Project not found")
            result: dict[str, Any] = {}
            if job.kind in ("auto_edit", "analyze"):
                tl = build_auto_timeline(db, p, ctx)
                result.update({"clip_count": len(tl.clips), "duration": round(tl.duration(), 3), "notes": tl.notes})
                db.commit()
            if job.kind == "render" or (job.kind == "auto_edit" and job.params.get("render", True)):
                ctx.span(0.45 if job.kind == "auto_edit" else 0.0, 1.0)
                ctx.progress(0.0, "Rendering", "Starting render", force=True)
                result.update(render_project(db, p, job, ctx, preview=bool(job.params.get("preview"))))
            job = db.get(Job, job_id)
            job.status = "done"
            job.progress = 1.0
            job.stage = "Done"
            job.message = "Finished"
            job.eta_seconds = 0
            job.result = result
            job.finished_at = datetime.now(UTC)
    except Cancelled:
        _fail(job_id, "cancelled", "Cancelled by user")
    except PipelineError as e:
        _fail(job_id, "failed", str(e))
    except FFmpegError as e:
        log.exception("FFmpeg failed in job %s", job_id)
        _fail(job_id, "failed", f"Video processing failed: {str(e)[-500:]}")
    except Exception as e:  # noqa: BLE001 - report every failure to the user
        log.exception("Job %s crashed", job_id)
        _fail(job_id, "failed", f"Unexpected error: {type(e).__name__}: {e}"[:600])
    finally:
        shutil.rmtree(get_settings().dir("work") / job_id, ignore_errors=True)


def _fail(job_id: str, status: str, message: str) -> None:
    from datetime import datetime
    with session_scope() as db:
        job = db.get(Job, job_id)
        if job:
            job.status = status
            job.error = message if status == "failed" else None
            job.message = message
            job.finished_at = datetime.now(UTC)
            job.eta_seconds = None
