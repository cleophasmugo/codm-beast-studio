from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.security import clean_display_name, current_owner
from ..db.models import Media, Project
from ..db.session import get_db
from ..schemas import MediaOut, MediaUpdate
from ..services.maintenance import LIBRARY_OWNER, delete_media_files
from ..services.media_inspector import ALLOWED_EXT, InspectionError, MediaInspector
from ..services.thumbnails import ThumbnailGenerator
from ..storage.base import get_storage
from .deps import get_media, media_out

router = APIRouter(prefix="/api/media", tags=["media"])
log = logging.getLogger(__name__)
CHUNK = 1024 * 1024


async def _save_upload(up: UploadFile, limit_bytes: int) -> Path:
    tmp = get_settings().dir("work") / f"upload_{uuid.uuid4().hex}"
    size = 0
    with open(tmp, "wb") as fh:
        while chunk := await up.read(CHUNK):
            size += len(chunk)
            if size > limit_bytes:
                fh.close()
                tmp.unlink(missing_ok=True)
                raise HTTPException(413, f"{clean_display_name(up.filename or 'file')} is larger than the "
                                         f"{limit_bytes // (1024 * 1024)} MB upload limit")
            fh.write(chunk)
    if size == 0:
        tmp.unlink(missing_ok=True)
        raise HTTPException(400, "Empty file")
    return tmp


def ingest_file(db: Session, owner: str, tmp: Path, filename: str, folder: str = "", source: str = "upload",
                name: str | None = None) -> Media:
    """Validate a local file, move it into storage, make thumbnails and create the Media row."""
    s = get_settings()
    ext = Path(filename).suffix.lower()
    try:
        ins = MediaInspector().inspect(tmp, filename)
    except InspectionError as e:
        tmp.unlink(missing_ok=True)
        raise HTTPException(415, str(e)) from e
    dur = float(ins.info.get("duration") or 0)
    if ins.kind == "video" and dur > s.max_video_minutes * 60:
        tmp.unlink(missing_ok=True)
        raise HTTPException(413, f"Video is longer than the {s.max_video_minutes:g}-minute limit")
    if ins.kind == "audio" and dur > s.max_audio_minutes * 60:
        tmp.unlink(missing_ok=True)
        raise HTTPException(413, f"Audio is longer than the {s.max_audio_minutes:g}-minute limit")
    if ins.kind in ("image", "sticker") and ins.info.get("megapixels", 0) > s.max_image_megapixels:
        tmp.unlink(missing_ok=True)
        raise HTTPException(413, f"Image is larger than {s.max_image_megapixels:g} megapixels")
    st = get_storage()
    key = st.new_key("uploads", ext.lstrip("."))
    size = tmp.stat().st_size
    st.put_file(tmp, key)
    path = st.path_for(key)
    thumbs = ThumbnailGenerator()
    thumb_key = sheet_key = None
    try:
        if ins.kind == "video":
            thumb_key = st.new_key("thumbs", "jpg")
            thumbs.video_thumb(path, st.path_for(thumb_key), dur)
            sheet_key = st.new_key("thumbs", "jpg")
            thumbs.contact_sheet(path, st.path_for(sheet_key), dur)
        elif ins.kind == "audio":
            thumb_key = st.new_key("thumbs", "png")
            thumbs.waveform(path, st.path_for(thumb_key))
        else:
            thumb_key = st.new_key("thumbs", "png" if ins.kind == "sticker" else "jpg")
            thumbs.image_thumb(path, st.path_for(thumb_key))
    except Exception:  # thumbnails are nice-to-have
        log.warning("Thumbnail generation failed for %s", filename, exc_info=True)
    m = Media(owner_id=owner, kind=ins.kind, name=clean_display_name(name or Path(filename).stem),
              folder=clean_display_name(folder, fallback="")[:100], original_filename=clean_display_name(filename),
              storage_key=key, thumb_key=thumb_key, contact_sheet_key=sheet_key, mime=ins.mime, size_bytes=size,
              source=source, info=ins.info)
    db.add(m)
    db.flush()
    return m


@router.post("", response_model=list[MediaOut], summary="Upload one or more media files")
async def upload(files: list[UploadFile] = File(...), folder: str = Form(""),
                 owner: str = Depends(current_owner), db: Session = Depends(get_db)) -> list[MediaOut]:
    limit = get_settings().max_upload_mb * 1024 * 1024
    out = []
    for up in files:
        fname = clean_display_name(up.filename or "upload")
        if Path(fname).suffix.lower() not in ALLOWED_EXT:
            raise HTTPException(415, f"{fname}: unsupported file type. Allowed: {', '.join(sorted(ALLOWED_EXT))}")
        tmp = await _save_upload(up, limit)
        out.append(media_out(ingest_file(db, owner, tmp, fname, folder)))
    return out


@router.get("", response_model=list[MediaOut], summary="List media (yours plus the built-in library)")
def list_media(kind: str | None = Query(None, pattern="^(video|audio|image|sticker)$"),
               folder: str | None = None, include_library: bool = True,
               owner: str = Depends(current_owner), db: Session = Depends(get_db)) -> list[MediaOut]:
    owners = [owner, LIBRARY_OWNER] if include_library else [owner]
    q = select(Media).where(Media.owner_id.in_(owners)).order_by(Media.created_at.desc())
    if kind:
        q = q.where(Media.kind == kind)
    if folder is not None:
        q = q.where(Media.folder == folder)
    return [media_out(m) for m in db.scalars(q).all()]


@router.get("/{media_id}", response_model=MediaOut)
def get_one(media_id: str, owner: str = Depends(current_owner), db: Session = Depends(get_db)) -> MediaOut:
    return media_out(get_media(db, media_id, owner))


@router.patch("/{media_id}", response_model=MediaOut, summary="Rename or move to a folder")
def update(media_id: str, body: MediaUpdate, owner: str = Depends(current_owner),
           db: Session = Depends(get_db)) -> MediaOut:
    m = get_media(db, media_id, owner, writable=True)
    if body.name is not None:
        m.name = clean_display_name(body.name)
    if body.folder is not None:
        m.folder = clean_display_name(body.folder, fallback="")[:100]
    return media_out(m)


@router.delete("/{media_id}", status_code=204, summary="Delete media and its files")
def delete(media_id: str, owner: str = Depends(current_owner), db: Session = Depends(get_db)) -> None:
    m = get_media(db, media_id, owner, writable=True)
    for p in db.scalars(select(Project).where(Project.owner_id == owner)).all():
        if media_id in (p.media_ids or []):
            p.media_ids = [i for i in p.media_ids if i != media_id]
    delete_media_files(m)
    db.delete(m)


def _file(key: str | None, mime: str | None = None, download_name: str | None = None) -> FileResponse:
    st = get_storage()
    if not key or not st.exists(key):
        raise HTTPException(404, "File not found")
    return FileResponse(st.path_for(key), media_type=mime, filename=download_name,
                        content_disposition_type="attachment" if download_name else "inline")


@router.get("/{media_id}/file", summary="Stream the original file (supports Range for seeking)")
def file(media_id: str, owner: str = Depends(current_owner), db: Session = Depends(get_db)) -> FileResponse:
    m = get_media(db, media_id, owner)
    return _file(m.storage_key, m.mime)


@router.get("/{media_id}/thumb")
def thumb(media_id: str, owner: str = Depends(current_owner), db: Session = Depends(get_db)) -> FileResponse:
    m = get_media(db, media_id, owner)
    return _file(m.thumb_key)


@router.get("/{media_id}/contact-sheet")
def contact_sheet(media_id: str, owner: str = Depends(current_owner), db: Session = Depends(get_db)) -> FileResponse:
    m = get_media(db, media_id, owner)
    return _file(m.contact_sheet_key)


@router.get("/{media_id}/frame", summary="A still frame from a video at time t (seconds)")
def frame(media_id: str, t: float = Query(0, ge=0), owner: str = Depends(current_owner),
          db: Session = Depends(get_db)) -> FileResponse:
    m = get_media(db, media_id, owner)
    if m.kind != "video":
        raise HTTPException(400, "Not a video")
    t = min(t, max(0.0, float(m.info.get("duration", 0)) - 0.05))
    st = get_storage()
    key = f"previews/frame_{m.id}_{int(t * 1000)}.jpg"
    if not st.exists(key):
        ThumbnailGenerator().frame_at(st.path_for(m.storage_key), st.path_for(key), t, width=640)
    return _file(key, "image/jpeg")
