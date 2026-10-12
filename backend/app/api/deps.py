from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.models import Export, Job, Media, Project, TimelineRevision
from ..schemas import ExportOut, JobOut, MediaOut, ProjectOut, ProjectSettings, Timeline
from ..services.maintenance import LIBRARY_OWNER


def visible_owner(m_owner: str, owner: str) -> bool:
    return m_owner in (owner, LIBRARY_OWNER)


def get_media(db: Session, mid: str, owner: str, *, writable: bool = False) -> Media:
    m = db.get(Media, mid)
    if not m or not visible_owner(m.owner_id, owner) or (writable and m.owner_id != owner):
        raise HTTPException(404, "Media not found")
    return m


def get_project(db: Session, pid: str, owner: str) -> Project:
    p = db.get(Project, pid)
    if not p or p.owner_id != owner:
        raise HTTPException(404, "Project not found")
    return p


def get_job(db: Session, jid: str, owner: str) -> Job:
    j = db.get(Job, jid)
    if not j or j.owner_id != owner:
        raise HTTPException(404, "Job not found")
    return j


def get_export(db: Session, eid: str, owner: str) -> Export:
    e = db.get(Export, eid)
    if not e or e.owner_id != owner:
        raise HTTPException(404, "Export not found")
    return e


def media_out(m: Media) -> MediaOut:
    return MediaOut(
        id=m.id, kind=m.kind, name=m.name, folder=m.folder, original_filename=m.original_filename, mime=m.mime,
        size_bytes=m.size_bytes, source=m.source, license=m.license, info=m.info or {},
        has_analysis=bool(m.analysis), created_at=m.created_at, url=f"/api/media/{m.id}/file",
        thumb_url=f"/api/media/{m.id}/thumb" if m.thumb_key else None,
        contact_sheet_url=f"/api/media/{m.id}/contact-sheet" if m.contact_sheet_key else None,
    )


def export_out(e: Export) -> ExportOut:
    return ExportOut(id=e.id, project_id=e.project_id, kind=e.kind, name=e.name, format=e.format, width=e.width,
                     height=e.height, duration=e.duration, size_bytes=e.size_bytes, settings=e.settings or {},
                     created_at=e.created_at, url=f"/api/exports/{e.id}/file",
                     download_url=f"/api/exports/{e.id}/download",
                     thumb_url=f"/api/exports/{e.id}/thumb" if e.thumb_key else None)


def job_out(j: Job) -> JobOut:
    return JobOut(id=j.id, project_id=j.project_id, kind=j.kind, status=j.status, stage=j.stage,
                  progress=j.progress, message=j.message, eta_seconds=j.eta_seconds, result=j.result,
                  error=j.error, attempts=j.attempts, created_at=j.created_at, started_at=j.started_at,
                  finished_at=j.finished_at)


def project_out(db: Session, p: Project) -> ProjectOut:
    n = db.scalar(select(func.count()).select_from(TimelineRevision).where(TimelineRevision.project_id == p.id))
    latest = db.scalars(select(Export).where(Export.project_id == p.id).order_by(Export.created_at.desc())
                        .limit(1)).first()
    return ProjectOut(
        id=p.id, name=p.name, media_ids=p.media_ids or [], settings=ProjectSettings.model_validate(p.settings or {}),
        timeline=Timeline.model_validate(p.timeline) if p.timeline else None, highlights=p.highlights,
        created_at=p.created_at, updated_at=p.updated_at, revision_count=n or 0,
        latest_export=export_out(latest).model_dump(mode="json") if latest else None,
    )
