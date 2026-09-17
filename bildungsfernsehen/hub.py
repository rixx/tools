#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["fastapi", "uvicorn", "yt-dlp", "google-auth-oauthlib", "requests"]
# ///
"""Watch-later hub: `./hub.py` serves the UI; `add URL`, `sync`, `auth`, `open` work from the shell."""

import random
import socket
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import db
import youtube
import ytapi

HOST, PORT = "127.0.0.1", 8765
STATIC = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_app):
    db.init()
    enrich_missing()
    yield


app = FastAPI(title="bildungsfernsehen", lifespan=lifespan)


# --- enrichment: publish dates need one request per video, run in the background ---

_enrich_lock = threading.Lock()
_enrich_pending: set[str] = set()


def _enrich_one(video_id):
    info = youtube.fetch_video(video_id)
    with db.connect() as conn:
        db.store_enrichment(conn, video_id, info)
    with _enrich_lock:
        _enrich_pending.discard(video_id)


def enrich_missing():
    with db.connect() as conn:
        ids = db.pending_enrichment(conn)
    with _enrich_lock:
        new = [i for i in ids if i not in _enrich_pending]
        _enrich_pending.update(new)
    if not new:
        return

    def run():
        with ThreadPoolExecutor(max_workers=4) as pool:
            pool.map(_enrich_one, new)

    threading.Thread(target=run, daemon=True).start()


def enriching_count():
    with _enrich_lock:
        return len(_enrich_pending)


# --- sync ---


def sync_playlist(playlist_id):
    with db.connect() as conn:
        row = db.get_playlist(conn, playlist_id)
    if row is None:
        raise HTTPException(404, "playlist not found")
    source = ytapi if ytapi.available() else youtube
    try:
        title, entries = source.fetch_playlist(row["yt_id"])
    except Exception as e:  # noqa: BLE001 — yt-dlp raises a zoo of things
        raise HTTPException(502, f"youtube fetch failed: {e}")
    with db.connect() as conn:
        conn.execute("UPDATE playlists SET title = ? WHERE id = ?", (title, playlist_id))
        added, gone = db.apply_sync(conn, playlist_id, entries)
        playlist = db.playlist_dict(conn, db.get_playlist(conn, playlist_id))
    enrich_missing()
    return {"added": added, "gone": gone, "total": len(entries), "playlist": playlist}


# --- api ---


class PlaylistIn(BaseModel):
    url: str


@app.get("/api/state")
def state():
    with db.connect() as conn:
        playlists = [db.playlist_dict(conn, r) for r in conn.execute("SELECT * FROM playlists ORDER BY id")]
    return {
        "playlists": playlists,
        "enriching": enriching_count(),
        "youtube": {"connected": ytapi.available(), "client_secret": ytapi.CLIENT_SECRET.exists()},
    }


@app.post("/api/playlists", status_code=201)
def add_playlist(body: PlaylistIn):
    try:
        yt_id = youtube.parse_playlist_id(body.url)
    except ValueError:
        raise HTTPException(400, "not a playlist url")
    with db.connect() as conn:
        if conn.execute("SELECT 1 FROM playlists WHERE yt_id = ?", (yt_id,)).fetchone():
            raise HTTPException(409, "playlist already added")
        cur = conn.execute("INSERT INTO playlists (yt_id, title) VALUES (?, ?)", (yt_id, yt_id))
        playlist_id = cur.lastrowid
    try:
        return sync_playlist(playlist_id)["playlist"]
    except HTTPException:
        with db.connect() as conn:
            conn.execute("DELETE FROM playlists WHERE id = ?", (playlist_id,))
        raise


@app.post("/api/playlists/{playlist_id}/sync")
def sync(playlist_id: int):
    return sync_playlist(playlist_id)


@app.delete("/api/playlists/{playlist_id}", status_code=204)
def delete_playlist(playlist_id: int):
    with db.connect() as conn:
        if conn.execute("DELETE FROM playlists WHERE id = ?", (playlist_id,)).rowcount == 0:
            raise HTTPException(404, "playlist not found")
    return Response(status_code=204)


@app.get("/api/playlists/{playlist_id}/items")
def items(playlist_id: int):
    with db.connect() as conn:
        if db.get_playlist(conn, playlist_id) is None:
            raise HTTPException(404, "playlist not found")
        rows = conn.execute(db.ITEM_SQL + " WHERE i.playlist_id = ? ORDER BY i.position", (playlist_id,)).fetchall()
    return [db.item_dict(r) for r in rows]


@app.get("/api/playlists/{playlist_id}/pick")
def pick(
    playlist_id: int,
    min_duration: int | None = Query(default=None, alias="min"),
    max_duration: int | None = Query(default=None, alias="max"),
    channel: list[str] = Query(default=[]),
    exclude: int | None = None,
):
    with db.connect() as conn:
        rows = conn.execute(
            db.ITEM_SQL + " WHERE i.playlist_id = ? AND i.status = 'active' AND v.available = 1", (playlist_id,)
        ).fetchall()
    candidates = [
        r
        for r in rows
        if r["id"] != exclude
        and (min_duration is None or (r["duration"] is not None and r["duration"] >= min_duration))
        and (max_duration is None or (r["duration"] is not None and r["duration"] <= max_duration))
        and (not channel or r["channel"] in channel)
    ]
    if not candidates:
        return None
    # Skipped videos come back only once everything else has been skipped as often.
    min_skips = min(r["skips"] for r in candidates)
    return db.item_dict(random.choice([r for r in candidates if r["skips"] == min_skips]))


ACTIONS = {
    "skip": "UPDATE items SET skips = skips + 1, last_skipped_at = :ts WHERE id = :id",
    "unskip": "UPDATE items SET skips = MAX(skips - 1, 0) WHERE id = :id",
    "watched": "UPDATE items SET status = 'watched', watched_at = :ts WHERE id = :id",
    "remove": "UPDATE items SET status = 'removed', removed_at = :ts WHERE id = :id",
    "restore": "UPDATE items SET status = 'active', watched_at = NULL, removed_at = NULL WHERE id = :id",
}


def push_to_youtube(conn, item, action):
    """Mirror watched/remove/restore onto the YouTube playlist. Returns an error string or None."""
    if not ytapi.available():
        return None
    try:
        if action in ("watched", "remove") and item["yt_item_id"]:
            ytapi.delete_item(item["yt_item_id"])
            conn.execute("UPDATE items SET yt_item_id = NULL WHERE id = ?", (item["id"],))
        elif action == "restore" and not item["yt_item_id"]:
            playlist = db.get_playlist(conn, item["playlist_id"])
            yt_item_id = ytapi.insert_item(playlist["yt_id"], item["video_id"])
            conn.execute("UPDATE items SET yt_item_id = ? WHERE id = ?", (yt_item_id, item["id"]))
    except Exception as e:  # noqa: BLE001
        return str(e)
    return None


@app.post("/api/items/{item_id}/{action}")
def item_action(item_id: int, action: str):
    if action not in ACTIONS:
        raise HTTPException(404, "unknown action")
    with db.connect() as conn:
        item = db.get_item(conn, item_id)
        if item is None:
            raise HTTPException(404, "item not found")
        conn.execute(ACTIONS[action], {"id": item_id, "ts": db.now()})
        db.log_event(conn, item_id, action)
        youtube_error = push_to_youtube(conn, item, action)
        result = db.item_dict(db.get_item(conn, item_id))
    if youtube_error:
        result["youtube_error"] = youtube_error
    return result


@app.get("/api/playlists/{playlist_id}/history")
def history(playlist_id: int, limit: int = 50):
    with db.connect() as conn:
        rows = conn.execute(
            """SELECT e.id AS event_id, e.action, e.at, i.*, v.title, v.channel, v.channel_id, v.duration,
                      v.published, v.view_count, v.available
               FROM events e JOIN items i ON i.id = e.item_id JOIN videos v ON v.id = i.video_id
               WHERE i.playlist_id = ? AND e.action != 'added' ORDER BY e.id DESC LIMIT ?""",
            (playlist_id, limit),
        ).fetchall()
    return [{"id": r["event_id"], "action": r["action"], "at": r["at"], "item": db.item_dict(r)} for r in rows]


app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")


# --- cli ---


def port_open():
    with socket.socket() as sock:
        return sock.connect_ex((HOST, PORT)) == 0


def open_hub():
    """Start the server if needed, resync every playlist, open the browser."""
    import requests

    if not port_open():
        log = db.DB_PATH.parent / "serve.log"
        with open(log, "ab") as out:
            subprocess.Popen([sys.executable, __file__, "serve"], stdout=out, stderr=out, start_new_session=True)
        for _ in range(100):
            if port_open():
                break
            time.sleep(0.1)
        else:
            sys.exit(f"server did not come up, see {log}")
    base = f"http://{HOST}:{PORT}"
    for playlist in requests.get(f"{base}/api/state", timeout=10).json()["playlists"]:
        result = requests.post(f"{base}/api/playlists/{playlist['id']}/sync", timeout=120).json()
        print(f"{playlist['title']}: +{result.get('added')} -{result.get('gone')}")
    subprocess.Popen(["xdg-open", f"{base}/"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main(argv):
    db.init()
    cmd = argv[0] if argv else "serve"
    if cmd == "serve":
        if port_open():
            sys.exit(f"already running on http://{HOST}:{PORT}/")
        print(f"http://{HOST}:{PORT}/")
        uvicorn.run(app, host=HOST, port=PORT, log_level="warning")
    elif cmd == "open":
        open_hub()
    elif cmd == "auth":
        ytapi.authorize()
        print(f"token stored in {ytapi.TOKEN}; next sync uses the YouTube API")
    elif cmd == "add" and len(argv) == 2:
        print(add_playlist(PlaylistIn(url=argv[1])))
    elif cmd == "sync":
        with db.connect() as conn:
            ids = [r["id"] for r in conn.execute("SELECT id FROM playlists")]
        for pid in ids:
            result = sync_playlist(pid)
            print(f"{result['playlist']['title']}: +{result['added']} -{result['gone']} = {result['total']}")
        # CLI sync waits for the background lookups so the process can exit cleanly.
        while enriching_count():
            threading.Event().wait(1)
    else:
        sys.exit("usage: hub.py [serve | open | auth | add URL | sync]")


if __name__ == "__main__":
    main(sys.argv[1:])
