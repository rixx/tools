import csv
import re
import os
import subprocess
import sys
from pathlib import Path

import bs4
import inquirer
import requests


CWD = Path(os.getcwd())
CSV_PATH = Path(__file__).parent / "episodes.csv"
EPISODES = []


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


def get_episode(url):
    global EPISODES
    if not EPISODES:
        EPISODES = load_csv()
    response = requests.get(url)
    content = bs4.BeautifulSoup(response.content.decode(), "html.parser")
    title = content.find("meta", {"property": "og:title"}).attrs["content"]
    trailing = ("(", "ARD", "Mediathek")
    leading = ("Tatort:",)
    for substr in trailing:
        if substr in title:
            title = title[: title.find(substr)]
    for substr in leading:
        if substr in title:
            title = title[title.find(substr) + len(substr) :]
    slug = slugify(title.strip())
    matches = [
        e for e in EPISODES if e["slug"].startswith(slug) or slug.startswith(e["slug"])
    ]
    if not matches:
        print("Episode not found! Can't assign file name, aborting")
        return
    if len(matches) == 1:
        result = matches[0]
    else:
        options = [(f"{e['episode']} – {e['titel']}", e) for e in matches] + [
            ("None, abort", None)
        ]
        result = inquirer.list_input(
            "Which Episode is the right one?",
            choices=options,
            carousel=True,
        )
    result["filename"] = slug
    return result


def handle_download(url):
    episode = get_episode(url)
    if not episode:
        return
    number = f"{int(episode['episode']):04d}"
    found = list(CWD.glob(f"{number}-*"))
    if found:
        print(f"Episode exists on disk: {found[0]}")
        return
    filename = f"{number}-{episode['filename']}.mp4"
    print(f"Downloading episode {number}: {episode['titel']} to {filename}")
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


if __name__ == "__main__":
    arg = sys.argv[1]
    if arg == "update_csv":
        update_csv()
    elif arg == "download":
        download()
    else:
        print(
            "Call script with either 'update_csv' or 'download' (with a link or without to enter interactive mode)"
        )
