import requests
import xml.etree.ElementTree as ET

from .utils import needs_update


def get_current_book_count(config):
    user_id = config.get("goal:goodreads", "user_id")
    api_token = config.get("goal:goodreads", "api_token")
    shelves = config.get("goal:goodreads", "shelves")
    url = f"https://www.goodreads.com/review/list/{user_id}.xml"
    data = {"key": api_token, "v": "2", "per_page": 0}
    total = 0
    for shelf in shelves.split(","):
        data["shelf"] = shelf
        response = requests.get(url, data=data)
        to_root = ET.fromstring(response.content.decode())
        total += int(to_root.find("reviews").attrib["total"] or 0)
    print(f"{total} books in total!")
    return total


def handle_goodreads(config, original_value):
    book_count = get_current_book_count(config)
    mode = config.get("goal:goodreads", "mode")
    goal = config.get("goal:goodreads", "goal")
    if needs_update(book_count, original_value, mode):
        return book_count
