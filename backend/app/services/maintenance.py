"""Startup housekeeping, the built-in asset library, and retention cleanup."""

from __future__ import annotations

import logging
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from ..core.config import get_settings
from ..db.models import Export, Job, Media
from ..db.session import session_scope
from ..storage.base import get_storage
from .ffmpeg import run_ffmpeg_simple
from .graphics import BUILTIN_STICKERS
from .media_inspector import MediaInspector
from .sound_library import LIBRARY_TRACKS, LICENSE, generate_library_track
from .thumbnails import ThumbnailGenerator

log = logging.getLogger(__name__)
LIBRARY_OWNER = "__library__"


def recover_interrupted_jobs() -> int:
    """Jobs left 'running' by a crashed/restarted thread-mode server can never finish: mark them failed."""
    if get_settings().broker_url:
        return 0  # Celery redelivers unacknowledged tasks itself
    n = 0
    with session_scope() as db:
        for job in db.scalars(select(Job).where(Job.status.in_(("running", "queued")))).all():
            job.status = "failed"
            job.error = "The server restarted while this job was running. Press Retry to run it again."
            job.finished_at = datetime.now(UTC)
            n += 1
    return n


def ensure_library() -> None:
    """Create the royalty-free music tracks and stickers once."""
    st = get_storage()
    thumbs = ThumbnailGenerator()
    with session_scope() as db:
        existing = {m.name for m in db.scalars(select(Media).where(Media.owner_id == LIBRARY_OWNER)).all()}
        for kind, (title, desc) in LIBRARY_TRACKS.items():
            if title in existing:
                continue
            tmp = get_settings().dir("work") / f"lib_{kind}.wav"
            generate_library_track(kind, tmp)
            key = st.new_key("library", "m4a")
            run_ffmpeg_simple(["-i", tmp, "-c:a", "aac", "-b:a", "192k", st.path_for(key)])
            tmp.unlink(missing_ok=True)
            path = st.path_for(key)
            ins = MediaInspector().inspect(path, path.name)
            thumb = st.new_key("thumbs", "png")
            try:
                thumbs.waveform(path, st.path_for(thumb))
            except Exception:
                thumb = None
            db.add(Media(owner_id=LIBRARY_OWNER, kind="audio", name=title, folder="Library music",
                         original_filename=f"{kind}.m4a", storage_key=key, thumb_key=thumb, mime="audio/mp4",
                         size_bytes=path.stat().st_size, source="library", license=f"{LICENSE} {desc}",
                         info=ins.info))
        for name, make in BUILTIN_STICKERS.items():
            if name in existing:
                continue
            key = st.new_key("library", "png")
            img = make()
            img.save(st.path_for(key))
            db.add(Media(owner_id=LIBRARY_OWNER, kind="sticker", name=name, folder="Library stickers",
                         original_filename=f"{name}.png", storage_key=key, thumb_key=key, mime="image/png",
                         size_bytes=st.path_for(key).stat().st_size, source="library", license=LICENSE,
                         info={"width": img.width, "height": img.height, "has_alpha": True, "animated": False}))


def delete_media_files(m: Media) -> None:
    st = get_storage()
    for k in (m.storage_key, m.thumb_key, m.contact_sheet_key, f"analysis/{m.id}.npz"):
        if k:
            st.delete(k)


def cleanup_expired() -> dict:
    """Delete user uploads and exports older than BEAST_RETENTION_DAYS (0 = keep forever)."""
    days = get_settings().retention_days
    removed = {"media": 0, "exports": 0, "work_dirs": 0}
    work = get_settings().dir("work")
    for d in work.iterdir():
        if d.is_dir() and (datetime.now().timestamp() - d.stat().st_mtime) > 24 * 3600:
            shutil.rmtree(d, ignore_errors=True)
            removed["work_dirs"] += 1
    previews = get_storage().root / "previews"
    removed["previews"] = 0
    if previews.exists():
        for f in previews.iterdir():  # comparison frames and frame grabs are a cache
            if f.is_file() and (datetime.now().timestamp() - f.stat().st_mtime) > 24 * 3600:
                f.unlink(missing_ok=True)
                removed["previews"] += 1
    if days <= 0:
        return removed
    cutoff = datetime.now(UTC) - timedelta(days=days)
    st = get_storage()
    with session_scope() as db:
        for m in db.scalars(select(Media).where(Media.created_at < cutoff, Media.owner_id != LIBRARY_OWNER)).all():
            delete_media_files(m)
            db.delete(m)
            removed["media"] += 1
        for e in db.scalars(select(Export).where(Export.created_at < cutoff)).all():
            st.delete(e.storage_key)
            st.delete(e.thumb_key)
            db.delete(e)
            removed["exports"] += 1
    return removed


def dir_size(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.exists() else 0
