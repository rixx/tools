#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "inquirer",
#     "beautifulsoup4",
#     "requests",
#     "openpyxl",
# ]
# ///
import csv
import os
import re
import subprocess
import sys
from pathlib import Path

import bs4
import inquirer
import requests
from openpyxl import load_workbook

from lib import search_mediathekviewweb, download_mediathek_video

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
    # gold vs goldbach :(
    "goldbach",
)
OFFSET = int(os.environ.get("OFFSET") or 0)

# TODO: mappings
# 'Es grünt so grün, wenn Frankfurts Berge blühen' (API) -> 'Es grünt so grün, wenn Frankfurts Berge blüh’n' (CSV)


def check_youtube_dl():
    try:
        subprocess.check_output(["yt-dlp", "--version"])
    except FileNotFoundError:
        print("yt-dlp not found. Please install it.")
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
        data = list(reader)
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
    return title.strip().strip(":")


def get_episode_by_title(title, include_existing=True, noinput=False):
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

    exact_matches = [e for e in matches if normalize_title(e["titel"]) == title]

    if not include_existing:
        # If there are exact matches and all of them exist, we don't need to continue.
        if exact_matches and all(find_episode(e["episode"]) for e in exact_matches):
            return

        # If there is only one exact match, we can use that.
        if len(exact_matches) == 1 and not find_episode(exact_matches[0]["episode"]):
            matches = exact_matches
        else:
            # Continue with only non-downloaded episodes
            matches = [e for e in matches if not find_episode(e["episode"])]
            if not matches:
                return

    if len(matches) == 1:
        result = matches[0]
    elif noinput:
        return
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
        print("Episode not found or exists already on disk.")
        return
    filename = get_episode_filename(episode)
    print(f"Downloading episode {episode['episode']}: {episode['titel']} to {filename}")
    subprocess.call(["yt-dlp", "-o", filename, url])
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


def bulk_download(noinput=False):
    print("Welcome to the Tatort bulk downloader.")
    global EPISODES, OFFSET
    EPISODES = load_csv()
    size = 10
    blocklist = ["klare Sprache", "Audiodeskription"]
    seen = set()
    while True:
        results = search_mediathekviewweb(
            topic="tatort",
            min_duration=4800,
            max_results=size,
            offset=OFFSET,
            blocklist=blocklist,
        )
        print(f"Got {len(results)} results at offset {OFFSET}")
        if not results:
            break
        for result in results:
            title = result.title
            if title in seen:
                continue
            seen.add(title)
            episode = get_episode_by_title(
                title, include_existing=False, noinput=noinput
            )
            if not episode:
                continue
            filename = Path(get_episode_filename(episode))
            if filename.exists():
                continue
            print(
                f"Downloading {episode['episode']} – {episode['titel']} to {filename}"
            )
            download_result = download_mediathek_video(result, filename)
            if download_result.success:
                subprocess.call(["notify-send", f"Finished downloading {episode['titel']}"])
            else:
                print(
                    f"Download failed for {episode['episode']} – {episode['titel']}: {download_result.error}"
                )
        OFFSET += size


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
        if episode not in watched:
            break
    path = find_episode(episode)[0]
    global EPISODES
    if not EPISODES:
        EPISODES = load_csv()
    print()
    print("#" * 80)
    print(f"#  Watching {episode}: {EPISODES[episode - 1]['titel']}")
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
                bulk_download(noinput="--noinput" in sys.argv)
                break
            except Exception as e:
                print(f"Failure, increasing offset to {OFFSET + 1}")
                print(e)
                OFFSET += 1
    elif arg == "watch":
        watch()
    else:
        print(
            "Call script with 'update_csv', 'download' (with a link or without to enter interactive mode), 'bulk [--noinput]' or 'watch'"
        )
