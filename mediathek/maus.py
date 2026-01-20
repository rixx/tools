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
from pathlib import Path
from urllib.parse import urljoin

import click
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


def download_video(url: str, output_path: Path) -> str:
    """Download video using yt-dlp, return duration in MM:SS format."""
    # Download the video
    subprocess.run(
        ["yt-dlp", "-o", str(output_path), url],
        check=True,
    )

    # Get duration from downloaded file
    return get_video_duration(output_path)


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


def load_json() -> list:
    """Load existing JSON data."""
    if JSON_FILE.exists():
        with open(JSON_FILE) as f:
            return json.load(f)
    return []


def save_json(data: list):
    """Save JSON data, sorted by title."""
    sorted_data = sorted(data, key=lambda x: x.get("name", "").lower())
    with open(JSON_FILE, "w") as f:
        json.dump(sorted_data, f, indent=2, ensure_ascii=False)


def upsert_entry(metadata: dict):
    """Add or update an entry in the JSON data by slug (title+year), preserving local fields."""
    entries = load_json()
    title = metadata.get("name", "")
    year = get_year(metadata)
    new_slug = get_slug(title, year)

    # Find existing entry by slug and preserve local fields (presenter, duration)
    existing = None
    for e in entries:
        entry_slug = get_slug(e.get("name", ""), get_year(e))
        if entry_slug == new_slug:
            existing = e
            break

    # Preserve presenter and duration from existing entry if not in new metadata
    if existing:
        if not metadata.get("presenter") and existing.get("presenter"):
            metadata["presenter"] = existing["presenter"]
        if not metadata.get("duration") and existing.get("duration"):
            metadata["duration"] = existing["duration"]

    # Also check missing list for presenter if still not set
    if not metadata.get("presenter"):
        missing = load_missing()
        for m in missing:
            if m.get("title", "").lower() == title.lower():
                if m.get("presenter"):
                    metadata["presenter"] = m["presenter"]
                break

    # Remove existing entry with same slug
    entries = [e for e in entries if get_slug(e.get("name", ""), get_year(e)) != new_slug]

    # Add new entry
    entries.append(metadata)
    save_json(entries)
    return entries


def is_already_downloaded(title: str, year: str = "") -> bool:
    """Check if an episode is already downloaded (file exists)."""
    slug = get_slug(title, year)
    video_path = SACHGESCHICHTEN_DIR / f"{slug}.mp4"
    return video_path.exists()


def load_missing() -> list:
    """Load missing episodes list."""
    if MISSING_FILE.exists():
        with open(MISSING_FILE) as f:
            return json.load(f)
    return []


def save_missing(data: list):
    """Save missing episodes list, sorted by title."""
    sorted_data = sorted(data, key=lambda x: x.get("title", "").lower())
    with open(MISSING_FILE, "w") as f:
        json.dump(sorted_data, f, indent=2, ensure_ascii=False)


def remove_from_missing(title: str):
    """Remove an entry from missing list by title."""
    missing = load_missing()
    missing = [m for m in missing if m.get("title", "").lower() != title.lower()]
    save_missing(missing)


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


def update_index(entries: list):
    """Update the markdown tables in index.md (downloaded and missing separately)."""
    missing = load_missing()

    # Build downloaded table
    downloaded_headers = ["Titel", "Jahr", "Autor", "Dauer"]
    downloaded_data = []
    for entry in sorted(entries, key=lambda x: x.get("name", "").lower()):
        downloaded_data.append([
            entry.get("name", ""),
            get_year(entry),
            entry.get("presenter", ""),
            entry.get("duration", ""),
        ])
    downloaded_table = build_table(downloaded_headers, downloaded_data)

    # Build missing table
    missing_headers = ["Titel", "Jahr", "Autor"]
    missing_data = []
    for entry in sorted(missing, key=lambda x: x.get("title", "").lower()):
        missing_data.append([
            entry.get("title", ""),
            entry.get("year", ""),
            entry.get("presenter", ""),
        ])
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


def process_url(url: str) -> bool:
    """Process a single URL. Returns True on success, False on failure."""
    try:
        # Fetch metadata
        info(f"Lade Metadaten von {url}")
        metadata = fetch_metadata(url)

        title = metadata.get("name", "Unbekannt")
        year = get_year(metadata)
        description = metadata.get("description", "")

        header(f"{title} ({year})")
        if description:
            click.echo(click.style("  ", fg="white") + description[:100] + "...")
        click.echo()

        # Check if already downloaded
        if is_already_downloaded(title, year):
            info(f"Bereits vorhanden, überspringe Download")
            # Check if duration is missing and update if needed
            slug = get_slug(title, year)
            video_path = SACHGESCHICHTEN_DIR / f"{slug}.mp4"
            entries = load_json()
            for entry in entries:
                if entry.get("name", "").lower() == title.lower():
                    if entry.get("duration") in (None, "", "NA"):
                        duration = get_video_duration(video_path)
                        if duration:
                            entry["duration"] = duration
                            save_json(entries)
                            update_index(entries)
                            info(f"Dauer ergänzt: {duration}")
                    break
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

        metadata["presenter"] = presenter

        slug = get_slug(title, year)
        video_path = SACHGESCHICHTEN_DIR / f"{slug}.mp4"
        image_path = SACHGESCHICHTEN_DIR / f"{slug}.webp"

        # Download video
        info(f"Lade Video herunter: {video_path.name}")
        duration = download_video(url, video_path)
        metadata["duration"] = duration
        success(f"Video heruntergeladen ({duration})")

        # Download image
        image_url = metadata.get("image", {}).get("url") or (
            metadata.get("thumbnailURL", [None])[0] if metadata.get("thumbnailURL") else None
        )
        if image_url:
            info(f"Lade Bild herunter: {image_path.name}")
            download_image(image_url, image_path)
            success("Bild als WebP gespeichert")

        # Update JSON (upsert to avoid duplicates)
        entries = upsert_entry(metadata)
        success("sachgeschichten.json aktualisiert")

        # Remove from missing if present
        remove_from_missing(title)

        # Update index
        update_index(entries)
        success("index.md aktualisiert")

        click.echo()
        click.echo(click.style("  ══════════════════════════════════════", fg=ORANGE))
        click.echo(click.style(f"  🐘 Erfolgreich hinzugefügt: {title}", fg=ORANGE, bold=True))
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
        if metadata.get("presenter"):
            entry = {"title": title, "year": year, "presenter": metadata["presenter"]}
            add_to_missing([entry])
            info("Moderator für Fehlt-Liste gespeichert")
            update_index(load_json())
        return False
    except Exception as e:
        error(f"Unerwarteter Fehler: {e}")
        # Save presenter info to missing list so user doesn't have to re-enter it
        if 'metadata' in locals() and metadata.get("presenter"):
            entry = {"title": metadata.get("name", ""), "year": get_year(metadata), "presenter": metadata["presenter"]}
            add_to_missing([entry])
            info("Moderator für Fehlt-Liste gespeichert")
            update_index(load_json())
        return False


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


def add_to_missing(entries: list[dict]):
    """Add entries to missing list if not already present, or update presenter if missing."""
    current = load_missing()
    current_by_title = {m.get("title", "").lower(): m for m in current}

    # Also check downloaded
    downloaded = load_json()
    downloaded_titles = {d.get("name", "").lower() for d in downloaded}

    added = 0
    for entry in entries:
        title_lower = entry.get("title", "").lower()
        if title_lower in downloaded_titles:
            continue  # Already downloaded, skip

        if title_lower in current_by_title:
            # Update presenter if we have it and existing entry doesn't
            existing = current_by_title[title_lower]
            if entry.get("presenter") and not existing.get("presenter"):
                existing["presenter"] = entry["presenter"]
        else:
            current.append(entry)
            current_by_title[title_lower] = entry
            added += 1

    save_missing(current)
    return added


def process_url_auto(url: str, presenter: str = "") -> bool:
    """Process a URL without interactive prompts. Returns True on success."""
    try:
        metadata = fetch_metadata(url)
        title = metadata.get("name", "Unbekannt")
        year = get_year(metadata)

        # Check if already downloaded (file exists)
        if is_already_downloaded(title, year):
            slug = get_slug(title, year)
            video_path = SACHGESCHICHTEN_DIR / f"{slug}.mp4"

            # Check if entry exists in JSON by slug (title + year) - if not, add it
            entries = load_json()
            matching_entry = None
            for e in entries:
                entry_slug = get_slug(e.get("name", ""), get_year(e))
                if entry_slug == slug:
                    matching_entry = e
                    break

            if not matching_entry:
                # File exists but JSON entry is missing - add it
                if presenter:
                    metadata["presenter"] = presenter
                metadata["duration"] = get_video_duration(video_path)
                upsert_entry(metadata)
                remove_from_missing(title)
            else:
                # Entry exists - just update duration if missing
                if matching_entry.get("duration") in (None, "", "NA"):
                    duration = get_video_duration(video_path)
                    if duration:
                        matching_entry["duration"] = duration
                        save_json(entries)
            return True

        if presenter:
            metadata["presenter"] = presenter

        slug = get_slug(title, year)
        video_path = SACHGESCHICHTEN_DIR / f"{slug}.mp4"
        image_path = SACHGESCHICHTEN_DIR / f"{slug}.webp"

        # Download video
        duration = download_video(url, video_path)
        metadata["duration"] = duration

        # Download image
        image_url = metadata.get("image", {}).get("url") or (
            metadata.get("thumbnailURL", [None])[0] if metadata.get("thumbnailURL") else None
        )
        if image_url:
            download_image(image_url, image_path)

        # Update JSON (upsert to avoid duplicates)
        upsert_entry(metadata)

        # Remove from missing if present
        remove_from_missing(title)

        return True

    except Exception as e:
        import traceback
        warn(f"DEBUG: Fehler bei {url}: {e}")
        warn(f"DEBUG: {traceback.format_exc()}")
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


def get_existing_presenter(title: str) -> str | None:
    """Get presenter for a title from existing JSON data or missing list, or None if not set."""
    # Check downloaded entries
    entries = load_json()
    for entry in entries:
        if entry.get("name", "").lower() == title.lower():
            presenter = entry.get("presenter", "")
            if presenter:
                return presenter

    # Check missing entries
    missing = load_missing()
    for entry in missing:
        if entry.get("title", "").lower() == title.lower():
            presenter = entry.get("presenter", "")
            if presenter:
                return presenter

    return None


def ask_presenter(title: str, year: str) -> str | None:
    """Ask user for presenter. Returns None if cancelled."""
    click.echo()
    click.echo(click.style(f"  {title} ({year})", fg=ORANGE))
    presenter_questions = [
        inquirer.List(
            "presenter",
            message="Wer moderiert?",
            choices=["Christoph", "Armin", "Ralph", "Clarissa", "Siham", "Johannes", "Andre", "Jana", "Andere", "Unbekannt", "Überspringen"],
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

    info(f"Lese {url}")

    try:
        available, missing_episodes = parse_bulk_page(url)
    except Exception as e:
        error(f"Fehler beim Einlesen: {e}")
        return

    success(f"Gefunden: {len(available)} verfügbar, {len(missing_episodes)} nicht verfügbar")

    # Add missing episodes
    if missing_episodes:
        added = add_to_missing(missing_episodes)
        if added:
            success(f"{added} neue Folgen zur Fehlt-Liste hinzugefügt")
        else:
            info("Keine neuen fehlenden Folgen")

    # Download available episodes
    if not no_download and available:
        click.echo()
        header("Lade verfügbare Folgen herunter")

        # Filter out already downloaded - use URL for matching since titles
        # can differ between A-Z listing and actual episode metadata
        downloaded_entries = load_json()
        downloaded_urls = set()
        for d in downloaded_entries:
            # Normalize URLs (remove double slashes, trailing slashes)
            for key in ("url", "@id"):
                if url_val := d.get(key):
                    downloaded_urls.add(url_val.replace("//filme", "/filme").rstrip("/").lower())
        to_download = [
            ep for ep in available
            if ep["url"].rstrip("/").lower() not in downloaded_urls
        ]

        # Update missing durations for already downloaded episodes
        updated_durations = 0
        url_to_entry = {
            d.get("url", "").replace("//filme", "/filme").rstrip("/").lower(): d
            for d in downloaded_entries
        }
        for ep in available:
            ep_url = ep["url"].rstrip("/").lower()
            if ep_url in url_to_entry:
                entry = url_to_entry[ep_url]
                if entry.get("duration") in (None, "", "NA"):
                    slug = get_slug(entry.get("name", ""), get_year(entry))
                    video_path = SACHGESCHICHTEN_DIR / f"{slug}.mp4"
                    if video_path.exists():
                        duration = get_video_duration(video_path)
                        if duration:
                            entry["duration"] = duration
                            updated_durations += 1
        if updated_durations:
            save_json(downloaded_entries)
            success(f"Dauer für {updated_durations} Folgen ergänzt")

        # Collect episodes that need presenter info (including already downloaded ones without presenter)
        presenter_map = {}  # title -> presenter

        if not no_interactive:
            # Find episodes needing presenter info
            need_presenter = []
            for ep in available:
                existing = get_existing_presenter(ep["title"])
                if existing is None:  # No presenter info yet
                    need_presenter.append(ep)

            if need_presenter:
                click.echo()
                header(f"Moderator für {len(need_presenter)} Folgen angeben")
                info("'Überspringen' um ohne Moderator fortzufahren")

                for ep in need_presenter:
                    presenter = ask_presenter(ep["title"], ep["year"])
                    if presenter is None:  # Cancelled
                        warn("Abgebrochen")
                        return
                    if presenter:  # Not skipped
                        presenter_map[ep["title"].lower()] = presenter

                        # Update existing entries that already have files but no presenter
                        if is_already_downloaded(ep["title"], ep["year"]):
                            entries = load_json()
                            for entry in entries:
                                if entry.get("name", "").lower() == ep["title"].lower():
                                    entry["presenter"] = presenter
                                    break
                            save_json(entries)

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
                if process_url_auto(ep["url"], presenter=presenter):
                    downloaded_count += 1
                else:
                    failed.append(ep)

            click.echo()
            success(f"{downloaded_count}/{len(to_download)} Folgen heruntergeladen")

            if failed:
                # Add failed episodes to missing list (include presenter if available)
                failed_for_missing = []
                for ep in failed:
                    entry = {"title": ep["title"], "year": ep["year"]}
                    presenter = presenter_map.get(ep["title"].lower(), "")
                    if presenter:
                        entry["presenter"] = presenter
                    failed_for_missing.append(entry)
                add_to_missing(failed_for_missing)
                warn(f"Fehlgeschlagen (zur Fehlt-Liste hinzugefügt): {', '.join(ep['title'] for ep in failed)}")

    # Update index at the end
    update_index(load_json())
    success("index.md aktualisiert")

    click.echo()
    info("Fertig!")
    click.echo()


if __name__ == "__main__":
    cli()
