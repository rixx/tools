import csv
import json
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
KNOWN_BAD = ("die-professorin-tatort-ölfeld",)


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
    return title.strip().replace("ß", "ss")


def get_episode_by_title(title):
    title = normalize_title(title)
    slug = slugify(title)
    if slug in KNOWN_BAD:
        return
    matches = [
        e for e in EPISODES if e["slug"].startswith(slug) or slug.startswith(e["slug"])
    ]
    if not matches:
        print("Episode not found!")
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
    episode = get_episode(url, title=title)
    if not episode:
        return
    found = find_episode(episode["episode"])
    if found:
        print(f"Episode exists on disk: {found[0]}")
        return
    filename = get_episode_filename(episode)
    print(f"Downloading episode {episode['number']}: {episode['titel']} to {filename}")
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
    global EPISODES
    EPISODES = load_csv()
    size = 10
    query = {
        "queries": [{"fields": ["topic"], "query": "tatort"}],
        "duration_min": 4800,
        "sortBy": "timestamp",
        "sortOrder": "desc",
        "future": "false",
        "offset": int(os.environ.get("OFFSET") or 0),
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
            episode = get_episode_by_title(title)
            if not episode:
                print(
                    f"Unable to find episode for title {title}, with url {entry['url_video_hd']}"
                )
                continue
            found = find_episode(episode["episode"])
            if found:
                # print(f"Episode exists on disk: {found[0]}")
                continue
            filename = get_episode_filename(episode)
            print(f"Downloading episode['episode'] – {episode['titel']} to {filename}")
            url = entry["url_video_hd"] or entry["url_video"] or entry["url_video_low"]
            subprocess.call(["youtube-dl", "-o", filename, url])
            subprocess.call(["notify-send", f"Finished downloading {episode['titel']}"])
        query["offset"] += size


if __name__ == "__main__":
    arg = sys.argv[1]
    if arg == "update_csv":
        update_csv()
    elif arg == "download":
        download()
    elif arg == "bulk":
        bulk_download()
    else:
        print(
            "Call script with either 'update_csv' or 'download' (with a link or without to enter interactive mode)"
        )
