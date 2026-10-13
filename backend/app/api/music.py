"""Browse free-licensed music on the internet and add it to your music library."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..core.security import current_owner
from ..db.models import Media
from ..db.session import get_db
from ..schemas import MediaOut, OnlineMusicImport, OnlineMusicSearch
from ..services import online_music
from .deps import media_out
from .media import ingest_file

router = APIRouter(prefix="/api/music", tags=["online music"])
FOLDER = "Online music"


def _filename(track_id: str, ext: str) -> str:
    return f"openverse-{track_id}{ext}"


def _imported(db: Session, owner: str) -> dict[str, str]:
    """Openverse track id -> Media id for tracks this owner already added."""
    rows = db.scalars(select(Media).where(Media.owner_id == owner, Media.source == "online")).all()
    return {m.original_filename.removeprefix("openverse-").rsplit(".", 1)[0]: m.id for m in rows}


@router.get("/search", response_model=OnlineMusicSearch,
            summary="Search free-licensed music online (Jamendo via Openverse; CC0, CC BY, CC BY-SA)")
def search(q: str = Query("", max_length=200), page: int = Query(1, ge=1, le=50),
           owner: str = Depends(current_owner), db: Session = Depends(get_db)) -> OnlineMusicSearch:
    try:
        data = online_music.search(q, page)
    except online_music.OnlineMusicError as e:
        raise HTTPException(502, str(e)) from e
    done = _imported(db, owner)
    for t in data["results"]:
        t["imported_media_id"] = done.get(t["id"])
    return OnlineMusicSearch(**data)


@router.post("/import", response_model=MediaOut, status_code=201,
             summary="Download an online track into your music library")
def import_track(body: OnlineMusicImport, owner: str = Depends(current_owner),
                 db: Session = Depends(get_db)) -> MediaOut:
    existing = _imported(db, owner).get(body.track_id)
    if existing:
        return media_out(db.get(Media, existing))
    try:
        track, ext = online_music.fetch_track(body.track_id)
        tmp = get_settings().dir("work") / f"online_{uuid.uuid4().hex}{ext}"
        online_music.download(track["preview_url"], tmp, get_settings().max_upload_mb * 1024 * 1024)
    except online_music.OnlineMusicError as e:
        raise HTTPException(502, str(e)) from e
    m = ingest_file(db, owner, tmp, _filename(track["id"], ext), FOLDER, source="online",
                    name=f"{track['title']} - {track['creator']}")
    credit = track["attribution"] or f'"{track["title"]}" by {track["creator"]}, {track["license"]}'
    m.license = f"{credit} Source: {track['page_url']}".strip()[:300]
    return media_out(m)
