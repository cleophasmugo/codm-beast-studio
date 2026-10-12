"""Shared fixtures. Every test session gets its own data directory and SQLite database."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

_DATA = Path(tempfile.mkdtemp(prefix="beast-test-"))
os.environ["BEAST_DATA_DIR"] = str(_DATA)
os.environ.setdefault("BEAST_DATABASE_URL", "")
os.environ["BEAST_BROKER_URL"] = ""
os.environ["BEAST_API_TOKEN"] = ""
os.environ["BEAST_X264_PRESET"] = "ultrafast"

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))


@pytest.fixture(scope="session")
def samples() -> Path:
    out = _DATA / "samples"
    if not (out / "sample_gameplay.mp4").exists():
        subprocess.run([sys.executable, str(REPO / "scripts" / "make_sample_media.py"), str(out)], check=True)
    return out


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app.main import app
    with TestClient(app) as c:
        yield c


def wait_job(client, job_id: str, timeout: float = 300) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["status"] in ("done", "failed", "cancelled"):
            return j
        time.sleep(0.5)
    raise AssertionError(f"job {job_id} did not finish: {j}")


def probe(path: Path) -> dict:
    import json
    out = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams",
                          str(path)], capture_output=True, text=True, check=True).stdout
    return json.loads(out)
