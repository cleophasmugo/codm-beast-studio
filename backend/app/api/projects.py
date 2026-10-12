from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.security import clean_display_name, current_owner
from ..db.models import Export, Job, Media, Project, TimelineRevision
from ..db.session import get_db
from ..jobs.runner import dispatch
from ..presets import preset_settings
from ..schemas import (
    AutoEditRequest,
    JobOut,
    ProjectCreate,
    ProjectOut,
    ProjectSettings,
    ProjectUpdate,
    QuickMontageRequest,
    RenderRequest,
    RevisionOut,
    Timeline,
    TimelineSave,
)
from ..services.auto_color import ColorCorrection
from ..services.effects import EffectsComposer
from ..services.thumbnails import ThumbnailGenerator
from ..storage.base import get_storage
from .deps import get_media, get_project, job_out, project_out

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _check_media(db: Session, ids: list[str], owner: str) -> list[str]:
    out = []
    for i in ids:
        get_media(db, i, owner)
        if i not in out:
            out.append(i)
    return out


def _check_settings(db: Session, s: ProjectSettings, owner: str) -> None:
    if s.music_id:
        m = get_media(db, s.music_id, owner)
        if m.kind != "audio":
            raise HTTPException(422, "music_id must be an audio file")
    if s.watermark_media_id:
        m = get_media(db, s.watermark_media_id, owner)
        if m.kind not in ("image", "sticker"):
            raise HTTPException(422, "watermark_media_id must be an image")


def _check_timeline(db: Session, tl: Timeline, owner: str) -> Timeline:
    for c in tl.clips:
        if c.kind in ("video", "image"):
            if not c.media_id:
                raise HTTPException(422, f"Clip {c.id} needs a media_id")
            m = get_media(db, c.media_id, owner)
            if c.kind == "video":
                dur = float(m.info.get("duration", 0))
                if m.kind != "video":
                    raise HTTPException(422, f"Clip {c.id}: media is not a video")
                if not (0 <= c.start < c.end <= dur + 0.05):
                    raise HTTPException(422, f"Clip {c.id}: in/out points must be inside 0–{dur:.2f}s")
            elif m.kind not in ("image", "sticker"):
                raise HTTPException(422, f"Clip {c.id}: media is not an image")
            elif c.duration <= 0:
                raise HTTPException(422, f"Clip {c.id}: image clips need a duration")
    for o in tl.overlays:
        if o.media_id:
            get_media(db, o.media_id, owner)
        if o.end <= o.start:
            raise HTTPException(422, f"Overlay {o.id}: end must be after start")
    if tl.music:
        if get_media(db, tl.music.media_id, owner).kind != "audio":
            raise HTTPException(422, "Timeline music must be an audio file")
    return tl


def _new_job(db: Session, owner: str, project_id: str, kind: str, params: dict) -> Job:
    running = db.scalars(select(Job).where(Job.project_id == project_id, Job.status.in_(("queued", "running")))).first()
    if running:
        raise HTTPException(409, f"This project already has a {running.kind.replace('_', ' ')} job in progress")
    job = Job(owner_id=owner, project_id=project_id, kind=kind, params=params, message="Waiting to start")
    db.add(job)
    db.commit()
    dispatch(job.id)
    return job


@router.post("", response_model=ProjectOut, status_code=201)
def create(body: ProjectCreate, owner: str = Depends(current_owner), db: Session = Depends(get_db)) -> ProjectOut:
    settings = body.settings or ProjectSettings()
    if body.preset:
        settings = preset_settings(body.preset, settings)
    _check_settings(db, settings, owner)
    p = Project(owner_id=owner, name=clean_display_name(body.name, "My Montage"),
                media_ids=_check_media(db, body.media_ids, owner), settings=settings.model_dump(mode="json"))
    db.add(p)
    db.flush()
    return project_out(db, p)


@router.get("", response_model=list[ProjectOut])
def list_projects(owner: str = Depends(current_owner), db: Session = Depends(get_db)) -> list[ProjectOut]:
    rows = db.scalars(select(Project).where(Project.owner_id == owner).order_by(Project.updated_at.desc())).all()
    return [project_out(db, p) for p in rows]


@router.get("/{project_id}", response_model=ProjectOut)
def get_one(project_id: str, owner: str = Depends(current_owner), db: Session = Depends(get_db)) -> ProjectOut:
    return project_out(db, get_project(db, project_id, owner))


@router.patch("/{project_id}", response_model=ProjectOut, summary="Rename, change media, or change settings")
def update(project_id: str, body: ProjectUpdate, owner: str = Depends(current_owner),
           db: Session = Depends(get_db)) -> ProjectOut:
    p = get_project(db, project_id, owner)
    if body.name is not None:
        p.name = clean_display_name(body.name, "My Montage")
    if body.media_ids is not None:
        p.media_ids = _check_media(db, body.media_ids, owner)
    if body.settings is not None:
        _check_settings(db, body.settings, owner)
        p.settings = body.settings.model_dump(mode="json")
    db.flush()
    return project_out(db, p)


@router.post("/{project_id}/apply-preset/{preset}", response_model=ProjectOut,
             summary="Replace style settings with a preset (keeps music, titles and export choices)")
def apply_preset(project_id: str, preset: str, owner: str = Depends(current_owner),
                 db: Session = Depends(get_db)) -> ProjectOut:
    p = get_project(db, project_id, owner)
    from ..presets import PRESETS
    if preset not in PRESETS:
        raise HTTPException(404, "Unknown preset")
    p.settings = preset_settings(preset, ProjectSettings.model_validate(p.settings or {})).model_dump(mode="json")
    db.flush()
    return project_out(db, p)


@router.delete("/{project_id}", status_code=204, summary="Delete a project and its exports")
def delete(project_id: str, owner: str = Depends(current_owner), db: Session = Depends(get_db)) -> None:
    p = get_project(db, project_id, owner)
    for j in db.scalars(select(Job).where(Job.project_id == p.id, Job.status.in_(("queued", "running")))).all():
        j.cancel_requested = True
    st = get_storage()
    for e in db.scalars(select(Export).where(Export.project_id == p.id)).all():
        st.delete(e.storage_key)
        st.delete(e.thumb_key)
        db.delete(e)
    db.delete(p)


# ---------------------------------------------------------------- timeline + history
@router.put("/{project_id}/timeline", response_model=ProjectOut, summary="Save a manually edited timeline")
def save_timeline(project_id: str, body: TimelineSave, owner: str = Depends(current_owner),
                  db: Session = Depends(get_db)) -> ProjectOut:
    from ..services.pipeline import save_timeline as _save
    p = get_project(db, project_id, owner)
    tl = _check_timeline(db, body.timeline, owner)
    _save(db, p, tl, body.note)
    db.flush()
    return project_out(db, p)


@router.get("/{project_id}/revisions", response_model=list[RevisionOut], summary="Timeline edit history")
def revisions(project_id: str, owner: str = Depends(current_owner), db: Session = Depends(get_db)) -> list[RevisionOut]:
    p = get_project(db, project_id, owner)
    rows = db.scalars(select(TimelineRevision).where(TimelineRevision.project_id == p.id)
                      .order_by(TimelineRevision.created_at.desc())).all()
    out = []
    for r in rows:
        tl = Timeline.model_validate(r.timeline)
        out.append(RevisionOut(id=r.id, note=r.note, created_at=r.created_at, clip_count=len(tl.clips),
                               duration=round(tl.duration(), 3)))
    return out


@router.post("/{project_id}/revisions/{revision_id}/restore", response_model=ProjectOut)
def restore(project_id: str, revision_id: str, owner: str = Depends(current_owner),
            db: Session = Depends(get_db)) -> ProjectOut:
    from ..services.pipeline import save_timeline as _save
    p = get_project(db, project_id, owner)
    r = db.get(TimelineRevision, revision_id)
    if not r or r.project_id != p.id:
        raise HTTPException(404, "Revision not found")
    _save(db, p, Timeline.model_validate(r.timeline), f"Restored: {r.note}"[:200])
    db.flush()
    return project_out(db, p)


@router.get("/{project_id}/highlights", summary="Detected highlight candidates, scene cuts and quiet sections")
def highlights(project_id: str, owner: str = Depends(current_owner), db: Session = Depends(get_db)) -> dict:
    p = get_project(db, project_id, owner)
    if not p.highlights:
        raise HTTPException(404, "No analysis yet. Run Auto Edit first.")
    return p.highlights


# ---------------------------------------------------------------- jobs
@router.post("/{project_id}/auto-edit", response_model=JobOut, status_code=202,
             summary="Analyse footage, build a montage timeline and (by default) render it")
def auto_edit(project_id: str, body: AutoEditRequest | None = None, owner: str = Depends(current_owner),
              db: Session = Depends(get_db)) -> JobOut:
    body = body or AutoEditRequest()
    p = get_project(db, project_id, owner)
    if body.settings is not None:
        _check_settings(db, body.settings, owner)
        p.settings = body.settings.model_dump(mode="json")
    if not p.media_ids:
        raise HTTPException(422, "Add gameplay videos or screenshots to the project first")
    return job_out(_new_job(db, owner, p.id, "auto_edit", {"render": body.render}))


@router.post("/{project_id}/render", response_model=JobOut, status_code=202,
             summary="Render the current timeline (preview=true for a fast low-res preview)")
def render(project_id: str, body: RenderRequest | None = None, owner: str = Depends(current_owner),
           db: Session = Depends(get_db)) -> JobOut:
    body = body or RenderRequest()
    p = get_project(db, project_id, owner)
    if not p.timeline:
        raise HTTPException(422, "Run Auto Edit first to create a timeline")
    return job_out(_new_job(db, owner, p.id, "render", {"preview": body.preview}))


class CompareRequest(BaseModel):
    media_id: str
    t: float = Field(0.0, ge=0)


@router.post("/{project_id}/compare", summary="Before/after still frames using the project's real FFmpeg grade")
def compare(project_id: str, body: CompareRequest, owner: str = Depends(current_owner),
            db: Session = Depends(get_db)) -> dict:
    from ..services.pipeline import analyze_video
    p = get_project(db, project_id, owner)
    m = get_media(db, body.media_id, owner)
    if m.kind != "video":
        raise HTTPException(400, "Choose a video")
    if not (m.analysis or {}).get("auto_color"):
        analyze_video(db, m)
    settings = ProjectSettings.model_validate(p.settings or {})
    ac = m.analysis["auto_color"]
    corr = ColorCorrection(**{k: ac[k] for k in ("brightness", "contrast", "saturation", "gamma", "sharpen", "denoise")})
    chain = EffectsComposer(settings).grade(corr)
    if settings.effects.vignette:
        chain.append("vignette=angle=0.5")
    t = min(body.t, max(0.0, float(m.info.get("duration", 0)) - 0.05))
    st = get_storage()
    th = ThumbnailGenerator()
    before = st.new_key("previews", "jpg")
    after = st.new_key("previews", "jpg")
    src = st.path_for(m.storage_key)
    th.frame_at(src, st.path_for(before), t)
    th.frame_at(src, st.path_for(after), t, vf=",".join(chain) if chain else None)
    return {"before_url": f"/api/previews/{before.split('/')[-1]}", "after_url": f"/api/previews/{after.split('/')[-1]}",
            "filters": chain, "auto_color": ac}


# ---------------------------------------------------------------- one click
quick_router = APIRouter(prefix="/api/montage", tags=["auto edit"])


@quick_router.post("/quick", response_model=JobOut, status_code=202,
                   summary="One click: new project from media, auto-edit and render")
def quick(body: QuickMontageRequest, owner: str = Depends(current_owner), db: Session = Depends(get_db)) -> JobOut:
    ids = _check_media(db, body.media_ids, owner)
    kinds = {get_media(db, i, owner).kind for i in ids}
    if not kinds & {"video", "image"}:
        raise HTTPException(422, "Include at least one gameplay video or screenshot")
    music = body.music_id
    if music is None:  # pick the preset's library track so the montage has a beat
        from ..services.maintenance import LIBRARY_OWNER
        want = {"cinematic": "Cinematic Rise", "neon": "Neon Drive", "smooth": "Neon Drive"}.get(body.preset, "Beast Pulse")
        lib = db.scalars(select(Media).where(Media.owner_id == LIBRARY_OWNER, Media.kind == "audio")).all()
        music = next((m.id for m in lib if m.name.startswith(want)), lib[0].id if lib else None)
    settings = preset_settings(body.preset, target_duration=body.target_duration, music_id=music)
    if body.target_duration is None and "target_duration" in body.model_fields_set:
        settings.target_duration = None
    _check_settings(db, settings, owner)
    p = Project(owner_id=owner, name=clean_display_name(body.name, "My Montage"), media_ids=ids,
                settings=settings.model_dump(mode="json"))
    db.add(p)
    db.flush()
    return job_out(_new_job(db, owner, p.id, "auto_edit", {"render": True}))
