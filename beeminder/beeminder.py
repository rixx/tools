#!/bin/python3
import copy
from pathlib import Path

from modules.firefox import handle_firefox
from modules.utils import get_config, get_data, save_data


def main():
    base_dir = Path(__file__).parent
    data_path = base_dir / "beeminder.json"
    config = get_config(base_dir)
    data = get_data(data_path)
    goal_mapping = {
        "firefox": handle_firefox,
        # "goodreads": handle_goodreads,
    }
    for key, value in goal_mapping.items():
        if f"goal:{key}" in config:
            original_data = copy.deepcopy(data)
            try:
                data = value(config, data)
                if data != original_data:
                    save_data(data_path, data)
            except Exception as e:
                print(f"Error in command {key}: {e}")


if __name__ == "__main__":
    main()
