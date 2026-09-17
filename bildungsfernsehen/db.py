import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "hub.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS playlists (
    id INTEGER PRIMARY KEY,
    yt_id TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    last_synced TEXT
);
CREATE TABLE IF NOT EXISTS videos (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    channel TEXT,
    channel_id TEXT,
    duration INTEGER,
    published TEXT,
    view_count INTEGER,
    available INTEGER NOT NULL DEFAULT 1,
    enriched_at TEXT
);
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY,
    playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
    video_id TEXT NOT NULL REFERENCES videos(id),
    position INTEGER NOT NULL,
    added_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    skips INTEGER NOT NULL DEFAULT 0,
    last_skipped_at TEXT,
    watched_at TEXT,
    removed_at TEXT,
    yt_item_id TEXT,
    UNIQUE (playlist_id, video_id)
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_item ON events(item_id);
"""

_lock = threading.RLock()


def now():
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def init():
    DB_PATH.parent.mkdir(exist_ok=True)
    with _lock:
        conn = sqlite3.connect(DB_PATH)
        conn.executescript(SCHEMA)
        columns = {r[1] for r in conn.execute("PRAGMA table_info(items)")}
        if "yt_item_id" not in columns:
            conn.execute("ALTER TABLE items ADD COLUMN yt_item_id TEXT")
        conn.close()


@contextmanager
def connect():
    # One serialised connection per call; the app is single-user and sqlite hates threads.
    with _lock:
        conn = sqlite3.connect(DB_PATH, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        try:
            conn.execute("BEGIN")
            yield conn
            conn.execute("COMMIT")
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()


ITEM_SQL = """
SELECT i.*, v.title, v.channel, v.channel_id, v.duration, v.published, v.view_count, v.available
FROM items i JOIN videos v ON v.id = i.video_id
"""


def item_dict(row):
    vid = row["video_id"]
    return {
        "id": row["id"],
        "playlist_id": row["playlist_id"],
        "video_id": vid,
        "url": f"https://www.youtube.com/watch?v={vid}",
        "title": row["title"],
        "channel": row["channel"],
        "channel_id": row["channel_id"],
        "channel_url": (
            f"https://www.youtube.com/channel/{row['channel_id']}"
            if row["channel_id"]
            else None
        ),
        "duration": row["duration"],
        "published": row["published"],
        "view_count": row["view_count"],
        "thumbnail": f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
        "thumbnail_large": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
        "available": bool(row["available"]),
        "position": row["position"],
        "added_at": row["added_at"],
        "status": row["status"],
        "skips": row["skips"],
        "last_skipped_at": row["last_skipped_at"],
        "watched_at": row["watched_at"],
        "removed_at": row["removed_at"],
        "on_youtube": row["yt_item_id"] is not None,
    }


def playlist_dict(conn, row):
    counts = {"active": 0, "watched": 0, "removed": 0, "gone": 0}
    for c in conn.execute(
        "SELECT status, COUNT(*) n FROM items WHERE playlist_id = ? GROUP BY status",
        (row["id"],),
    ):
        counts[c["status"]] = c["n"]
    return {
        "id": row["id"],
        "yt_id": row["yt_id"],
        "title": row["title"],
        "url": f"https://www.youtube.com/playlist?list={row['yt_id']}",
        "last_synced": row["last_synced"],
        "counts": counts,
    }


def get_playlist(conn, playlist_id):
    return conn.execute(
        "SELECT * FROM playlists WHERE id = ?", (playlist_id,)
    ).fetchone()


def get_item(conn, item_id):
    return conn.execute(ITEM_SQL + " WHERE i.id = ?", (item_id,)).fetchone()


def log_event(conn, item_id, action):
    conn.execute(
        "INSERT INTO events (item_id, action, at) VALUES (?, ?, ?)",
        (item_id, action, now()),
    )


def upsert_video(conn, entry):
    """Insert or refresh a video row from a flat playlist entry. Enrichment fields are kept."""
    placeholder = (entry.get("title") or "").strip("[]") in (
        "Private video",
        "Deleted video",
    )
    available = bool(entry.get("duration")) or not placeholder
    conn.execute(
        """INSERT INTO videos (id, title, channel, channel_id, duration, view_count, available, published, enriched_at)
           VALUES (:id, :title, :channel, :channel_id, :duration, :view_count, :available, :published, :enriched_at)
           ON CONFLICT(id) DO UPDATE SET
               title = excluded.title,
               channel = COALESCE(excluded.channel, channel),
               channel_id = COALESCE(excluded.channel_id, channel_id),
               duration = COALESCE(excluded.duration, duration),
               view_count = COALESCE(excluded.view_count, view_count),
               available = excluded.available,
               published = COALESCE(:published, published),
               enriched_at = COALESCE(:enriched_at, enriched_at)""",
        {
            "id": entry["id"],
            "title": entry.get("title") or entry["id"],
            "channel": entry.get("channel") or entry.get("uploader"),
            "channel_id": entry.get("channel_id"),
            "duration": int(entry["duration"]) if entry.get("duration") else None,
            "view_count": entry.get("view_count"),
            "available": int(available),
            "published": entry.get("published"),
            "enriched_at": now() if "published" in entry else None,
        },
    )


def apply_sync(conn, playlist_id, entries):
    """Reconcile items with the current YouTube listing. Returns (added, gone)."""
    ts = now()
    seen = set()
    added = 0
    for position, entry in enumerate(entries):
        upsert_video(conn, entry)
        seen.add(entry["id"])
        row = conn.execute(
            "SELECT id, status FROM items WHERE playlist_id = ? AND video_id = ?",
            (playlist_id, entry["id"]),
        ).fetchone()
        # The API knows the real add date and the playlist item id; the yt-dlp listing has neither.
        added_at = entry.get("added_at")
        yt_item_id = entry.get("yt_item_id")
        if row is None:
            cur = conn.execute(
                "INSERT INTO items (playlist_id, video_id, position, added_at, yt_item_id) VALUES (?, ?, ?, ?, ?)",
                (playlist_id, entry["id"], position, added_at or ts, yt_item_id),
            )
            log_event(conn, cur.lastrowid, "added")
            added += 1
        else:
            conn.execute(
                "UPDATE items SET position = ?, added_at = COALESCE(?, added_at), yt_item_id = COALESCE(?, yt_item_id) WHERE id = ?",
                (position, added_at, yt_item_id, row["id"]),
            )
            if row["status"] == "gone":
                # Re-added on YouTube after we flagged it missing.
                conn.execute(
                    "UPDATE items SET status = 'active', removed_at = NULL WHERE id = ?",
                    (row["id"],),
                )
                log_event(conn, row["id"], "restore")
    gone = 0
    for row in conn.execute(
        "SELECT id, video_id FROM items WHERE playlist_id = ? AND status = 'active'",
        (playlist_id,),
    ).fetchall():
        if row["video_id"] not in seen:
            conn.execute(
                "UPDATE items SET status = 'gone', removed_at = ? WHERE id = ?",
                (ts, row["id"]),
            )
            log_event(conn, row["id"], "gone")
            gone += 1
    conn.execute("UPDATE playlists SET last_synced = ? WHERE id = ?", (ts, playlist_id))
    return added, gone


def pending_enrichment(conn):
    """Video ids of available videos that still lack a publish date."""
    return [
        r["id"]
        for r in conn.execute(
            "SELECT id FROM videos WHERE enriched_at IS NULL AND available = 1 AND id IN (SELECT video_id FROM items)"
        )
    ]


def store_enrichment(conn, video_id, info):
    if info is None:
        # Lookup failures (region locks, consent walls) keep the listing's verdict on availability.
        conn.execute(
            "UPDATE videos SET enriched_at = ? WHERE id = ?", (now(), video_id)
        )
        return
    published = info.get("upload_date")
    if published and len(published) == 8:
        published = f"{published[:4]}-{published[4:6]}-{published[6:]}"
    conn.execute(
        """UPDATE videos SET enriched_at = ?, published = ?,
               channel = COALESCE(?, channel), channel_id = COALESCE(?, channel_id),
               duration = COALESCE(?, duration), view_count = COALESCE(?, view_count)
           WHERE id = ?""",
        (
            now(),
            published,
            info.get("channel") or info.get("uploader"),
            info.get("channel_id"),
            int(info["duration"]) if info.get("duration") else None,
            info.get("view_count"),
            video_id,
        ),
    )
