"""YouTube Data API v3 with OAuth. Optional: only used once `data/token.json` exists (see `hub.py auth`)."""

import json
import re
from pathlib import Path

from google.auth.transport.requests import AuthorizedSession, Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

DATA = Path(__file__).parent / "data"
CLIENT_SECRET = DATA / "client_secret.json"
TOKEN = DATA / "token.json"
SCOPES = ["https://www.googleapis.com/auth/youtube"]
BASE = "https://www.googleapis.com/youtube/v3"

DURATION_RE = re.compile(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


class ApiError(Exception):
    pass


def available():
    return TOKEN.exists()


def authorize():
    if not CLIENT_SECRET.exists():
        raise ApiError(
            f"missing {CLIENT_SECRET}: create an OAuth desktop client in Google Cloud and download its JSON there"
        )
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
    creds = flow.run_local_server(port=0, open_browser=True)
    TOKEN.write_text(creds.to_json())


def _session():
    creds = Credentials.from_authorized_user_file(TOKEN, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN.write_text(creds.to_json())
    return AuthorizedSession(creds)


def _call(method, resource, **kwargs):
    resp = _session().request(method, f"{BASE}/{resource}", **kwargs)
    if resp.status_code >= 400:
        try:
            message = resp.json()["error"]["message"]
        except (ValueError, KeyError):
            message = resp.text[:200]
        raise ApiError(f"{method} {resource}: {resp.status_code} {message}")
    return resp.json() if resp.content else None


def parse_duration(text):
    m = DURATION_RE.fullmatch(text or "")
    if not m:
        return None
    days, hours, minutes, seconds = (int(x or 0) for x in m.groups())
    return ((days * 24 + hours) * 60 + minutes) * 60 + seconds


def _paged(resource, **params):
    token = None
    while True:
        page = _call("GET", resource, params={**params, "maxResults": 50, **({"pageToken": token} if token else {})})
        yield from page.get("items", [])
        token = page.get("nextPageToken")
        if not token:
            return


def fetch_playlist(yt_id):
    """Same shape as `youtube.fetch_playlist`, plus yt_item_id, added_at and published per entry."""
    lists = _call("GET", "playlists", params={"part": "snippet", "id": yt_id}).get("items", [])
    title = lists[0]["snippet"]["title"] if lists else yt_id
    entries = []
    for item in _paged("playlistItems", part="snippet,contentDetails", playlistId=yt_id):
        snippet = item["snippet"]
        entries.append(
            {
                "id": snippet["resourceId"]["videoId"],
                "title": snippet["title"],
                "channel": snippet.get("videoOwnerChannelTitle"),
                "channel_id": snippet.get("videoOwnerChannelId"),
                "duration": None,
                "view_count": None,
                "yt_item_id": item["id"],
                "added_at": snippet["publishedAt"],
                "published": (item.get("contentDetails", {}).get("videoPublishedAt") or "")[:10] or None,
            }
        )
    by_id = {e["id"]: e for e in entries}
    ids = list(by_id)
    for start in range(0, len(ids), 50):
        chunk = ids[start : start + 50]
        videos = _call("GET", "videos", params={"part": "contentDetails,statistics", "id": ",".join(chunk)})
        for video in videos.get("items", []):
            entry = by_id[video["id"]]
            entry["duration"] = parse_duration(video["contentDetails"]["duration"])
            entry["view_count"] = int(video.get("statistics", {}).get("viewCount") or 0) or None
    return title, entries


def delete_item(yt_item_id):
    _call("DELETE", "playlistItems", params={"id": yt_item_id})


def insert_item(playlist_yt_id, video_id):
    body = {"snippet": {"playlistId": playlist_yt_id, "resourceId": {"kind": "youtube#video", "videoId": video_id}}}
    return _call(
        "POST",
        "playlistItems",
        params={"part": "snippet"},
        data=json.dumps(body),
        headers={"Content-Type": "application/json"},
    )["id"]
