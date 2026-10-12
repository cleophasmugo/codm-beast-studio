"""Authentication hook and filesystem safety helpers."""

from __future__ import annotations

import hmac
import re
import unicodedata
from pathlib import Path

from fastapi import Header, HTTPException, Query, status

from .config import get_settings

LOCAL_OWNER = "local"


def current_owner(
    authorization: str | None = Header(default=None),
    access_token: str | None = Query(default=None, include_in_schema=False),
) -> str:
    """Return the owner id for this request.

    Single-user mode (no BEAST_API_TOKEN) always returns "local". With a token configured,
    the request must present it. Swap this function for real user auth later; every table
    already carries an owner_id column, and every query is filtered by it.
    """
    token = get_settings().api_token
    if not token:
        return LOCAL_OWNER
    presented = ""
    if authorization and authorization.lower().startswith("bearer "):
        presented = authorization[7:].strip()
    elif access_token:
        presented = access_token
    if not presented or not hmac.compare_digest(presented, token):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing or invalid access token",
                            headers={"WWW-Authenticate": "Bearer"})
    return LOCAL_OWNER


_SAFE_CHARS = re.compile(r"[^A-Za-z0-9 ._()\-]+")


def clean_display_name(name: str, fallback: str = "untitled", max_len: int = 120) -> str:
    """Make a user-supplied name safe to show and to use in a download filename."""
    name = unicodedata.normalize("NFKC", name or "")
    name = Path(name.replace("\\", "/")).name  # drop any directory parts
    name = _SAFE_CHARS.sub("_", name).strip(" ._")
    return (name or fallback)[:max_len]


def safe_join(root: Path, *parts: str) -> Path:
    """Join paths and refuse anything that escapes root (path traversal guard)."""
    root = root.resolve()
    p = root.joinpath(*parts).resolve()
    if p != root and root not in p.parents:
        raise ValueError("Path escapes storage root")
    return p
