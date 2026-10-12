import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import db  # noqa: E402
import hub  # noqa: E402
import youtube  # noqa: E402
import ytapi  # noqa: E402


def entry(vid, duration=600, channel="Chan", title=None):
    return {
        "id": vid,
        "title": title or f"Video {vid}",
        "duration": duration,
        "channel": channel,
        "channel_id": "UC" + vid,
        "view_count": 1,
    }


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "hub.sqlite")
    monkeypatch.setattr(hub, "enrich_missing", lambda: None)
    monkeypatch.setattr(ytapi, "available", lambda: False)
    monkeypatch.setattr(youtube, "fetch_playlist", lambda yt_id: ("List", LISTING[:]))
    db.init()
    with TestClient(hub.app) as c:
        yield c


LISTING = [
    entry("aaaaaaaaaaa", 300, "A"),
    entry("bbbbbbbbbbb", 1200, "B"),
    entry("ccccccccccc", 3600, "A"),
]


def test_add_and_sync(client):
    r = client.post(
        "/api/playlists",
        json={"url": "https://www.youtube.com/playlist?list=PLxxxxxxxxxxx"},
    )
    assert r.status_code == 201
    assert r.json()["counts"]["active"] == 3
    assert (
        client.post("/api/playlists", json={"url": "PLxxxxxxxxxxx"}).status_code == 409
    )
    assert client.post("/api/playlists", json={"url": "nope"}).status_code == 400

    LISTING.pop()
    r = client.post("/api/playlists/1/sync").json()
    assert (r["added"], r["gone"], r["total"]) == (0, 1, 2)
    LISTING.append(entry("ccccccccccc", 3600, "A"))
    r = client.post("/api/playlists/1/sync").json()
    assert (r["added"], r["gone"]) == (0, 0)
    assert all(
        i["status"] == "active" for i in client.get("/api/playlists/1/items").json()
    )


def test_pick_filters_and_skip_tiers(client):
    client.post("/api/playlists", json={"url": "PLxxxxxxxxxxx"})
    items = {i["video_id"]: i for i in client.get("/api/playlists/1/items").json()}

    assert (
        client.get("/api/playlists/1/pick?min=1000&max=2000").json()["video_id"]
        == "bbbbbbbbbbb"
    )
    assert (
        client.get("/api/playlists/1/pick?channel=B").json()["video_id"]
        == "bbbbbbbbbbb"
    )
    assert client.get("/api/playlists/1/pick?min=5000").json() is None

    a, c = items["aaaaaaaaaaa"]["id"], items["ccccccccccc"]["id"]
    client.post(f"/api/items/{a}/skip")
    picks = {
        client.get("/api/playlists/1/pick?channel=A").json()["id"] for _ in range(20)
    }
    assert picks == {c}
    client.post(f"/api/items/{c}/skip")
    picks = {
        client.get("/api/playlists/1/pick?channel=A").json()["id"] for _ in range(40)
    }
    assert picks == {a, c}
    client.post(f"/api/items/{c}/watched")
    assert client.get(f"/api/playlists/1/pick?channel=A&exclude={a}").json() is None
    client.post(f"/api/items/{c}/restore")
    assert client.get(f"/api/playlists/1/pick?channel=A&exclude={a}").json()["id"] == c

    actions = [e["action"] for e in client.get("/api/playlists/1/history").json()]
    assert actions == ["restore", "watched", "skip", "skip"]
    assert client.post(f"/api/items/{a}/unskip").json()["skips"] == 0
    assert client.post(f"/api/items/{a}/unskip").json()["skips"] == 0
    assert client.post("/api/items/999/skip").status_code == 404
    assert client.post(f"/api/items/{a}/explode").status_code == 404


def test_delete_playlist(client):
    client.post("/api/playlists", json={"url": "PLxxxxxxxxxxx"})
    assert client.delete("/api/playlists/1").status_code == 204
    assert client.get("/api/state").json()["playlists"] == []
    assert client.get("/api/playlists/1/items").status_code == 404


def test_parse_playlist_id():
    assert (
        youtube.parse_playlist_id("https://www.youtube.com/playlist?list=PLabc123_-xyz")
        == "PLabc123_-xyz"
    )
    assert (
        youtube.parse_playlist_id(
            "https://www.youtube.com/watch?v=x&list=PLabc123_-xyz&index=2"
        )
        == "PLabc123_-xyz"
    )
    assert youtube.parse_playlist_id(" PLabc123_-xyz ") == "PLabc123_-xyz"
    with pytest.raises(ValueError):
        youtube.parse_playlist_id("https://example.com/")


def test_parse_duration():
    assert ytapi.parse_duration("PT1H2M3S") == 3723
    assert ytapi.parse_duration("PT45S") == 45
    assert ytapi.parse_duration("P1DT1S") == 86401
    assert ytapi.parse_duration("nonsense") is None


def test_api_sync_and_push(client, monkeypatch):
    calls = []
    api_entries = [
        {
            **entry("aaaaaaaaaaa", 300, "A"),
            "yt_item_id": "PI_a",
            "added_at": "2024-01-02T03:04:05Z",
            "published": "2023-12-31",
        },
        {
            "id": "ppppppppppp",
            "title": "Private video",
            "duration": None,
            "yt_item_id": "PI_p",
            "added_at": "2024-02-02T00:00:00Z",
            "published": None,
        },
    ]
    monkeypatch.setattr(ytapi, "available", lambda: True)
    monkeypatch.setattr(
        ytapi, "fetch_playlist", lambda yt_id: ("Api list", api_entries)
    )
    monkeypatch.setattr(
        ytapi, "delete_item", lambda yt_item_id: calls.append(("delete", yt_item_id))
    )
    monkeypatch.setattr(
        ytapi,
        "insert_item",
        lambda pl, vid: calls.append(("insert", pl, vid)) or "PI_new",
    )

    client.post("/api/playlists", json={"url": "PLxxxxxxxxxxx"})
    items = {i["video_id"]: i for i in client.get("/api/playlists/1/items").json()}
    a = items["aaaaaaaaaaa"]
    assert (a["added_at"], a["published"], a["on_youtube"]) == (
        "2024-01-02T03:04:05Z",
        "2023-12-31",
        True,
    )
    assert items["ppppppppppp"]["available"] is False
    assert client.get("/api/state").json()["youtube"]["connected"] is True

    r = client.post(f"/api/items/{a['id']}/watched").json()
    assert r["on_youtube"] is False and "youtube_error" not in r
    r = client.post(f"/api/items/{a['id']}/restore").json()
    assert r["on_youtube"] is True
    assert calls == [("delete", "PI_a"), ("insert", "PLxxxxxxxxxxx", "aaaaaaaaaaa")]

    def boom(*_):
        raise ytapi.ApiError("quota")

    monkeypatch.setattr(ytapi, "delete_item", boom)
    r = client.post(f"/api/items/{a['id']}/remove").json()
    assert (
        r["status"] == "removed"
        and r["youtube_error"] == "quota"
        and r["on_youtube"] is True
    )


def test_auth_flow(client, monkeypatch, tmp_path):
    monkeypatch.setattr(ytapi, "CLIENT_SECRET", tmp_path / "missing.json")
    assert client.get("/auth", follow_redirects=False).status_code == 400

    secret = tmp_path / "client_secret.json"
    secret.write_text(
        '{"installed": {"client_id": "id", "client_secret": "s", '
        '"auth_uri": "https://accounts.google.com/o/oauth2/auth", '
        '"token_uri": "https://oauth2.googleapis.com/token", '
        '"redirect_uris": ["http://localhost"]}}'
    )
    monkeypatch.setattr(ytapi, "CLIENT_SECRET", secret)
    r = client.get("/auth", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"].startswith(
        "https://accounts.google.com/o/oauth2/auth?"
    )
    assert "prompt=consent" in r.headers["location"]
    assert "auth%2Fcallback" in r.headers["location"]

    assert (
        client.get(
            "/auth/callback?error=access_denied", follow_redirects=False
        ).status_code
        == 400
    )
    codes = []
    monkeypatch.setattr(ytapi, "finish_auth", codes.append)
    r = client.get("/auth/callback?code=abc", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "/" and codes == ["abc"]


def test_expired_token_falls_back_to_ytdlp(client, monkeypatch):
    monkeypatch.setattr(ytapi, "available", lambda: True)

    def expired(_):
        raise ytapi.TokenExpired("gone")

    monkeypatch.setattr(ytapi, "fetch_playlist", expired)
    r = client.post("/api/playlists", json={"url": "PLxxxxxxxxxxx"})
    assert r.status_code == 201 and r.json()["title"] == "List"
