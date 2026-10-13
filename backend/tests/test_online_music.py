"""Online music browsing. The Openverse API is faked, so these tests run offline."""

from __future__ import annotations

import shutil

import pytest

from app.services import online_music

TRACK_ID = "7408ac37-9986-4fe6-b71c-11316deed3ae"


def _row(**kw):
    r = {"id": TRACK_ID, "title": "Play the Game", "creator": "Lilly Wolf", "license": "by", "license_version": "3.0",
         "license_url": "https://creativecommons.org/licenses/by/3.0/", "source": "jamendo", "duration": 230000,
         "attribution": '"Play the Game" by Lilly Wolf is licensed under CC BY 3.0.', "genres": ["electronic"],
         "url": "https://prod-1.storage.jamendo.com/?trackid=1093616&format=mp32", "filetype": "mp32",
         "foreign_landing_url": "https://www.jamendo.com/track/1093616"}
    r.update(kw)
    return r


@pytest.fixture
def fake_openverse(monkeypatch, samples):
    def get_json(url, timeout=15):
        if "/audio/?" in url:
            return {"result_count": 3, "page_count": 1, "results": [
                _row(), _row(id="a" * 8 + "-0000-0000-0000-" + "0" * 12, duration=4000),  # too short
                _row(id="b" * 8 + "-0000-0000-0000-" + "0" * 12, license="by-nc"),  # non-commercial
            ]}
        return _row()

    def download(url, dest, limit_bytes, timeout=60):
        assert online_music._host_ok(url)
        shutil.copy(_wav(samples), dest)

    monkeypatch.setattr(online_music, "_get_json", get_json)
    monkeypatch.setattr(online_music, "download", download)


def _wav(samples):
    import numpy as np
    import soundfile as sf
    p = samples / "online_test.wav"
    if not p.exists():
        t = np.linspace(0, 25, 25 * 22050, endpoint=False)
        sf.write(p, 0.3 * np.sin(2 * np.pi * 220 * t), 22050)
    return p


def test_search_filters_to_usable_tracks(client, fake_openverse):
    r = client.get("/api/music/search", params={"q": "gaming"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert [t["id"] for t in body["results"]] == [TRACK_ID]
    t = body["results"][0]
    assert t["license"] == "CC BY 3.0" and t["duration"] == 230.0 and t["imported_media_id"] is None


def test_import_adds_credited_track_once(client, fake_openverse):
    r = client.post("/api/music/import", json={"track_id": TRACK_ID})
    assert r.status_code == 201, r.text
    m = r.json()
    assert m["kind"] == "audio" and m["source"] == "online" and m["folder"] == "Online music"
    assert m["name"] == "Play the Game - Lilly Wolf"
    assert "Lilly Wolf" in m["license"] and "jamendo.com/track/1093616" in m["license"]
    again = client.post("/api/music/import", json={"track_id": TRACK_ID}).json()
    assert again["id"] == m["id"]
    found = client.get("/api/music/search", params={"q": "gaming"}).json()["results"][0]
    assert found["imported_media_id"] == m["id"]


def test_import_rejects_bad_ids_and_hosts(client):
    assert client.post("/api/music/import", json={"track_id": "../../etc"}).status_code == 502
    assert not online_music._host_ok("https://evil.example.com/x.mp3")
    assert not online_music._host_ok("http://prod-1.storage.jamendo.com/x")
    assert online_music._host_ok("https://prod-1.storage.jamendo.com/?trackid=1")
