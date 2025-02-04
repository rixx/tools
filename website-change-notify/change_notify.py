#!/bin/python3
import configparser
import json
from contextlib import suppress
from functools import cached_property

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


IGNORE_TITLE = get_config_list("ignore", "title")
IGNORE_ID = get_config_list("ignore", "id")


class TolerantDict(dict):
    def __missing__(self, key):
        """Don't fail when formatting strings with a dict with missing keys."""
        return "MISSING"


def get_value(html, query, multiple=False):
    # Query should be a CSS selector. However, it can include an "[attribute]" part,
    # which will be used to return the attribute value.
    # If multiple is True, return a comma-separated list of all values.
    attribute = None
    if "[" in query:
        query, attribute = query.split("[")
        attribute = attribute.strip("]")
    if not html:
        return None
    if multiple:
        elements = html.select(query)
    else:
        elements = [html.select_one(query)]
    if not elements:
        raise ValueError(f"Could not find {query} in HTML {html}")
    if attribute:
        elements = [element.get(attribute) for element in elements if element]
    else:
        elements = [
            " ".join(string for string in element.stripped_strings)
            for element in elements
            if element
        ]
    return "\n".join(elements)


class Entry:

    def __init__(self, html):
        self.html = html
        self.id = get_value(self.html, config["website"]["id"])
        self.title = get_value(self.html, config["website"]["title"])
        self.detail_url = None
        with suppress(Exception):
            self.detail_url = get_value(self.html, config["website"]["detail_url"])

        if self.detail_url and not self.detail_url.startswith("http"):
            if self.detail_url.startswith("//"):
                self.detail_url = "https:" + self.detail_url
            elif self.detail_url.startswith("/"):
                # Get domain
                url = config["website"]["url"]
                domain = url.split("/")[2]
                self.detail_url = f"https://{domain}{self.detail_url}"
            else:
                # Relative URL
                self.detail_url = config["website"]["url"] + self.detail_url

    def get_detail_html(self):
        if self.detail_url:
            response = requests.get(self.detail_url, allow_redirects=True)
            if response.status_code != 200:
                print(f"Could not get detail URL {self.detail_url}")
                self.detail_url = None
            return BeautifulSoup(response.text, "html.parser")

    def should_notify(self):
        if self.title.lower() in IGNORE_TITLE:
            return False
        if self.id in IGNORE_ID:
            return False
        return True

    def render_template(self, template, context):
        return template.format(**TolerantDict(context)).strip("\"' \n")

    def send_pushover(self, force=False):
        if not self.should_notify() and not force:
            return

        context = {
            "id": self.id,
            "title": self.title,
            "url": self.detail_url,
        }
        for key, value in config["context_main"].items():
            context[key] = get_value(self.html, value, multiple=key.endswith("list"))

        if self.detail_url:
            detail_html = self.get_detail_html()
            for key, value in config["context_detail"].items():
                value = value.strip('"')
                try:
                    context[key] = get_value(
                        detail_html, value, multiple=key.endswith("list")
                    )
                except Exception:
                    print(f"Could not get {value} from detail HTML")

        payload = {
            "token": config["pushover"]["app"],
            "user": config["pushover"]["user"],
            "title": limit_length(
                self.render_template(config["templates"]["subject"], context), 250
            ),
            "message": limit_length(
                self.render_template(config["templates"]["message"], context), 1024
            ),
            "url": self.detail_url or config["website"]["url"],
            "url_title": "Go to website",
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
        return {element.strip() for element in content.strip().split("\n") if element}
    return set()


def write_seen_ids(ids):
    content = "\n".join(str(element) for element in ids)
    with open("./seen_ids", "w") as seen_file:
        seen_file.write(content)


def get_entries():
    response = requests.get(config["website"]["url"])
    response.raise_for_status()
    html = BeautifulSoup(response.text, "html.parser")
    return [Entry(entry) for entry in html.select(config["website"]["element"])]


def limit_length(text, length):
    if len(text) <= length:
        return text
    return text[: length - 2] + "…"


def main():
    seen_ids = get_seen_ids()
    try:
        entries = get_entries()
    except Exception:
        # This usually happens when DNS is failing.
        # Fail quietly, as exceptions are just annoying, and this isn't critical.
        return
    new_seen_ids = []
    for entry in entries:
        if entry.id not in seen_ids:
            entry.send_pushover()
        new_seen_ids.append(entry.id)
    write_seen_ids(new_seen_ids)


if __name__ == "__main__":
    main()
