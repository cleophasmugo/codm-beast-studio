"""End-to-end API tests: upload -> one-click montage -> preview/download, Image Studio -> montage."""

from __future__ import annotations

import pytest
from conftest import probe, wait_job

from app.core.config import get_settings


@pytest.fixture(scope="module")
def uploaded(client, samples):
    files = [("files", (n, open(samples / n, "rb"))) for n in
             ("sample_gameplay.mp4", "sample_screenshot.jpg", "sample_sticker.png")]
    r = client.post("/api/media", files=files, data={"folder": "Session 1"})
    assert r.status_code == 200, r.text
    by_kind = {m["kind"]: m for m in r.json()}
    assert set(by_kind) == {"video", "image", "sticker"}
    return by_kind


def test_health_and_system(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    s = client.get("/api/system").json()
    assert s["formats"]["mp4_h264"] and len(s["presets"]) == 9 and s["job_backend"] == "thread"


def test_library_is_seeded(client):
    music = client.get("/api/media?kind=audio").json()
    assert len([m for m in music if m["source"] == "library"]) == 3
    assert all("CC0" in m["license"] for m in music if m["source"] == "library")
    assert len(client.get("/api/media?kind=sticker").json()) >= 8


def test_media_metadata_thumbs_and_paths(client, uploaded):
    v = uploaded["video"]
    assert v["info"]["width"] == 1280 and v["info"]["fps"] == 30 and v["folder"] == "Session 1"
    assert "path" not in str(v).lower() or "/api/" in v["url"]  # never a filesystem path
    assert "/tmp" not in str(v) and "storage" not in v
    assert client.get(v["thumb_url"]).headers["content-type"] == "image/jpeg"
    assert client.get(v["contact_sheet_url"]).status_code == 200
    r = client.get(v["url"], headers={"Range": "bytes=0-1023"})
    assert r.status_code == 206 and len(r.content) == 1024
    assert client.get(f"/api/media/{v['id']}/frame?t=8").status_code == 200


def test_rename_and_folder(client, uploaded):
    sid = uploaded["sticker"]["id"]
    r = client.patch(f"/api/media/{sid}", json={"name": "../../Crosshair", "folder": "Overlays"})
    assert r.json()["name"] == "Crosshair" and r.json()["folder"] == "Overlays"


def test_upload_validation(client):
    r = client.post("/api/media", files=[("files", ("x.exe", b"MZ" * 10, "application/octet-stream"))])
    assert r.status_code == 415
    r = client.post("/api/media", files=[("files", ("x.mp4", b"not a video at all" * 50, "video/mp4"))])
    assert r.status_code == 415
    s = get_settings()
    old = s.max_upload_mb
    s.max_upload_mb = 0
    try:
        r = client.post("/api/media", files=[("files", ("y.png", b"x" * 2048, "image/png"))])
        assert r.status_code == 413
    finally:
        s.max_upload_mb = old


def test_one_click_montage(client, uploaded):
    r = client.post("/api/montage/quick", json={"media_ids": [uploaded["video"]["id"], uploaded["image"]["id"]],
                                                "preset": "tiktok", "target_duration": 15})
    assert r.status_code == 202, r.text
    job = wait_job(client, r.json()["id"])
    assert job["status"] == "done", job
    res = job["result"]
    assert res["width"] == 1080 and res["height"] == 1920 and 8 <= res["duration"] <= 16
    ex = client.get(f"/api/exports/{res['export_id']}").json()
    dl = client.get(ex["download_url"])
    assert dl.status_code == 200 and "attachment" in dl.headers["content-disposition"]
    path = get_settings().resolved_data_dir / "dl.mp4"
    path.write_bytes(dl.content)
    p = probe(path)
    assert {s["codec_name"] for s in p["streams"]} == {"h264", "aac"}
    proj = client.get(f"/api/projects/{job['project_id']}").json()
    tl = proj["timeline"]
    assert tl["music"] is not None, "one-click picks a library track"
    assert any(c["kind"] == "image" for c in tl["clips"])
    hl = client.get(f"/api/projects/{job['project_id']}/highlights").json()
    cands = next(iter(hl["media"].values()))["candidates"]
    assert cands and all(c["evidence"] == "heuristic" for c in cands)
    assert "kill" in hl["evidence_note"].lower() and "heuristic" in hl["evidence_note"]
    assert proj["revision_count"] >= 1


@pytest.fixture(scope="module")
def project(client, uploaded):
    r = client.post("/api/projects", json={"name": "Manual", "media_ids": [uploaded["video"]["id"]]})
    assert r.status_code == 201
    pid = r.json()["id"]
    r = client.post(f"/api/projects/{pid}/apply-preset/esports")
    assert r.json()["settings"]["preset"] == "esports"
    s = r.json()["settings"]
    s["target_duration"] = 10
    client.patch(f"/api/projects/{pid}", json={"settings": s})
    job = wait_job(client, client.post(f"/api/projects/{pid}/auto-edit", json={"render": False}).json()["id"])
    assert job["status"] == "done" and "export_id" not in job["result"]
    return pid


def test_timeline_edit_validation_and_history(client, project, uploaded):
    p = client.get(f"/api/projects/{project}").json()
    tl = p["timeline"]
    bad = {**tl, "clips": [{**tl["clips"][0], "start": 50, "end": 60}]}
    assert client.put(f"/api/projects/{project}/timeline", json={"timeline": bad}).status_code == 422
    edited = {**tl, "clips": list(reversed(tl["clips"]))[:2]}
    r = client.put(f"/api/projects/{project}/timeline", json={"timeline": edited, "note": "Reordered"})
    assert r.status_code == 200 and len(r.json()["timeline"]["clips"]) == 2
    revs = client.get(f"/api/projects/{project}/revisions").json()
    assert revs[0]["note"] == "Reordered" and len(revs) >= 2
    r = client.post(f"/api/projects/{project}/revisions/{revs[-1]['id']}/restore")
    assert len(r.json()["timeline"]["clips"]) == len(tl["clips"])


def test_image_studio_to_montage(client, project, uploaded):
    img = uploaded["image"]["id"]
    a = client.post(f"/api/images/{img}/analyze").json()
    assert a["suggested"]["gamma"] > 1
    prev = client.post(f"/api/images/{img}/preview", json={"auto_enhance": True})
    assert prev.headers["content-type"] == "image/jpeg" and prev.headers["x-auto-reasons"]
    r = client.post(f"/api/images/{img}/render", json={"edit": {"auto_enhance": True, "layers": [
        {"type": "text", "text": "ACE"}, {"type": "sticker", "media_id": uploaded["sticker"]["id"]}]},
        "format": "jpeg"})
    assert r.status_code == 200, r.text
    new_id = r.json()["media"]["id"]
    assert r.json()["export"]["kind"] == "image"
    assert client.get(r.json()["export"]["download_url"]).status_code == 200
    # an image export and the saved image are independent files
    extra = client.post(f"/api/images/{img}/render", json={"edit": {}, "format": "png"}).json()
    assert client.delete(f"/api/exports/{extra['export']['id']}").status_code == 204
    assert client.get(extra["media"]["url"]).status_code == 200
    before = len(client.get(f"/api/projects/{project}").json()["timeline"]["clips"])
    r = client.post("/api/images/add-to-montage", json={"project_id": project, "media_id": new_id, "duration": 2,
                                                        "position": 1})
    clips = r.json()["timeline"]["clips"]
    assert len(clips) == before + 1 and clips[1]["kind"] == "image" and clips[1]["media_id"] == new_id
    job = wait_job(client, client.post(f"/api/projects/{project}/render", json={"preview": True}).json()["id"])
    assert job["status"] == "done", job
    assert job["result"]["height"] == 540


def test_compare_frames(client, project, uploaded):
    r = client.post(f"/api/projects/{project}/compare", json={"media_id": uploaded["video"]["id"], "t": 9})
    assert r.status_code == 200
    d = r.json()
    assert d["filters"] and client.get(d["before_url"]).status_code == 200
    assert client.get(d["after_url"]).content != client.get(d["before_url"]).content
    assert client.get("/api/previews/..%2F..%2Fbeast.sqlite3").status_code == 404
    r = client.get("/api/previews/../../beast.sqlite3")  # client normalises to /beast.sqlite3
    assert b"SQLite format" not in r.content
    assert client.get("/api/does-not-exist").status_code == 404


def test_cancel_and_retry(client, project):
    r = client.post(f"/api/projects/{project}/render", json={"preview": False})
    jid = r.json()["id"]
    assert client.post(f"/api/projects/{project}/render").status_code == 409  # one job per project at a time
    client.post(f"/api/jobs/{jid}/cancel")
    job = wait_job(client, jid)
    assert job["status"] == "cancelled"
    r = client.post(f"/api/jobs/{jid}/retry")
    assert r.status_code == 202
    assert wait_job(client, jid)["status"] == "done"
    hist = client.get("/api/exports").json()
    assert any(e["kind"] == "video" for e in hist) and any(e["kind"] == "image" for e in hist)


def test_auth_token(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "api_token", "s3cret")
    assert client.get("/api/media").status_code == 401
    assert client.get("/api/media", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.get("/api/media", headers={"Authorization": "Bearer s3cret"}).status_code == 200
    assert client.get("/api/media?access_token=s3cret").status_code == 200
    assert client.get("/api/health").status_code == 200


def test_delete_project_and_media(client, uploaded):
    pid = client.post("/api/projects", json={"name": "tmp"}).json()["id"]
    assert client.delete(f"/api/projects/{pid}").status_code == 204
    assert client.get(f"/api/projects/{pid}").status_code == 404
    lib = client.get("/api/media?kind=sticker").json()
    lib_id = next(m["id"] for m in lib if m["source"] == "library")
    assert client.delete(f"/api/media/{lib_id}").status_code == 404  # library assets are read-only
    sid = uploaded["sticker"]["id"]
    assert client.delete(f"/api/media/{sid}").status_code == 204
    assert client.get(f"/api/media/{sid}").status_code == 404


def test_migrations_match_models():
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from app.db.base import Base
    from app.db.session import get_engine
    with get_engine().connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == [], diff
