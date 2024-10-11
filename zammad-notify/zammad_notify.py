#!/bin/python3
import configparser
import datetime as dt
import json
from contextlib import suppress

import requests
from bs4 import BeautifulSoup

config = configparser.ConfigParser()
config.read("notify.cfg")


def get_config_list(section, key):
    return [
        term.strip().lower()
        for term in config.get(section, key, fallback="").split("\n")
        if term.strip()
    ]


IGNORE_SUBJECT = get_config_list("ignore", "subject")
IGNORE_BODY = get_config_list("ignore", "body")
IGNORE_TAGS = set(get_config_list("ignore", "tags"))
IGNORE_FROM = get_config_list("ignore", "from")
QUOTES = get_config_list("cut", "quotes")


class Ticket:
    def __init__(self, ticket_id):
        ticket_data = zammad_get(f"/tickets/{ticket_id}")
        customer = zammad_get(f'/users/{ticket_data["customer_id"]}')
        body = zammad_get(f"/ticket_articles/by_ticket/{ticket_id}")[-1]["body"]

        self.ticket_id = ticket_id
        self.subject = ticket_data["title"]
        self.is_pending_reached = is_past(ticket_data.get("pending_time"))
        self.customer_name = (
            customer["firstname"] + " " + customer["lastname"]
        ).strip()
        self.customer_email = customer["email"]
        self.tags = zammad_get(f"/tags?object=Ticket&o_id={ticket_id}")["tags"]
        if "<" in body:
            try:
                body = BeautifulSoup(body, "html.parser").text.strip()
            except Exception:
                pass
        self.body = body

    def should_notify(self):
        if set(self.tags) & IGNORE_TAGS:
            return False
        if not self.body:
            return False
        for blocked in IGNORE_SUBJECT:
            if blocked in self.subject.lower():
                return False
        for blocked in IGNORE_BODY:
            if blocked in self.body.lower():
                return False
        for blocked in IGNORE_FROM:
            if blocked in self.customer_email:
                return False
        return True

    def send_pushover(self, force=False):
        if not self.should_notify() and not force:
            return
        name = self.customer_name or f"<{self.customer_email}>"
        title = f"{self.subject} ({name})"
        if self.is_pending_reached:
            title = f"Pending reminder reached: {title}"

        payload = {
            "token": config["pushover"]["app"],
            "user": config["pushover"]["user"],
            "title": limit_length(title, 250),
            "message": limit_length(cut_quote(cut_signature((self.body))), 1024),
            "url": f"{config['zammad']['url']}/#ticket/zoom/{self.ticket_id}",
            "url_title": "Go to ticket",
            "sound": "none",
        }
        response = requests.post(
            url="https://api.pushover.net/1/messages.json",
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()


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
    response = requests.get(
        url=config["zammad"]["url"] + "/api/v1" + url,
        headers={"Authorization": f'Bearer {config["zammad"]["token"]}'},
    )
    response.raise_for_status()
    return response.json()


def get_unread_notifications():
    response = zammad_get("/online_notifications")
    return [notification for notification in response if notification["seen"] is False]


def is_past(timestamp: str):
    if not timestamp:
        return False
    return timestamp < dt.datetime.now().isoformat()


def limit_length(text, length):
    if len(text) <= length:
        return text
    return text[: length - 2] + "…"


def cut_signature(text):
    signature_marker = "-- \n"
    if not text or signature_marker not in text:
        return text
    return text.split(signature_marker, maxsplit=1)[0]


def cut_quote(text):
    if not QUOTES:
        return text
    result = []

    for line in text.split("\n"):
        if line.endswith(":") and any(quote in line.lower() for quote in QUOTES):
            break
        result.append(line)

    return "\n".join(result)


def main():
    seen_ids = get_seen_ids()
    try:
        notifications = get_unread_notifications()
    except Exception:
        # This usually happens when DNS is failing.
        # Fail quietly, as exceptions are just annoying, and this isn't critical.
        return
    new_seen_ids = []
    for notification in notifications:
        if notification["id"] not in seen_ids:
            Ticket(notification["o_id"]).send_pushover()
        new_seen_ids.append(notification["id"])
    write_seen_ids(new_seen_ids)


if __name__ == "__main__":
    main()
