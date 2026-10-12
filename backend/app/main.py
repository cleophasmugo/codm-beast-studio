"""FastAPI application: REST API under /api, interactive docs at /docs, built frontend at /."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from . import __version__
from .api import media, projects
from .api.misc import exports, images, jobs, system
from .core.config import get_settings
from .db.session import run_migrations
from .services.maintenance import (
    cleanup_expired,
    ensure_library,
    recover_interrupted_jobs,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("beast")


@asynccontextmanager
async def lifespan(app: FastAPI):
    run_migrations()
    n = recover_interrupted_jobs()
    if n:
        log.warning("Marked %d interrupted job(s) as failed; they can be retried", n)
    ensure_library()
    cleanup_expired()
    yield


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="CODM Beast Studio API", version=__version__, lifespan=lifespan,
        description="Automatic CODM montage editor: upload gameplay, auto-edit, preview and export. "
                    "Set BEAST_API_TOKEN to require `Authorization: Bearer <token>` on every /api call.",
    )
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_origins, allow_credentials=False,
                       allow_methods=["*"], allow_headers=["*"], expose_headers=["X-Auto-Reasons"])

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:  # no stack traces or paths to clients
        log.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse({"detail": "Internal server error. Check the server log for details."}, status_code=500)

    for r in (media.router, projects.router, projects.quick_router, jobs, exports, images, system):
        app.include_router(r)

    dist = s.frontend_dist.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        """Serve the built frontend (checked per request, so building it needs no restart)."""
        if path == "api" or path.startswith(("api/", "docs", "openapi.json")):
            raise HTTPException(404, "Not found")
        if not (dist / "index.html").exists():
            return JSONResponse({"app": "CODM Beast Studio", "docs": "/docs",
                                 "note": "Frontend not built: run `npm run build` in frontend/ (see README)."})
        f = (dist / path).resolve()
        if path and dist in f.parents and f.is_file():
            headers = {"Cache-Control": "public, max-age=31536000, immutable"} if path.startswith("assets/") else None
            return FileResponse(f, headers=headers)
        return FileResponse(dist / "index.html", headers={"Cache-Control": "no-cache"})

    return app


app = create_app()
