"""Common functionality for mediathekviewweb API."""

import subprocess
from dataclasses import dataclass
from pathlib import Path

import requests


MEDIATHEKVIEWWEB_API = "https://mediathekviewweb.de/api/query"


@dataclass
class MediathekResult:
    """A single result from mediathekviewweb."""
    title: str
    topic: str
    channel: str
    description: str
    duration: int  # in seconds
    timestamp: int
    url_video: str
    url_video_hd: str
    url_video_low: str

    @classmethod
    def from_api(cls, data: dict) -> "MediathekResult":
        return cls(
            title=data.get("title", ""),
            topic=data.get("topic", ""),
            channel=data.get("channel", ""),
            description=data.get("description", ""),
            duration=data.get("duration", 0),
            timestamp=data.get("timestamp", 0),
            url_video=data.get("url_video", ""),
            url_video_hd=data.get("url_video_hd", ""),
            url_video_low=data.get("url_video_low", ""),
        )

    def get_best_url(self) -> str:
        """Return the best available video URL (HD > normal > low)."""
        return self.url_video_hd or self.url_video or self.url_video_low


@dataclass
class DownloadResult:
    """Result of a video download attempt."""
    success: bool
    path: Path | None = None
    duration_seconds: float | None = None
    error: str | None = None

    @property
    def duration_formatted(self) -> str:
        """Return duration as MM:SS string."""
        if self.duration_seconds is None:
            return ""
        minutes = int(self.duration_seconds // 60)
        secs = int(self.duration_seconds % 60)
        return f"{minutes}:{secs:02d}"


def search_mediathekviewweb(
    topic: str,
    title: str | None = None,
    min_duration: int | None = None,
    max_results: int = 10,
    offset: int = 0,
    blocklist: list[str] | None = None,
) -> list[MediathekResult]:
    """Search mediathekviewweb for videos.

    Args:
        topic: The show/topic to search for (e.g., "Die Maus", "tatort")
        title: Optional title to search for within the topic
        min_duration: Minimum duration in seconds (e.g., 4800 for 80 minutes)
        max_results: Maximum number of results to return
        offset: Offset for pagination
        blocklist: List of strings; results with titles containing any of these
            (case-insensitive) will be filtered out

    Returns:
        List of MediathekResult objects
    """
    queries = [{"fields": ["topic"], "query": topic}]
    if title:
        queries.append({"fields": ["title"], "query": title})

    query = {
        "queries": queries,
        "sortBy": "timestamp",
        "sortOrder": "desc",
        "future": "false",
        "offset": offset,
        "size": max_results,
    }
    if min_duration:
        query["duration_min"] = min_duration

    headers = {"Content-Type": "text/plain"}
    response = requests.post(MEDIATHEKVIEWWEB_API, json=query, headers=headers)
    response.raise_for_status()

    data = response.json()
    if data.get("err"):
        raise ValueError(f"API error: {data}")

    results = data.get("result", {}).get("results", [])
    mediathek_results = [MediathekResult.from_api(r) for r in results]

    # Filter by blocklist
    if blocklist:
        blocklist_lower = [b.lower() for b in blocklist]
        mediathek_results = [
            r for r in mediathek_results
            if not any(b in r.title.lower() for b in blocklist_lower)
        ]

    return mediathek_results


def get_video_duration_seconds(video_path: Path) -> float | None:
    """Get video duration in seconds using ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except Exception:
        pass
    return None


def download_mediathek_video(
    result: MediathekResult,
    output_path: Path,
    extract_duration: bool = False,
) -> DownloadResult:
    """Download video from MediathekResult, trying HD -> normal -> low.

    Args:
        result: MediathekResult with video URLs
        output_path: Path where the video should be saved
        extract_duration: If True, extract duration via ffprobe after download

    Returns:
        DownloadResult with success status and optional duration
    """
    urls = [result.url_video_hd, result.url_video, result.url_video_low]
    urls = [u for u in urls if u]

    if not urls:
        return DownloadResult(success=False, error="No video URLs available")

    for video_url in urls:
        try:
            subprocess.run(
                ["yt-dlp", "-o", str(output_path), video_url],
                check=True,
            )
            duration_seconds = None
            if extract_duration and output_path.exists():
                duration_seconds = get_video_duration_seconds(output_path)
            return DownloadResult(
                success=True,
                path=output_path,
                duration_seconds=duration_seconds,
            )
        except subprocess.CalledProcessError:
            # Clean up partial file if it exists
            if output_path.exists():
                output_path.unlink()
            continue

    return DownloadResult(
        success=False,
        error=f"All {len(urls)} URLs failed",
    )
