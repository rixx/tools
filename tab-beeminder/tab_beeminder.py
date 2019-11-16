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

config = configparser.ConfigParser()
config.read("tab-beeminder.cfg")
config['DEFAULT']['mode'] = 'minimum'


def get_firefox_profile_path():
    basis = Path.home() / '.mozilla/firefox'
    possibilities = glob.glob(str(basis / '*default*'))
    if len(possibilities) == 1:
        return possibilities[0]
    example_config = f'[firefox]\npath = {basis}…'
    if len(possibilities) == 0:
        print(f'''Could not find Firefox profile in {basis}.
Please put one in your tab-beeminder.cfg, like this:

{example_config}''')
    else:
        print(f'''I found more than one Firefox profile called "default", and now I am confused.
Please tell me which to use in the tab-beeminder.cfg, like this:

{example_config}

Possible profiles:''')
        for path in possibilities:
            print(f'- {path}')
    sys.exit(-1)


def get_current_tab_count():
    if 'firefox' in config:
        path = config['firefox']['path'] or get_firefox_profile_path()
    else:
        path = get_firefox_profile_path()
    recovery_file = Path(path) / 'sessionstore-backups/recovery.jsonlz4'
    if not recovery_file.exists():
        print(f'No recovery file at {recovery_file}. Cannot determine tab count!')
        sys.exit(-1)
    with open(recovery_file, 'rb') as f:
        f.read(8)  # Custom Firefox header, ignore
        content = f.read()
    data = json.loads(lz4.block.decompress(content))
    tab_count = 0
    for window in data.get("windows"):
        tab_count += len(window.get('tabs'))
    print(f'{tab_count} tabs currently!')
    return tab_count


def needs_update(old_value, current_value):
    mode = config.get('beeminder', 'mode')
    if mode == 'update':
        return True
    if mode == 'minimum':
        return old_value > current_value
    return old_value < current_value


def get_tab_count():
    current_count = get_current_tab_count()
    historic_data = {}
    with suppress(FileNotFoundError):
        with open('tab-beeminder.json') as f:
            historic_data = json.load(f)
    today = dt.datetime.now().strftime('%Y%m%d')
    old_value = historic_data.get(today)
    if old_value is None or needs_update(old_value, current_count):
        historic_data[today] = current_count
        with open('tab-beeminder.json', 'w') as f:
            json.dump(historic_data, f, indent=4)
        return current_count


def submit_tab_count(tab_count):
    bee_config = config['beeminder']
    user = bee_config['username']
    goal = bee_config['goal']
    auth_token = bee_config['auth_token']
    data = {
        'auth_token': auth_token,
        'daystamp': dt.datetime.now().strftime('%Y-%m-%d'),
        'value': tab_count,
    }
    base_url = f'https://beeminder.com/api/v1/users/{user}/goals/{goal}/datapoints'
    url = f'{base_url}.json?auth_token={auth_token}'
    response = requests.post(url, data)
    response.raise_for_status()
    response_data = response.json()[0]
    if response_data["value"] != tab_count:
        url = f'{base_url}/{response_data["id"]}.json?auth_token={auth_token}'
        data['_method'] = 'PUT'
        response = requests.post(url, data)
        response.raise_for_status()
    print(response.content.decode())


def main():
    tab_count = get_tab_count()
    if tab_count is not None:
        submit_tab_count(tab_count)


if __name__ == "__main__":
    main()
