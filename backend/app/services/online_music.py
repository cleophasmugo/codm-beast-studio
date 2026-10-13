"""Search and import Creative Commons music from the internet through Openverse (https://openverse.org).

Only full-length Jamendo tracks whose licence allows commercial use and modification (CC0, CC BY,
CC BY-SA) are offered, so a montage made with one can be posted on YouTube or TikTok as long as the
artist is credited. The attribution text is stored as the track's licence.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError

from .. import __version__
from ..core.config import get_settings

SOURCES = "jamendo"
ALLOWED_DOWNLOAD_HOSTS = ("jamendo.com",)
ALLOWED_LICENSES = {"cc0", "pdm", "by", "by-sa"}
FILETYPE_EXT = {"mp32": ".mp3", "mp31": ".mp3", "mp3": ".mp3", "ogg": ".ogg", "flac": ".flac", "wav": ".wav"}
MIN_SECONDS = 20  # skip jingles and stingers
USER_AGENT = f"CODMBeastStudio/{__version__} (+https://github.com/cleophasmugo/codm-beast-studio)"
_TRACK_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class OnlineMusicError(RuntimeError):
    """The music service could not be reached or returned something unusable (message is user-facing)."""


def _api() -> str:
    base = get_settings().online_music_api.rstrip("/")
    if not base:
        raise OnlineMusicError("Online music is turned off on this server (BEAST_ONLINE_MUSIC_API is empty).")
    return base


def _get_json(url: str, timeout: float = 15) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except HTTPError as e:
        if e.code == 404:
            raise OnlineMusicError("That track is no longer available online.") from e
        if e.code == 429:
            raise OnlineMusicError("The online music search is busy. Wait a minute and try again.") from e
        raise OnlineMusicError(f"The online music search returned an error ({e.code}).") from e
    except (URLError, TimeoutError, OSError, ValueError) as e:
        raise OnlineMusicError("Couldn't reach the online music search. Check your internet connection.") from e


def _license_label(r: dict[str, Any]) -> str:
    lic = (r.get("license") or "").lower()
    if lic in ("cc0", "pdm"):
        return "Public domain" if lic == "pdm" else "CC0"
    return f"CC {lic.upper()} {r.get('license_version') or ''}".strip()


def _track(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": r["id"],
        "title": (r.get("title") or "Untitled").strip(),
        "creator": (r.get("creator") or "Unknown artist").strip(),
        "duration": round((r.get("duration") or 0) / 1000, 1),
        "license": _license_label(r),
        "license_url": r.get("license_url") or "",
        "attribution": r.get("attribution") or "",
        "genres": [g for g in (r.get("genres") or []) if g][:4],
        "preview_url": r.get("url") or "",
        "page_url": r.get("foreign_landing_url") or "",
        "source": r.get("source") or "",
    }


def _usable(r: dict[str, Any]) -> bool:
    return (r.get("source") in SOURCES.split(",") and (r.get("license") or "").lower() in ALLOWED_LICENSES
            and (r.get("duration") or 0) >= MIN_SECONDS * 1000 and bool(r.get("url")))


def search(query: str, page: int = 1, page_size: int = 20) -> dict[str, Any]:
    params = {"q": query.strip() or "music", "license_type": "commercial,modification", "source": SOURCES,
              "page": page, "page_size": page_size}
    data = _get_json(f"{_api()}/audio/?{urllib.parse.urlencode(params)}")
    results = [_track(r) for r in data.get("results", []) if _usable(r)]
    return {"results": results, "page": page, "page_count": int(data.get("page_count") or 0),
            "result_count": int(data.get("result_count") or 0)}


def fetch_track(track_id: str) -> tuple[dict[str, Any], str]:
    """Look a track up by id (never trust a client-supplied URL). Returns (track, file extension)."""
    if not _TRACK_ID.match(track_id):
        raise OnlineMusicError("Invalid track id.")
    r = _get_json(f"{_api()}/audio/{track_id}/")
    if not _usable(r):
        raise OnlineMusicError("That track can't be used: it isn't a full-length track with a free licence.")
    ext = FILETYPE_EXT.get((r.get("filetype") or "").lower(), ".mp3")
    return _track(r), ext


def _host_ok(url: str) -> bool:
    p = urllib.parse.urlparse(url)
    host = (p.hostname or "").lower()
    return p.scheme == "https" and any(host == h or host.endswith("." + h) for h in ALLOWED_DOWNLOAD_HOSTS)


def download(url: str, dest: Path, limit_bytes: int, timeout: float = 60) -> None:
    if not _host_ok(url):
        raise OnlineMusicError("That track is hosted somewhere this app doesn't download from.")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    size = 0
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp, open(dest, "wb") as fh:
            if not _host_ok(resp.geturl()):
                raise OnlineMusicError("That track redirected somewhere this app doesn't download from.")
            while chunk := resp.read(1024 * 1024):
                size += len(chunk)
                if size > limit_bytes:
                    raise OnlineMusicError("That track is larger than the upload limit.")
                fh.write(chunk)
    except OnlineMusicError:
        dest.unlink(missing_ok=True)
        raise
    except (URLError, TimeoutError, OSError) as e:
        dest.unlink(missing_ok=True)
        raise OnlineMusicError("The track download failed. Check your internet connection and try again.") from e
    if size == 0:
        dest.unlink(missing_ok=True)
        raise OnlineMusicError("The track download was empty.")
