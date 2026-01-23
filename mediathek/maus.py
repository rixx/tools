#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "requests",
#     "inquirer",
#     "pillow",
#     "click",
#     "tqdm",
# ]
# ///
"""Download Sachgeschichten from wdrmaus.de"""

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

import click

from lib import search_mediathekviewweb, download_mediathek_video
import inquirer
import requests
from PIL import Image
from tqdm import tqdm

BASE_DIR = Path(__file__).parent
SACHGESCHICHTEN_DIR = BASE_DIR / "sachgeschichten"
JSON_FILE = BASE_DIR / "sachgeschichten.json"
MISSING_FILE = BASE_DIR / "sachgeschichten-missing.json"
INDEX_FILE = BASE_DIR / "index.md"


ORANGE = (255, 165, 0)
BLUE = (0, 150, 214)


@dataclass
class Episode:
    """Unified episode data model."""
    title: str
    year: str = ""  # Original broadcast year (used for filename)
    presenter: str = ""
    duration: str = ""
    description: str = ""
    url: str = ""
    alt_url: str = ""  # @id field
    image_url: str = ""
    date_published: str = ""  # Metadata publication date

    @property
    def slug(self) -> str:
        return get_slug(self.title, self.year)

    @property
    def video_path(self) -> Path:
        return SACHGESCHICHTEN_DIR / f"{self.slug}.mp4"

    @property
    def image_path(self) -> Path:
        return SACHGESCHICHTEN_DIR / f"{self.slug}.webp"

    @property
    def is_downloaded(self) -> bool:
        return self.video_path.exists()

    def has_valid_duration(self) -> bool:
        return self.duration not in (None, "", "NA")

    @classmethod
    def from_metadata(cls, metadata: dict) -> "Episode":
        """Construct from JSON-LD metadata dict."""
        date_str = metadata.get("datePublished", "")
        image_url = (metadata.get("image", {}).get("url") or
                     (metadata.get("thumbnailURL", []) or [None])[0] or "")
        # Prefer originalYear (broadcast year) over datePublished year
        year = metadata.get("originalYear") or (date_str[:4] if date_str else "")
        return cls(
            title=metadata.get("name", ""),
            year=year,
            presenter=metadata.get("presenter", ""),
            duration=metadata.get("duration", ""),
            description=metadata.get("description", ""),
            url=metadata.get("url", ""),
            alt_url=metadata.get("@id", ""),
            image_url=image_url,
            date_published=date_str,
        )

    @classmethod
    def from_missing(cls, entry: dict) -> "Episode":
        """Construct from missing entry dict."""
        return cls(
            title=entry.get("title", ""),
            year=entry.get("year", ""),
            presenter=entry.get("presenter", ""),
        )

    def to_metadata_dict(self) -> dict:
        """Convert to metadata dict format for JSON storage."""
        result = {"name": self.title}
        if self.date_published:
            result["datePublished"] = self.date_published
        # Always save originalYear if it differs from datePublished year
        if self.year and (not self.date_published or self.year != self.date_published[:4]):
            result["originalYear"] = self.year
        if self.description:
            result["description"] = self.description
        if self.presenter:
            result["presenter"] = self.presenter
        if self.duration:
            result["duration"] = self.duration
        if self.url:
            result["url"] = self.url
        if self.alt_url:
            result["@id"] = self.alt_url
        if self.image_url:
            result["image"] = {"url": self.image_url}
        return result

    def to_missing_dict(self) -> dict:
        """Convert to missing entry dict format."""
        result = {"title": self.title, "year": self.year}
        if self.presenter:
            result["presenter"] = self.presenter
        return result

    def merge_from(self, other: "Episode"):
        """Merge non-empty fields from another episode."""
        if not self.presenter and other.presenter:
            self.presenter = other.presenter
        if not self.has_valid_duration() and other.has_valid_duration():
            self.duration = other.duration
        # Prefer other's year if we only have date_published year
        if other.year and self.date_published and self.year == self.date_published[:4]:
            if other.year != self.year:
                self.year = other.year


class EpisodeRepository:
    """Manages episode data with slug-based indexing."""

    def __init__(self):
        self._downloaded: dict[str, Episode] = {}
        self._missing: dict[str, Episode] = {}
        self._downloaded_urls: set[str] = set()  # Normalized URLs for quick lookup
        self.reload()

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Normalize URL for comparison."""
        if not url:
            return ""
        return url.replace("//filme", "/filme").rstrip("/").lower()

    def reload(self):
        self._downloaded.clear()
        self._missing.clear()
        self._downloaded_urls.clear()
        if JSON_FILE.exists():
            for entry in json.loads(JSON_FILE.read_text()):
                ep = Episode.from_metadata(entry)
                self._downloaded[ep.slug] = ep
                # Index by URL for bulk matching
                if ep.url:
                    self._downloaded_urls.add(self._normalize_url(ep.url))
                if ep.alt_url:
                    self._downloaded_urls.add(self._normalize_url(ep.alt_url))
        if MISSING_FILE.exists():
            for entry in json.loads(MISSING_FILE.read_text()):
                ep = Episode.from_missing(entry)
                self._missing[ep.slug] = ep

    def is_url_downloaded(self, url: str) -> bool:
        """Check if a URL is already in the downloaded list."""
        return self._normalize_url(url) in self._downloaded_urls

    def get_by_url(self, url: str) -> Episode | None:
        """Get episode by URL."""
        normalized = self._normalize_url(url)
        for ep in self._downloaded.values():
            if self._normalize_url(ep.url) == normalized or self._normalize_url(ep.alt_url) == normalized:
                return ep
        return None

    def save(self):
        entries = sorted([ep.to_metadata_dict() for ep in self._downloaded.values()],
                        key=lambda x: x.get("name", "").lower())
        JSON_FILE.write_text(json.dumps(entries, indent=2, ensure_ascii=False))

        missing = sorted([ep.to_missing_dict() for ep in self._missing.values()],
                        key=lambda x: x.get("title", "").lower())
        MISSING_FILE.write_text(json.dumps(missing, indent=2, ensure_ascii=False))

    def get_by_slug(self, slug: str) -> Episode | None:
        return self._downloaded.get(slug) or self._missing.get(slug)

    def get_presenter(self, slug: str) -> str:
        ep = self.get_by_slug(slug)
        return ep.presenter if ep else ""

    def upsert_downloaded(self, episode: Episode):
        existing = self._downloaded.get(episode.slug)
        if existing:
            episode.merge_from(existing)
        missing_ep = self._missing.get(episode.slug)
        if missing_ep:
            episode.merge_from(missing_ep)
        self._downloaded[episode.slug] = episode

    def remove_from_missing(self, slug: str):
        self._missing.pop(slug, None)

    def add_to_missing(self, episode: Episode) -> bool:
        """Add episode to missing list. Returns True only if newly added."""
        if episode.slug in self._downloaded:
            return False
        existing = self._missing.get(episode.slug)
        if existing:
            existing.merge_from(episode)
            return False  # Already existed, just merged
        self._missing[episode.slug] = episode
        return True  # Newly added

    def get_all_downloaded(self) -> list[Episode]:
        return list(self._downloaded.values())

    def get_all_missing(self) -> list[Episode]:
        return list(self._missing.values())


def info(msg: str):
    click.echo("  🐭 " + click.style(msg, fg=BLUE))


def success(msg: str):
    click.echo("  🐘 " + click.style(msg, fg=ORANGE))


def warn(msg: str):
    click.echo("  ⚠️  " + click.style(msg, fg="yellow"))


def error(msg: str):
    click.echo("  ❌ " + click.style(msg, fg="red"))


def header(msg: str):
    click.echo()
    click.echo(click.style(f"  {msg}", fg=ORANGE, bold=True))
    click.echo(click.style("  " + "─" * len(msg), fg=ORANGE))


def fix_malformed_json(json_str: str) -> str:
    """Fix unescaped quotes in JSON string values.

    WDR's JSON-LD sometimes contains unescaped quotes inside string values,
    e.g. "description": "He said "hello" to her" - this function escapes them.
    """
    result = []
    in_string = False
    i = 0
    n = len(json_str)

    while i < n:
        char = json_str[i]

        if char == '\\' and i + 1 < n:
            # Escape sequence - keep as is
            result.append(char)
            result.append(json_str[i + 1])
            i += 2
            continue

        if char == '"':
            if not in_string:
                # Starting a string
                in_string = True
                result.append(char)
            else:
                # Could be end of string or unescaped quote inside
                # Look ahead to determine - end of string is followed by : , } ]
                rest = json_str[i + 1:].lstrip()
                if not rest or rest[0] in ',}]:':
                    # This is the end of the string
                    in_string = False
                    result.append(char)
                else:
                    # Unescaped quote inside string - escape it
                    result.append('\\"')
        else:
            result.append(char)

        i += 1

    return ''.join(result)


def fetch_metadata(url: str) -> dict:
    """Fetch and parse JSON-LD metadata from a wdrmaus.de page."""
    response = requests.get(url)
    response.raise_for_status()

    # Find the JSON-LD script tag
    match = re.search(
        r'<script type="application/ld\+json">\s*({.*?})\s*</script>',
        response.text,
        re.DOTALL,
    )
    if not match:
        raise ValueError("Keine JSON-LD Metadaten gefunden")

    json_str = match.group(1)

    # Try normal parsing first, fall back to fixing malformed JSON
    try:
        metadata = json.loads(json_str, strict=False)
    except json.JSONDecodeError:
        json_str = fix_malformed_json(json_str)
        metadata = json.loads(json_str, strict=False)

    # Remove publisher
    metadata.pop("publisher", None)

    return metadata


def get_slug(title: str, year: str = "") -> str:
    """Convert title to slug: lowercase, spaces to dashes, with year appended."""
    slug = title.lower()

    # Replace umlauts and special German characters
    replacements = {
        "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
        "Ä": "ae", "Ö": "oe", "Ü": "ue",
    }
    for char, replacement in replacements.items():
        slug = slug.replace(char, replacement)

    # Remove or replace problematic characters
    slug = slug.replace("'", "").replace("'", "").replace("`", "")
    slug = slug.replace("·", "-").replace("–", "-").replace("—", "-")
    slug = slug.replace("  ", " ").replace(" ", "-")

    # Remove any remaining non-ASCII or problematic characters
    slug = re.sub(r"[^a-z0-9\-]", "", slug)

    # Clean up multiple dashes
    slug = re.sub(r"-+", "-", slug)
    slug = slug.strip("-")

    if year:
        slug = f"{slug}-{year}"
    return slug


def get_year(metadata: dict) -> str:
    """Extract year from datePublished."""
    date_str = metadata.get("datePublished", "")
    if date_str:
        return date_str[:4]
    return ""


def get_video_duration(video_path: Path) -> str:
    """Get video duration in MM:SS format using ffprobe."""
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
            seconds = float(result.stdout.strip())
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{minutes}:{secs:02d}"
    except Exception:
        pass
    return ""


def download_video(url: str, output_path: Path, title: str = "") -> str:
    """Download video using yt-dlp, return duration in MM:SS format.

    If yt-dlp fails and a title is provided, falls back to searching
    mediathekviewweb for "Die Maus" episodes with matching title.
    """
    try:
        subprocess.run(
            ["yt-dlp", "-o", str(output_path), url],
            check=True,
        )
        return get_video_duration(output_path)
    except subprocess.CalledProcessError:
        if not title:
            raise

        # Try mediathekviewweb as fallback
        results = search_mediathekviewweb(
            topic="Die Maus",
            title=title,
            blocklist=["audiodeskription"],
        )

        if not results:
            raise

        # Try each result using shared download function
        for result in results:
            download_result = download_mediathek_video(
                result, output_path, extract_duration=True
            )
            if download_result.success:
                return download_result.duration_formatted

        # All attempts failed
        raise


def download_image(url: str, output_path: Path):
    """Download image and convert to webp."""
    response = requests.get(url)
    response.raise_for_status()

    # Save temporarily then convert
    temp_path = output_path.with_suffix(".tmp")
    temp_path.write_bytes(response.content)

    # Convert to webp
    with Image.open(temp_path) as img:
        img.save(output_path, "WEBP")

    temp_path.unlink()


def build_table(headers: list, data: list) -> str:
    """Build a markdown table with proper alignment."""
    if not data:
        return ""

    # Calculate column widths
    widths = [len(h) for h in headers]
    for row in data:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    # Build table
    def format_row(cells):
        return "| " + " | ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells)) + " |"

    lines = [
        format_row(headers),
        "| " + " | ".join("-" * w for w in widths) + " |",
    ]
    for row in data:
        lines.append(format_row(row))

    return "\n".join(lines)


def update_index(repo: EpisodeRepository):
    """Update the markdown tables in index.md (downloaded and missing separately)."""
    # Build downloaded table
    downloaded_headers = ["Titel", "Jahr", "Autor", "Dauer"]
    downloaded_data = [
        [ep.title, ep.year, ep.presenter, ep.duration]
        for ep in sorted(repo.get_all_downloaded(), key=lambda x: x.title.lower())
    ]
    downloaded_table = build_table(downloaded_headers, downloaded_data)

    # Build missing table
    missing_headers = ["Titel", "Jahr", "Autor"]
    missing_data = [
        [ep.title, ep.year, ep.presenter]
        for ep in sorted(repo.get_all_missing(), key=lambda x: x.title.lower())
    ]
    missing_table = build_table(missing_headers, missing_data)

    # Read current index.md
    content = INDEX_FILE.read_text()

    # Replace downloaded section
    new_content = re.sub(
        r"(<!-- Beginn Sachgeschichtenindex -->\n\n).*?(\n\n<!-- Ende Sachgeschichtenindex -->)",
        rf"\1{downloaded_table}\2",
        content,
        flags=re.DOTALL,
    )

    # Replace or create missing section
    if "<!-- Beginn Fehlt -->" in new_content:
        new_content = re.sub(
            r"(<!-- Beginn Fehlt -->\n\n).*?(\n\n<!-- Ende Fehlt -->)",
            rf"\1{missing_table}\2",
            new_content,
            flags=re.DOTALL,
        )
    else:
        # Add missing section at end
        new_content = new_content.rstrip() + "\n\n\n## Fehlt\n\n<!-- Beginn Fehlt -->\n\n" + missing_table + "\n\n<!-- Ende Fehlt -->\n"

    INDEX_FILE.write_text(new_content)


def download_episode(
    url: str,
    repo: EpisodeRepository,
    presenter: str = "",
    interactive: bool = False,
    original_year: str = "",
) -> tuple[bool, Episode | None]:
    """
    Core download logic. Returns (success, episode).
    original_year: If provided (from A-Z page), use this instead of metadata year.
    """
    metadata = fetch_metadata(url)  # Let exceptions propagate
    episode = Episode.from_metadata(metadata)

    # Use original broadcast year if provided (from A-Z page)
    if original_year and original_year != episode.year:
        episode.year = original_year

    # Already downloaded?
    if episode.is_downloaded:
        existing = repo.get_by_slug(episode.slug)
        if existing:
            if not existing.has_valid_duration():
                existing.duration = get_video_duration(episode.video_path)
                repo.save()
            return True, existing
        # File exists but no JSON entry
        episode.duration = get_video_duration(episode.video_path)
        if presenter:
            episode.presenter = presenter
        repo.upsert_downloaded(episode)
        repo.remove_from_missing(episode.slug)
        repo.save()
        return True, episode

    # Set presenter
    if presenter:
        episode.presenter = presenter
    elif interactive:
        result = ask_presenter(episode.title, episode.year)
        if result is None:
            return False, None  # Cancelled
        episode.presenter = result
    else:
        episode.presenter = repo.get_presenter(episode.slug)

    # Download video
    episode.duration = download_video(url, episode.video_path, title=episode.title)

    # Download image (non-fatal)
    if episode.image_url:
        try:
            download_image(episode.image_url, episode.image_path)
        except Exception:
            pass

    # Save
    repo.upsert_downloaded(episode)
    repo.remove_from_missing(episode.slug)
    repo.save()

    return True, episode


def process_url(url: str) -> bool:
    """Process a single URL. Returns True on success, False on failure."""
    repo = EpisodeRepository()
    episode = None
    try:
        # Fetch metadata for display
        info(f"Lade Metadaten von {url}")
        metadata = fetch_metadata(url)
        episode = Episode.from_metadata(metadata)

        header(f"{episode.title} ({episode.year})")
        if episode.description:
            click.echo(click.style("  ", fg="white") + episode.description[:100] + "...")
        click.echo()

        # Check if already downloaded
        if episode.is_downloaded:
            info("Bereits vorhanden, überspringe Download")
            existing = repo.get_by_slug(episode.slug)
            if existing and not existing.has_valid_duration():
                duration = get_video_duration(episode.video_path)
                if duration:
                    existing.duration = duration
                    repo.save()
                    update_index(repo)
                    info(f"Dauer ergänzt: {duration}")
            return True

        # Ask for presenter
        presenter_questions = [
            inquirer.List(
                "presenter",
                message="Wer moderiert?",
                choices=["Christoph", "Armin", "Ralph", "Clarissa", "Siham", "Johannes", "Andre", "Jana", "Andere", "Unbekannt"],
                carousel=True,
            ),
        ]
        presenter_answer = inquirer.prompt(presenter_questions)
        if not presenter_answer:
            warn("Abgebrochen")
            return False

        presenter = presenter_answer["presenter"]
        if presenter == "Unbekannt":
            presenter = "-"
        elif presenter == "Andere":
            other_q = [inquirer.Text("presenter", message="Name eingeben")]
            other_answer = inquirer.prompt(other_q)
            if not other_answer:
                warn("Abgebrochen")
                return False
            presenter = other_answer["presenter"]

        episode.presenter = presenter

        # Download video
        info(f"Lade Video herunter: {episode.video_path.name}")
        episode.duration = download_video(url, episode.video_path, title=episode.title)
        success(f"Video heruntergeladen ({episode.duration})")

        # Download image
        if episode.image_url:
            info(f"Lade Bild herunter: {episode.image_path.name}")
            try:
                download_image(episode.image_url, episode.image_path)
                success("Bild als WebP gespeichert")
            except Exception:
                pass

        # Save to repository
        repo.upsert_downloaded(episode)
        repo.remove_from_missing(episode.slug)
        repo.save()
        success("sachgeschichten.json aktualisiert")

        # Update index
        update_index(repo)
        success("index.md aktualisiert")

        click.echo()
        click.echo(click.style("  ══════════════════════════════════════", fg=ORANGE))
        click.echo(click.style(f"  🐘 Erfolgreich hinzugefügt: {episode.title}", fg=ORANGE, bold=True))
        click.echo(click.style("  ══════════════════════════════════════", fg=ORANGE))
        click.echo()

        return True

    except requests.RequestException as e:
        error(f"URL konnte nicht geladen werden: {e}")
        return False
    except ValueError as e:
        error(f"Metadaten konnten nicht gelesen werden: {e}")
        return False
    except subprocess.CalledProcessError as e:
        error(f"Video-Download fehlgeschlagen: {e}")
        # Save presenter info to missing list so user doesn't have to re-enter it
        if episode is not None and episode.presenter:
            repo.add_to_missing(episode)
            repo.save()
            info("Moderator für Fehlt-Liste gespeichert")
            update_index(repo)
        return False
    except Exception as e:
        error(f"Unerwarteter Fehler: {e}")
        # Save presenter info to missing list so user doesn't have to re-enter it
        if episode is not None and episode.presenter:
            repo.add_to_missing(episode)
            repo.save()
            info("Moderator für Fehlt-Liste gespeichert")
            update_index(repo)
        return False


def parse_filter_letters(url: str) -> list[str]:
    """Parse the filter letters from the A-Z main page and return list of filter URLs."""
    response = requests.get(url)
    response.raise_for_status()

    # Find all filter letter links in <ul class="filterbuchstaben">
    # Pattern: <a href="../../filme/sachgeschichten/a-bis-z.php5?filter=X">X</a>
    pattern = r'<ul class="filterbuchstaben">.*?</ul>'
    ul_match = re.search(pattern, response.text, re.DOTALL)
    if not ul_match:
        raise ValueError("Could not find filterbuchstaben list")

    ul_content = ul_match.group(0)

    # Extract all filter URLs
    link_pattern = r'<a href="([^"]+\?filter=[^"]+)">'
    filter_urls = []
    for match in re.finditer(link_pattern, ul_content):
        href = match.group(1)
        full_url = urljoin(url, href)
        filter_urls.append(full_url)

    return filter_urls


def parse_bulk_page(url: str) -> tuple[list[dict], list[dict]]:
    """Parse an A-Z list page and return (available, missing) episodes."""
    response = requests.get(url)
    response.raise_for_status()

    available = []
    missing = []

    # Find all list items in the abiszAusgabe section
    # Available: <li><a class="intern" href="..."><span class="abiszTitel">Title <span class="abiszJahr">(2020)</span></span></a></li>
    # Missing: <li><span><span class="abiszTitel">Title <span class="abiszJahr">(1990)</span></span></span></li>

    # Match available (with links)
    available_pattern = r'<a class="intern" href="([^"]+)"[^>]*><span class="abiszTitel">(?:<i></i>)?([^<]+)\s*<span class="abiszJahr">\((\d{4})\)</span>'
    for match in re.finditer(available_pattern, response.text):
        href, title, year = match.groups()
        full_url = urljoin(url, href)
        available.append({
            "title": title.strip(),
            "year": year,
            "url": full_url,
        })

    # Match missing (no links) - span directly inside li, not inside a
    missing_pattern = r'<li><span><span class="abiszTitel">([^<]+)\s*<span class="abiszJahr">\((\d{4})\)</span>'
    for match in re.finditer(missing_pattern, response.text):
        title, year = match.groups()
        missing.append({
            "title": title.strip(),
            "year": year,
        })

    return available, missing


def process_url_auto(url: str, presenter: str = "", repo: EpisodeRepository | None = None, original_year: str = "") -> bool:
    """Process a URL without interactive prompts. Returns True on success."""
    if repo is None:
        repo = EpisodeRepository()
    try:
        success, _ = download_episode(url, repo, presenter=presenter, interactive=False, original_year=original_year)
        return success
    except Exception:
        return False


@click.group()
def cli():
    """🐭 Sachgeschichten Downloader für wdrmaus.de 🐘"""
    SACHGESCHICHTEN_DIR.mkdir(exist_ok=True)


@cli.command()
def download():
    """Interaktiver Modus: Einzelne Folgen herunterladen."""
    click.echo()
    click.echo(click.style("  ╔═══════════════════════════════════════╗", fg=ORANGE))
    click.echo(click.style("  ║   🐭 Sachgeschichten Downloader 🐘    ║", fg=ORANGE))
    click.echo(click.style("  ║   'q' zum Beenden                     ║", fg=ORANGE))
    click.echo(click.style("  ╚═══════════════════════════════════════╝", fg=ORANGE))

    while True:
        click.echo()
        url = click.prompt(
            click.style("  URL", fg="yellow"),
            default="",
            show_default=False,
        ).strip()

        if not url:
            continue

        if url.lower() == "q":
            click.echo()
            info("Tschüss!")
            click.echo()
            break

        process_url(url)


def ask_presenter(title: str, year: str) -> str | None:
    """Ask user for presenter. Returns None if cancelled."""
    click.echo()
    click.echo(click.style(f"  {title} ({year})", fg=ORANGE))
    presenter_questions = [
        inquirer.List(
            "presenter",
            message=f"Wer moderiert '{title}' ({year})?",
            choices=["Christoph", "Armin", "Ralph", "Clarissa", "Siham", "Johannes", "Andre", "Jana", "Laura", "Andere", "Unbekannt", "Überspringen"],
            carousel=True,
        ),
    ]
    presenter_answer = inquirer.prompt(presenter_questions)
    if not presenter_answer:
        return None

    presenter = presenter_answer["presenter"]
    if presenter == "Überspringen":
        return ""
    if presenter == "Unbekannt":
        return "-"
    if presenter == "Andere":
        other_q = [inquirer.Text("presenter", message="Name eingeben")]
        other_answer = inquirer.prompt(other_q)
        if not other_answer:
            return None
        presenter = other_answer["presenter"]

    return presenter


def process_bulk_url(url: str, no_download: bool, no_interactive: bool, repo: EpisodeRepository) -> bool:
    """Process a single bulk URL. Returns True on success, False if cancelled."""
    info(f"Lese {url}")

    try:
        available, missing_episodes = parse_bulk_page(url)
    except Exception as e:
        error(f"Fehler beim Einlesen: {e}")
        return True  # Continue with other URLs

    success(f"Gefunden: {len(available)} verfügbar, {len(missing_episodes)} nicht verfügbar")

    # Add missing episodes
    if missing_episodes:
        added = 0
        for ep_data in missing_episodes:
            if repo.add_to_missing(Episode.from_missing(ep_data)):
                added += 1
        if added:
            success(f"{added} neue Folgen zur Fehlt-Liste hinzugefügt")
        else:
            info("Keine neuen fehlenden Folgen")

    # Download available episodes
    if not no_download and available:
        click.echo()
        header("Lade verfügbare Folgen herunter")

        # Filter out already downloaded by URL (more reliable than slug since titles can differ)
        # Don't skip episodes in missing list - they may be failed downloads that should be retried
        # (Episodes truly unavailable from WDR won't appear in 'available' anyway - they have no URL)
        to_download = [
            ep for ep in available
            if not repo.is_url_downloaded(ep["url"])
        ]

        # Update missing durations for already downloaded episodes
        updated_durations = 0
        for downloaded_ep in repo.get_all_downloaded():
            if not downloaded_ep.has_valid_duration() and downloaded_ep.video_path.exists():
                duration = get_video_duration(downloaded_ep.video_path)
                if duration:
                    downloaded_ep.duration = duration
                    updated_durations += 1
        if updated_durations:
            repo.save()
            success(f"Dauer für {updated_durations} Folgen ergänzt")

        # Collect episodes that need presenter info (including already downloaded ones without presenter)
        presenter_map = {}  # title -> presenter

        if not no_interactive:
            # Find episodes needing presenter info (check by URL for reliability)
            need_presenter = []
            for ep in available:
                # Check downloaded episodes by URL
                existing_ep = repo.get_by_url(ep["url"])
                if existing_ep and existing_ep.presenter:
                    continue
                # Check missing list by slug (failed downloads are stored there)
                slug = get_slug(ep["title"], ep["year"])
                missing_ep = repo._missing.get(slug)
                if missing_ep and missing_ep.presenter:
                    continue
                need_presenter.append(ep)

            if need_presenter:
                click.echo()
                header(f"Moderator für {len(need_presenter)} Folgen angeben")
                info("'Überspringen' um ohne Moderator fortzufahren")

                for ep in need_presenter:
                    presenter = ask_presenter(ep["title"], ep["year"])
                    if presenter is None:  # Cancelled
                        warn("Abgebrochen")
                        return False  # User cancelled
                    if presenter:  # Not skipped
                        presenter_map[ep["title"].lower()] = presenter

                        # Update existing entries that already have files but no presenter
                        existing_ep = repo.get_by_url(ep["url"])
                        if existing_ep and existing_ep.is_downloaded:
                            existing_ep.presenter = presenter
                            repo.save()

        if not to_download:
            info("Alle verfügbaren Folgen bereits heruntergeladen")
        else:
            titles = ", ".join(ep["title"] for ep in to_download)
            info(f"Lade {len(to_download)} neue Folgen herunter: {titles}")
            click.echo()

            downloaded_count = 0
            failed = []

            for ep in tqdm(to_download, desc="  🐭 Lädt", unit=" Folge"):
                presenter = presenter_map.get(ep["title"].lower(), "")
                if process_url_auto(ep["url"], presenter=presenter, repo=repo, original_year=ep["year"]):
                    downloaded_count += 1
                else:
                    failed.append(ep)

            click.echo()
            success(f"{downloaded_count}/{len(to_download)} Folgen heruntergeladen")

            if failed:
                # Add failed episodes to missing list (include presenter if available)
                for ep in failed:
                    presenter = presenter_map.get(ep["title"].lower(), "")
                    failed_ep = Episode(title=ep["title"], year=ep["year"], presenter=presenter)
                    repo.add_to_missing(failed_ep)
                repo.save()
                warn(f"Fehlgeschlagen (zur Fehlt-Liste hinzugefügt): {', '.join(ep['title'] for ep in failed)}")

    return True


@cli.command()
@click.argument("url")
@click.option("--no-download", is_flag=True, help="Nicht herunterladen, nur Fehlt-Liste füllen")
@click.option("--no-interactive", is_flag=True, help="Keine Rückfragen (Moderator wird nicht abgefragt)")
def bulk(url: str, no_download: bool, no_interactive: bool):
    """Massen-Import: A-Z Seite einlesen, fehlende Liste füllen, verfügbare herunterladen."""
    click.echo()
    click.echo(click.style("  ╔═══════════════════════════════════════╗", fg=ORANGE))
    click.echo(click.style("  ║   🐭 Sachgeschichten Bulk Import 🐘   ║", fg=ORANGE))
    click.echo(click.style("  ╚═══════════════════════════════════════╝", fg=ORANGE))
    click.echo()

    repo = EpisodeRepository()

    if not process_bulk_url(url, no_download, no_interactive, repo):
        return

    # Update index at the end
    repo.save()
    update_index(repo)
    success("index.md aktualisiert")

    click.echo()
    info("Fertig!")
    click.echo()


@cli.command()
@click.option("--no-download", is_flag=True, help="Nicht herunterladen, nur Fehlt-Liste füllen")
@click.option("--no-interactive", is_flag=True, help="Keine Rückfragen (Moderator wird nicht abgefragt)")
def all(no_download: bool, no_interactive: bool):
    """Alle Buchstaben: A-Z Seite laden und alle Buchstaben-Filter durchgehen."""
    click.echo()
    click.echo(click.style("  ╔═══════════════════════════════════════╗", fg=ORANGE))
    click.echo(click.style("  ║   🐭 Sachgeschichten Komplett 🐘      ║", fg=ORANGE))
    click.echo(click.style("  ╚═══════════════════════════════════════╝", fg=ORANGE))
    click.echo()

    base_url = "https://www.wdrmaus.de/filme/sachgeschichten/a-bis-z.php5"
    repo = EpisodeRepository()

    info(f"Lese Filter-Buchstaben von {base_url}")

    try:
        filter_urls = parse_filter_letters(base_url)
    except Exception as e:
        error(f"Fehler beim Einlesen der Filter: {e}")
        return

    success(f"Gefunden: {len(filter_urls)} Filter (Buchstaben/Zahlen)")
    click.echo()

    for i, filter_url in enumerate(filter_urls, 1):
        # Extract filter letter for display
        filter_char = filter_url.split("filter=")[-1].upper()
        header(f"[{i}/{len(filter_urls)}] Buchstabe: {filter_char}")

        if not process_bulk_url(filter_url, no_download, no_interactive, repo):
            warn("Abgebrochen")
            break

        click.echo()

    # Update index at the end
    repo.save()
    update_index(repo)
    success("index.md aktualisiert")

    click.echo()
    info("Fertig!")
    click.echo()


if __name__ == "__main__":
    cli()
