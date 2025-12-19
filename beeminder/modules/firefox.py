import glob
import json
from pathlib import Path

import lz4.block

from .utils import needs_update


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
    raise Exception


def get_current_tab_count(config):
    if "goal:firefox" in config:
        path = config["goal:firefox"]["path"] or get_firefox_profile_path()
    else:
        path = get_firefox_profile_path()
    recovery_file = Path(path) / "sessionstore-backups/recovery.jsonlz4"
    if not recovery_file.exists():
        print(f"No recovery file at {recovery_file}. Cannot determine tab count!")
        raise Exception
    with open(recovery_file, "rb") as f:
        f.read(8)  # Custom Firefox header, ignore
        content = f.read()
    data = json.loads(lz4.block.decompress(content))
    tab_count = 0
    for window in data.get("windows"):
        tab_count += len(window.get("tabs"))
    print(f"{tab_count} tabs currently!")
    return tab_count


def handle_firefox(config, original_value):
    tab_count = get_current_tab_count(config)
    mode = config.get("goal:firefox", "mode")
    if needs_update(tab_count, original_value, mode):
        return tab_count
