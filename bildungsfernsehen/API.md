# API

Backend: `uv run hub.py` on http://127.0.0.1:8765. Serves `static/` at `/`, JSON under `/api/`.

All timestamps ISO 8601 UTC strings. Durations in seconds (integer, may be `null` for unavailable videos).

## Objects

Playlist:
```json
{"id": 1, "yt_id": "PLyu…", "title": "Hobbingen", "url": "https://www.youtube.com/playlist?list=PLyu…",
 "last_synced": "2026-09-17T14:00:00Z", "counts": {"active": 110, "watched": 3, "removed": 2, "gone": 0}}
```

Item (a video on a playlist, carries the per-playlist state):
```json
{"id": 12, "playlist_id": 1, "video_id": "wPhMNx5SsaA",
 "url": "https://www.youtube.com/watch?v=wPhMNx5SsaA",
 "title": "Arktisches Norwegen …", "channel": "ARD Reisen", "channel_id": "UC2k…" ,
 "channel_url": "https://www.youtube.com/channel/UC2k…",
 "duration": 3572, "published": "2025-12-26", "view_count": 105333,
 "thumbnail": "https://i.ytimg.com/vi/wPhMNx5SsaA/mqdefault.jpg",
 "thumbnail_large": "https://i.ytimg.com/vi/wPhMNx5SsaA/hqdefault.jpg",
 "available": true,
 "position": 0, "added_at": "2026-09-17T14:00:00Z",
 "status": "active", "skips": 0, "last_skipped_at": null, "watched_at": null, "removed_at": null}
```
`status` ∈ `active | watched | removed | gone` (`gone` = disappeared from the YouTube playlist on sync while still active).
`published` is `null` until background enrichment fetched it (a minute or two after first sync).
`added_at` is when the hub first saw the item (YouTube does not expose the real add date without an API key).

## Endpoints

- `GET /api/state` → `{"playlists": [Playlist…], "enriching": 0}` — `enriching` = number of videos still waiting for publish-date lookup; poll every few seconds while > 0.
- `POST /api/playlists` body `{"url": "…"}` (full URL or bare list id) → Playlist. Creates and syncs. 400 on bad url, 409 if already added.
- `POST /api/playlists/{id}/sync` → `{"added": 3, "gone": 0, "total": 115, "playlist": Playlist}`.
- `DELETE /api/playlists/{id}` → 204. Deletes playlist and all its items/state.
- `GET /api/playlists/{id}/items` → `[Item…]` all statuses, ordered by position. Client filters and sorts.
- `GET /api/playlists/{id}/pick?min=600&max=3600&channel=NDR%20Doku&channel=The%20B1M&exclude=12` → Item or `null` (JSON `null`, status 200). All params optional; `channel` repeatable; `exclude` = item id not to pick (the currently shown one). Picks uniformly at random among active items matching the filters that have the lowest skip count in that set.
- `POST /api/items/{id}/skip` → Item (skips + 1)
- `POST /api/items/{id}/unskip` → Item (skips − 1, floor 0) — for undo
- `POST /api/items/{id}/watched` → Item (status watched)
- `POST /api/items/{id}/remove` → Item (status removed)
- `POST /api/items/{id}/restore` → Item (status active) — undo for watched/remove/gone
- `GET /api/playlists/{id}/history?limit=50` → `[{"id": 3, "item": Item, "action": "watched", "at": "…"}…]` newest first. Actions: skip, unskip, watched, remove, restore, gone (`added` events are logged but not listed).

Errors: `{"detail": "…"}` with 4xx.
