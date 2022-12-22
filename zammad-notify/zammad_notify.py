#!/bin/python3
import configparser
import json
from contextlib import suppress

import requests
from bs4 import BeautifulSoup

config = configparser.ConfigParser()
config.read("notify.cfg")


BODY_BLOCKED = [  # heh.
    "есть",
    "Spam detection software, running on the system",
]
# Most of these are now filtered in Zammad, but better safe than sorry
SUBJECT_BLOCKED = [
    "undelivered mail returned to sender",
    "delivery status notification",
    "automatic reply",
    "auto reply",
    "away from work",
    "out of office",
]


def get_seen_ids():
    with suppress(FileNotFoundError):
        with open("./seen_ids") as seen_file:
            content = seen_file.read()
        return {int(element) for element in content.strip().split("\n") if element}
    return set()


def write_seen_ids(ids):
    content = "\n".join(str(element) for element in ids)
    with open("./seen_ids", "w") as seen_file:
        seen_file.write(content)


def zammad_get(url):
    auth = None
    if "http_user" in config["zammad"]:
        auth = (config["zammad"]["http_user"], config["zammad"]["http_pass"])
    response = requests.get(
        url=config["zammad"]["url"] + url,
        headers={"Authorization": f'Bearer {config["zammad"]["token"]}'},
        auth=auth,
    )
    response.raise_for_status()
    return response.json()


def get_unread_notifications():
    response = zammad_get("/api/v1/online_notifications")
    return [notification for notification in response if notification["seen"] is False]


def limit_length(text, length):
    if len(text) <= length:
        return text
    return text[: length - 2] + "…"


def send_notification(notification):
    ticket_id = notification["o_id"]
    ticket = zammad_get(f"/api/v1/ticket_articles/by_ticket/{ticket_id}")[-1]
    if any((ticket.get(text) or "").startswith("RT @") for text in ["subject", "body"]):
        return
    ticket_data = zammad_get(f"/api/v1/tickets/{ticket_id}")
    customer = zammad_get(f'/api/v1/users/{ticket_data["customer_id"]}')
    subject = ticket_data["title"]
    for blocked in SUBJECT_BLOCKED:
        if blocked in subject.lower():
            return
    name = customer.get("firstname", " ") + " " + customer.get("lastname", "")
    name = name.strip()
    if not name:
        name = f'<{customer["email"]}>'
    body = ticket["body"]
    for blocked in BODY_BLOCKED:
        if blocked in body:
            return
    if "<" in body:
        try:
            body = BeautifulSoup(body, "html.parser").text.strip()
        except Exception:
            pass
    if not body:
        return
    auth = ""
    if "http_user" in config["zammad"]:
        auth = f"{config['zammad']['http_user']}:{config['zammad']['http_pass']}@"

    payload = {
        "token": config["pushover"]["app"],
        "user": config["pushover"]["user"],
        "title": limit_length(f"{subject} ({name})", 250),
        "message": limit_length(body, 1024),
        "url": f"{auth}{config['zammad']['url']}/#ticket/zoom/{ticket_id}",
        "url_title": "Go to ticket",
        "sound": "none",
    }
    response = requests.post(
        url="https://api.pushover.net/1/messages.json",
        data=json.dumps(payload),
        headers={"Content-Type": "application/json"},
    )
    response.raise_for_status()


def main():
    seen_ids = get_seen_ids()
    notifications = get_unread_notifications()
    new_seen_ids = []
    for notification in notifications:
        if notification["id"] not in seen_ids:
            send_notification(notification)
        new_seen_ids.append(notification["id"])
    write_seen_ids(new_seen_ids)


if __name__ == "__main__":
    main()
