#!/bin/python3
import configparser
import datetime as dt
import glob
import json
import sys
from contextlib import suppress
from pathlib import Path

import lz4.block
import requests

base_dir = Path(__file__).parent
config = configparser.ConfigParser()
config.read(base_dir / "beeminder.cfg")
config["DEFAULT"]["mode"] = "minimum"
data_path = base_dir / "beeminder.json"


def get_firefox_profile_path():
    basis = Path.home() / ".mozilla/firefox"
    possibilities = glob.glob(str(basis / "*default*"))
    if len(possibilities) == 1:
        return possibilities[0]
    example_config = f"[goal:firefox]\npath = {basis}…"
    if len(possibilities) == 0:
        print(
            f"""Could not find Firefox profile in {basis}.
Please put one in your beeminder.cfg, like this:

{example_config}"""
        )
    else:
        print(
            f"""I found more than one Firefox profile called "default", and now I am confused.
Please tell me which to use in the beeminder.cfg, like this:

{example_config}

Possible profiles:"""
        )
        for path in possibilities:
            print(f"- {path}")
    sys.exit(-1)


def get_current_tab_count():
    if "goal:firefox" in config:
        path = config["goal:firefox"]["path"] or get_firefox_profile_path()
    else:
        path = get_firefox_profile_path()
    recovery_file = Path(path) / "sessionstore-backups/recovery.jsonlz4"
    if not recovery_file.exists():
        print(f"No recovery file at {recovery_file}. Cannot determine tab count!")
        sys.exit(-1)
    with open(recovery_file, "rb") as f:
        f.read(8)  # Custom Firefox header, ignore
        content = f.read()
    data = json.loads(lz4.block.decompress(content))
    tab_count = 0
    for window in data.get("windows"):
        tab_count += len(window.get("tabs"))
    print(f"{tab_count} tabs currently!")
    return tab_count


def needs_update(current_value, old_value, mode):
    if old_value is None:
        return True
    if mode == "update":
        return True
    if mode == "minimum":
        return old_value > current_value
    return old_value < current_value


def get_historical_tab_count():
    historic_data = {}
    with suppress(FileNotFoundError):
        with open(data_path) as f:
            historic_data = json.load(f)
    return historic_data


def submit_data(goal, value):
    bee_config = config["beeminder"]
    user = bee_config["username"]
    auth_token = bee_config["auth_token"]
    data = {
        "auth_token": auth_token,
        "daystamp": dt.datetime.now().strftime("%Y-%m-%d"),
        "value": value,
    }
    base_url = f"https://www.beeminder.com/api/v1/users/{user}/goals/{goal}/datapoints"
    url = f"{base_url}.json"
    response = requests.post(url, data)
    response.raise_for_status()
    response_data = response.json()
    if isinstance(response_data, list):
        response_data = response_data[0]
    if response_data["value"] != value:
        url = f'{base_url}/{response_data["id"]}.json'
        response = requests.put(url, data)
        response.raise_for_status()


def handle_firefox():
    historic_data = get_historical_tab_count()
    tab_count = get_current_tab_count()
    mode = config.get("goal:firefox", "mode")
    today = dt.datetime.now().strftime("%Y%m%d")
    if needs_update(tab_count, historic_data.get(today), mode):
        submit_data(config.get("goal:firefox", "goal"), tab_count)
        historic_data[today] = tab_count
        with open(data_path, "w") as f:
            json.dump(historic_data, f, indent=4)


def main():
    goal_mapping = {
        "firefox": handle_firefox
    }
    for key, value in goal_mapping.items():
        if f"goal:{key}" in config:
            value()


if __name__ == "__main__":
    main()
