import csv
import json
import os
import re
import subprocess
import sys
from contextlib import suppress
from pathlib import Path

import bs4
import inquirer
import requests
from openpyxl import load_workbook

CWD = Path(os.getcwd())
CSV_PATH = Path(__file__).parent / "episodes.csv"
SPREADSHEET_PATH = "/home/rixx/lib/movies/tatort.xlsx"
EPISODES = []
KNOWN_BAD = (
    # kein tatort
    "die-professorin-tatort-ölfeld",
    # existiert 2x
    "taxi-nach-leipzig",
    "aus-der-traum",
)
OFFSET = int(os.environ.get("OFFSET") or 0)


def check_youtube_dl():
    try:
        subprocess.check_output(["youtube-dl", "--version"])
    except FileNotFoundError:
        print("youtube-dl not found. Please install it.")
        sys.exit(1)


def serialize_episode(line):
    fields = line.findAll("td")
    if not fields:
        return
    return {
        "episode": fields[0].text.strip(),
        "wiki_link": fields[1].find("a").attrs["href"],
        "titel": fields[1].text.strip(),
        "sender": fields[2].text.strip(),
        "datum": fields[3].text.strip(),
        "ermittler": fields[4].text.strip(),
        "ermittler_link": fields[4].find("a").attrs["href"],
        "ermittler_episode": fields[5].text.strip(),
        "kommentar": fields[8].text.strip(),
    }


def update_csv():
    print("Fetching data from Wikipedia")
    response = requests.get("https://de.wikipedia.org/wiki/Liste_der_Tatort-Folgen")
    content = bs4.BeautifulSoup(response.content.decode(), "html.parser")
    table = content.find("table")
    episodes = []
    episodes = [serialize_episode(line) for line in table.findAll("tr")]
    episodes = [e for e in episodes if e]

    print(f"{len(episodes)} Episoden gefunden!")

    with open(CSV_PATH, "w") as fp:
        writer = csv.DictWriter(
            fp,
            fieldnames=[
                "episode",
                "titel",
                "datum",
                "ermittler",
                "ermittler_episode",
                "wiki_link",
                "ermittler_link",
                "sender",
                "kommentar",
            ],
        )
        writer.writeheader()
        writer.writerows(episodes)


def slugify(s):
    return re.sub(r"[\W_]+", "-", s.lower()).strip("-")


def load_csv():
    if not CSV_PATH.exists():
        update_csv()
    with open(CSV_PATH, "r") as fp:
        reader = csv.DictReader(fp)
        data = [l for l in reader]
    for entry in data:
        entry["slug"] = slugify(entry["titel"])
    return data


def normalize_title(title):
    trailing = ("(", "ARD", "Mediathek", "–")  # not a -, a –
    leading = ("Tatort:", "Wunschtatort", "Tatort Konstanz:", "Tatort -")
    for substr in trailing:
        if substr in title:
            title = title[: title.find(substr)]
    for substr in leading:
        if substr in title:
            title = title[title.find(substr) + len(substr) :]
    return title.strip()


def get_episode_by_title(title, include_existing=True):
    title = normalize_title(title)
    slug = slugify(title)
    if slug in KNOWN_BAD:
        return
    matches = [
        e for e in EPISODES if e["slug"].startswith(slug) or slug.startswith(e["slug"])
    ]
    if not matches:
        if "ß" in slug:
            slug = slug.replace("ß", "ss")
        elif "ss" in slug:
            slug = slug.replace("ss", "ß")
        elif "chateau" in slug:
            slug = slug.replace("chateau", "château")
        matches = [
            e
            for e in EPISODES
            if e["slug"].startswith(slug) or slug.startswith(e["slug"])
        ]
        if not matches:
            print(f"Episode '{title}' not found!")
            return

    if not matches:
        return

    if not include_existing:
        exact_matches = [e for e in matches if normalize_title(e["titel"]) == title]
        # Collect all episodes that are exact matches. If all of them exist, we don't need to continue.
        if exact_matches and all(find_episode(e["episode"]) for e in exact_matches):
            return
        # Continue with only non-downloaded episodes
        matches = [
            e
            for e in matches
            if e not in exact_matches and not find_episode(e["episode"])
        ]
        if not matches:
            return

    if len(matches) == 1:
        result = matches[0]
    else:
        exact_matches = [e for e in matches if e["slug"] == slug]
        if len(exact_matches) == 1:
            result = exact_matches[0]
        else:
            options = [(f"{e['episode']} – {e['titel']}", e) for e in matches] + [
                ("None, abort", None)
            ]
            result = inquirer.list_input(
                f"Which Episode is the right one? Title was {title}",
                choices=options,
                carousel=True,
            )
    result["filename"] = slug
    return result


def get_episode(url, title=None):
    global EPISODES
    if not EPISODES:
        EPISODES = load_csv()

    if not title:
        response = requests.get(url)
        content = bs4.BeautifulSoup(response.content.decode(), "html.parser")
        title = content.find("meta", {"property": "og:title"}).attrs["content"]
    return get_episode_by_title(title)


def find_episode(number):
    number = f"{int(number):04d}"
    return list(CWD.glob(f"{number}-*"))


def get_episode_filename(episode):
    return f"{int(episode['episode']):04d}-{episode['filename']}.mp4"


def handle_download(url, title=None):
    episode = get_episode(url, title=title, include_existing=False)
    if not episode:
        print(f"Episode not found or exists already on disk.")
        return
    filename = get_episode_filename(episode)
    print(f"Downloading episode {episode['episode']}: {episode['titel']} to {filename}")
    subprocess.call(["youtube-dl", "-o", filename, url])
    subprocess.call(["notify-send", f"Finished downloading {episode['titel']}"])


def download():
    print("Welcome to the Tatort downloader.")
    global EPISODES
    EPISODES = load_csv()
    if len(sys.argv) > 2:
        for url in sys.argv[2:]:
            handle_download(url)
    else:
        while True:
            url = inquirer.text("Enter a URL (or q[uit] to quit)")
            if url in ("q", "quit"):
                break
            handle_download(url)


def bulk_download():
    print("Welcome to the Tatort bulk downloader.")
    global EPISODES, OFFSET
    EPISODES = load_csv()
    size = 10
    query = {
        "queries": [{"fields": ["topic"], "query": "tatort"}],
        "duration_min": 4800,
        "sortBy": "timestamp",
        "sortOrder": "desc",
        "future": "false",
        "offset": OFFSET,
        "size": 10,
    }
    url = "https://mediathekviewweb.de/api/query"
    headers = {"Content-Type": "text/plain"}
    blocklist = ("klare Sprache", "Audiodeskription")
    seen = set()
    while True:
        response = requests.post(url, data=json.dumps(query), headers=headers)
        data = response.json()
        if data.get("err"):
            raise Exception(data)
        print(
            f"Got results {query['offset'] + 1} – {query['offset'] + size} out of {data['result']['queryInfo']['totalResults']}"
        )
        if not data["result"]["results"]:
            break
        for entry in data["result"]["results"]:
            title = entry["title"]
            if any(b in title for b in blocklist):
                continue
            if title in seen:
                continue
            seen.add(title)
            episode = get_episode_by_title(title, include_existing=False)
            if not episode:
                continue
            filename = get_episode_filename(episode)
            print(
                f"Downloading {episode['episode']} – {episode['titel']} to {filename}"
            )
            urls = [entry["url_video_hd"], entry["url_video"], entry["url_video_low"]]
            for url in urls:
                if not url:
                    continue
                if Path(filename).exists():
                    break
                with suppress(Exception):
                    subprocess.call(["youtube-dl", "-o", filename, url])
                    if not "ERROR: Unable to download webpage" in result:
                        result = subprocess.check_output(
                            ["notify-send", f"Finished downloading {episode['titel']}"]
                        )
                        break
            else:
                print(
                    f"None of the URLs for {episode['episode']} – {episode['titel']} work, skipping."
                )
                print(urls)
        OFFSET += size
        query["offset"] = OFFSET


def get_available_episodes():
    # in cwd, match dddd-*.mp4, return the numbers
    return [int(e.name[:4]) for e in CWD.glob("*.mp4")]


def get_watched_episodes():
    wb = load_workbook(SPREADSHEET_PATH)
    return [
        int(e.value)
        for e in wb["Folgen"]["A"]
        if e.value and isinstance(e.value, int) or e.value.isdigit()
    ]


def watch():
    watched = get_watched_episodes()
    available = get_available_episodes()
    for episode in sorted(available):
        if not episode in watched:
            break
    path = find_episode(episode)[0]
    global EPISODES
    if not EPISODES:
        EPISODES = load_csv()
    print()
    print("#" * 80)
    print(f"#  Watching {episode}: {EPISODES[episode]['titel']}")
    print("#" * 80)
    print()
    subprocess.call(["vlc", path])
    subprocess.call(["libreoffice", SPREADSHEET_PATH])


if __name__ == "__main__":
    arg = sys.argv[1]
    if arg == "update_csv":
        update_csv()
    elif arg == "download":
        check_youtube_dl()
        download()
    elif arg == "bulk":
        check_youtube_dl()
        while True:
            try:
                bulk_download()
                break
            except Exception:
                print(f"Failure, increasing offset to {OFFSET + 1}")
                OFFSET += 1
    elif arg == "watch":
        watch()
    else:
        print(
            "Call script with 'update_csv', 'download' (with a link or without to enter interactive mode), 'bulk' or 'watch'"
        )
