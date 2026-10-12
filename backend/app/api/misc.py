"""Jobs, exports, Image Studio and system endpoints."""

from __future__ import annotations

import io
import re
import shutil
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.security import clean_display_name, current_owner
from ..db.models import Export, Job, Media
from ..db.session import get_db
from ..jobs.runner import dispatch
from ..presets import preset_list
from ..schemas import (
    AddToMontageRequest,
    Clip,
    ExportOut,
    ImageEdit,
    ImageRenderRequest,
    JobOut,
    MediaOut,
    ProjectOut,
    ProjectSettings,
    Timeline,
)
from ..services.effects import LOOKS
from ..services.export import ExportManager
from ..services.ffmpeg import ffmpeg_version
from ..services.image_studio import analyze_image, apply_edit, auto_enhance_params
from ..services.maintenance import cleanup_expired, dir_size
from ..storage.base import get_storage
from .deps import (
    export_out,
    get_export,
    get_job,
    get_media,
    get_project,
    job_out,
    media_out,
    project_out,
)
from .media import _file, ingest_file

# ---------------------------------------------------------------- jobs
jobs = APIRouter(prefix="/api/jobs", tags=["jobs"])


@jobs.get("", response_model=list[JobOut])
def list_jobs(project_id: str | None = None, limit: int = Query(50, ge=1, le=200),
              owner: str = Depends(current_owner), db: Session = Depends(get_db)) -> list[JobOut]:
    q = select(Job).where(Job.owner_id == owner).order_by(Job.created_at.desc()).limit(limit)
    if project_id:
        q = q.where(Job.project_id == project_id)
    return [job_out(j) for j in db.scalars(q).all()]


@jobs.get("/{job_id}", response_model=JobOut)
def get_one(job_id: str, owner: str = Depends(current_owner), db: Session = Depends(get_db)) -> JobOut:
    return job_out(get_job(db, job_id, owner))


@jobs.post("/{job_id}/cancel", response_model=JobOut)
def cancel(job_id: str, owner: str = Depends(current_owner), db: Session = Depends(get_db)) -> JobOut:
    j = get_job(db, job_id, owner)
    if j.status in ("queued", "running"):
        j.cancel_requested = True
        if j.status == "queued":
            j.status = "cancelled"
            j.message = "Cancelled by user"
            j.finished_at = datetime.now(UTC)
    return job_out(j)


@jobs.post("/{job_id}/retry", response_model=JobOut, status_code=202, summary="Run a failed or cancelled job again")
def retry(job_id: str, owner: str = Depends(current_owner), db: Session = Depends(get_db)) -> JobOut:
    j = get_job(db, job_id, owner)
    if j.status not in ("failed", "cancelled"):
        raise HTTPException(409, "Only failed or cancelled jobs can be retried")
    busy = db.scalars(select(Job).where(Job.project_id == j.project_id, Job.status.in_(("queued", "running")))).first()
    if busy:
        raise HTTPException(409, "This project already has a job in progress")
    j.status, j.progress, j.stage, j.message = "queued", 0.0, "", "Waiting to start (retry)"
    j.error, j.cancel_requested, j.result, j.finished_at, j.eta_seconds = None, False, None, None, None
    db.commit()
    dispatch(j.id)
    return job_out(j)


# ---------------------------------------------------------------- exports
exports = APIRouter(prefix="/api/exports", tags=["exports"])


@exports.get("", response_model=list[ExportOut], summary="Export history")
def list_exports(project_id: str | None = None, owner: str = Depends(current_owner),
                 db: Session = Depends(get_db)) -> list[ExportOut]:
    q = select(Export).where(Export.owner_id == owner).order_by(Export.created_at.desc())
    if project_id:
        q = q.where(Export.project_id == project_id)
    return [export_out(e) for e in db.scalars(q).all()]


@exports.get("/{export_id}", response_model=ExportOut)
def get_export_one(export_id: str, owner: str = Depends(current_owner), db: Session = Depends(get_db)) -> ExportOut:
    return export_out(get_export(db, export_id, owner))


MIMES = {"mp4_h264": "video/mp4", "mp4_h265": "video/mp4", "webm_vp9": "video/webm", "png": "image/png",
         "jpeg": "image/jpeg"}


@exports.get("/{export_id}/file", summary="Stream for in-browser preview")
def export_file(export_id: str, owner: str = Depends(current_owner), db: Session = Depends(get_db)) -> FileResponse:
    e = get_export(db, export_id, owner)
    return _file(e.storage_key, MIMES.get(e.format))


@exports.get("/{export_id}/download", summary="Download the finished file")
def export_download(export_id: str, owner: str = Depends(current_owner), db: Session = Depends(get_db)) -> FileResponse:
    e = get_export(db, export_id, owner)
    return _file(e.storage_key, MIMES.get(e.format), download_name=e.name)


@exports.get("/{export_id}/thumb")
def export_thumb(export_id: str, owner: str = Depends(current_owner), db: Session = Depends(get_db)) -> FileResponse:
    e = get_export(db, export_id, owner)
    return _file(e.thumb_key or (e.storage_key if e.kind == "image" else None))


@exports.delete("/{export_id}", status_code=204)
def delete_export(export_id: str, owner: str = Depends(current_owner), db: Session = Depends(get_db)) -> None:
    e = get_export(db, export_id, owner)
    st = get_storage()
    st.delete(e.storage_key)
    if e.thumb_key != e.storage_key:
        st.delete(e.thumb_key)
    db.delete(e)


# ---------------------------------------------------------------- image studio
images = APIRouter(prefix="/api/images", tags=["image studio"])


def _image_media(db: Session, media_id: str, owner: str) -> Media:
    m = get_media(db, media_id, owner)
    if m.kind not in ("image", "sticker"):
        raise HTTPException(400, "Choose an image or screenshot")
    return m


def _sticker_paths(db: Session, edit: ImageEdit, owner: str) -> dict:
    st = get_storage()
    out = {}
    for layer in edit.layers:
        if layer.type == "sticker" and layer.media_id:
            m = get_media(db, layer.media_id, owner)
            if m.kind not in ("image", "sticker"):
                raise HTTPException(422, "Sticker layers must use an image")
            out[m.id] = st.path_for(m.storage_key)
    return out


@images.post("/{media_id}/analyze", summary="Measure an image and suggest Auto Enhance settings")
def analyze(media_id: str, owner: str = Depends(current_owner), db: Session = Depends(get_db)) -> dict:
    from PIL import Image
    m = _image_media(db, media_id, owner)
    with Image.open(get_storage().path_for(m.storage_key)) as im:
        stats = analyze_image(im)
    return {"stats": stats, "suggested": auto_enhance_params(stats)}


@images.post("/{media_id}/preview", summary="Render an edit and return a JPEG preview (not saved)")
def preview(media_id: str, edit: ImageEdit, owner: str = Depends(current_owner), db: Session = Depends(get_db)) -> Response:
    m = _image_media(db, media_id, owner)
    edit = edit.model_copy(update={"max_size": min(edit.max_size, 1280)})
    im, info = apply_edit(get_storage().path_for(m.storage_key), edit, _sticker_paths(db, edit, owner))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    headers = {"X-Auto-Reasons": "; ".join(info.get("auto", {}).get("reasons", []))[:500]}
    return Response(buf.getvalue(), media_type="image/jpeg", headers=headers)


@images.post("/{media_id}/render", summary="Render an edit at full size and save it (PNG or JPEG)")
def render_image(media_id: str, body: ImageRenderRequest, owner: str = Depends(current_owner),
                 db: Session = Depends(get_db)) -> dict:
    m = _image_media(db, media_id, owner)
    im, info = apply_edit(get_storage().path_for(m.storage_key), body.edit, _sticker_paths(db, body.edit, owner))
    ext = "png" if body.format == "png" else "jpg"
    tmp = get_settings().dir("work") / f"img_{uuid.uuid4().hex}.{ext}"
    if body.format == "png":
        im.save(tmp, "PNG", optimize=True)
    else:
        im.save(tmp, "JPEG", quality=body.quality, optimize=True)
    name = clean_display_name(body.name or f"{m.name} enhanced")
    new = ingest_file(db, owner, tmp, f"{name}.{ext}", folder=m.folder, source="image_studio", name=name)
    st = get_storage()
    # The export keeps its own copy, so deleting the export or the media never breaks the other.
    ex_key = st.new_key("exports", ext)
    shutil.copyfile(st.path_for(new.storage_key), st.path_for(ex_key))
    ex = Export(owner_id=owner, kind="image", name=f"{name}.{ext}", storage_key=ex_key,
                thumb_key=None, format=body.format, width=im.width, height=im.height,
                size_bytes=new.size_bytes, settings={"source_media_id": m.id, "edit": body.edit.model_dump(mode="json")})
    db.add(ex)
    db.flush()
    return {"media": media_out(new).model_dump(mode="json"), "export": export_out(ex).model_dump(mode="json"),
            "auto": info.get("auto")}


@images.post("/add-to-montage", response_model=ProjectOut,
             summary="Add a screenshot to a project's montage as a timed scene")
def add_to_montage(body: AddToMontageRequest, owner: str = Depends(current_owner),
                   db: Session = Depends(get_db)) -> ProjectOut:
    from ..services.pipeline import save_timeline
    p = get_project(db, body.project_id, owner)
    _image_media(db, body.media_id, owner)
    if body.media_id not in (p.media_ids or []):
        p.media_ids = [*(p.media_ids or []), body.media_id]
    if p.timeline:
        tl = Timeline.model_validate(p.timeline)
        dur = body.duration
        if body.snap_to_beats and tl.bpm:
            beat = 60.0 / tl.bpm
            dur = max(beat, round(dur / beat) * beat)
        clip = Clip(id=uuid.uuid4().hex[:10], kind="image", media_id=body.media_id, duration=round(dur, 3),
                    transition=body.transition, motion=body.motion)
        pos = len(tl.clips) if body.position is None else max(0, min(body.position, len(tl.clips)))
        tl.clips.insert(pos, clip)
        save_timeline(db, p, tl, "Added screenshot scene")
    else:  # no timeline yet: the screenshot is used by the next Auto Edit
        s = ProjectSettings.model_validate(p.settings or {})
        s.image_duration = body.duration
        p.settings = s.model_dump(mode="json")
    db.flush()
    return project_out(db, p)


# ---------------------------------------------------------------- system
system = APIRouter(prefix="/api", tags=["system"])


@system.get("/health", summary="Liveness check (no auth)")
def health() -> dict:
    return {"status": "ok"}


@system.get("/system", summary="Capabilities, limits and storage usage")
def info(owner: str = Depends(current_owner)) -> dict:
    s = get_settings()
    st = get_storage()
    usage = st.usage_bytes()
    return {
        "version": __import__("app").__version__,
        "ffmpeg": ffmpeg_version(),
        "formats": ExportManager().supported_formats(),
        "presets": preset_list(),
        "looks": list(LOOKS.keys()),
        "job_backend": "celery" if s.broker_url else "thread",
        "auth_required": bool(s.api_token),
        "limits": {"max_upload_mb": s.max_upload_mb, "max_video_minutes": s.max_video_minutes,
                   "max_audio_minutes": s.max_audio_minutes, "retention_days": s.retention_days},
        "storage": {"total_bytes": sum(usage.values()), "by_area": usage,
                    "work_bytes": dir_size(s.dir("work"))},
        "detectors": [d for d in s.detector_plugins.split(",") if d.strip()],
    }


@system.get("/presets", summary="Auto-edit presets")
def presets() -> list[dict]:
    return preset_list()


@system.post("/system/cleanup", summary="Apply the retention policy now")
def cleanup(owner: str = Depends(current_owner)) -> dict:
    return cleanup_expired()


_PREVIEW_NAME = re.compile(r"^[0-9a-f]{32}\.jpg$")


@system.get("/previews/{name}", summary="Before/after comparison frames")
def preview_file(name: str, owner: str = Depends(current_owner)) -> FileResponse:
    if not _PREVIEW_NAME.match(name):
        raise HTTPException(404, "Not found")
    return _file(f"previews/{name}", "image/jpeg")


__all__ = ["jobs", "exports", "images", "system", "MediaOut"]
