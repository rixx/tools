#!/bin/python3
import copy
import datetime as dt
from pathlib import Path

from modules.firefox import handle_firefox
from modules.goodreads import handle_goodreads
from modules.utils import get_config, get_data, save_data, submit_data


def main():
    base_dir = Path(__file__).parent
    data_path = base_dir / "beeminder.json"
    config = get_config(base_dir)
    data = get_data(data_path)
    today = dt.datetime.now().strftime("%Y%m%d")
    data_today = data.get(today, {})

    goal_mapping = {"firefox": handle_firefox, "goodreads": handle_goodreads}

    for key, function in goal_mapping.items():
        if f"goal:{key}" in config:
            goal = config.get(f"goal:{key}", "goal")
            original_value = data_today.get(goal)
            try:
                new_value = function(config, original_value)
                if not (new_value is None) and new_value != original_value:
                    submit_data(goal, new_value, config)
                    data_today[goal] = new_value
            except Exception as e:
                print(f"Error in command {key}: {e}")
    data[today] = data_today
    save_data(data_path, data)


if __name__ == "__main__":
    main()
