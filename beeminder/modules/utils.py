import configparser
import datetime as dt
from contextlib import suppress
import json

import requests


def get_config(base_dir):
    config = configparser.ConfigParser()
    config.read(base_dir / "beeminder.cfg")
    config["DEFAULT"]["mode"] = "minimum"
    return config


def get_data(data_path):
    data = {}
    with suppress(FileNotFoundError):
        with open(data_path) as f:
            data = json.load(f)
    return data


def save_data(data_path, data):
    with open(data_path, "w") as f:
        json.dump(data, f, indent=4)


def needs_update(current_value, old_value, mode):
    if old_value is None:
        return True
    if mode == "update":
        return True
    if mode == "minimum":
        return old_value > current_value
    return old_value < current_value


def submit_data(goal, value, config):
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

