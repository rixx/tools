import re
from urllib.parse import parse_qs, urlparse

import yt_dlp

PLAYLIST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,}$")


def parse_playlist_id(text):
    text = text.strip()
    if PLAYLIST_ID_RE.match(text) and not text.startswith("http"):
        return text
    qs = parse_qs(urlparse(text).query)
    if qs.get("list"):
        return qs["list"][0]
    raise ValueError("no playlist id found")


def _ydl(**extra):
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noprogress": True}
    opts.update(extra)
    return yt_dlp.YoutubeDL(opts)


def fetch_playlist(yt_id):
    """Flat listing: title plus one entry per video with basic metadata. Seconds, not minutes."""
    with _ydl(extract_flat=True) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/playlist?list={yt_id}", download=False)
    entries = [e for e in info.get("entries") or [] if e and e.get("id")]
    return info.get("title") or yt_id, entries


def fetch_video(video_id):
    """Full metadata for one video, or None when unavailable."""
    try:
        with _ydl(noplaylist=True) as ydl:
            return ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
    except yt_dlp.utils.DownloadError:
        return None
