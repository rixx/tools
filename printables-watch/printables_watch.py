#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "requests",
# ]
# ///
"""Watch Printables searches and mail new models.

Config lives in watch.toml next to this script (or pass --config). Per search,
the newest firstPublish seen goes to state.json next to the config. The first run
for a search records the watermark without mailing.
"""

import argparse
import html
import json
import smtplib
import sys
import tomllib
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

import requests

API = "https://api.printables.com/graphql/"
UA = "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0"
MEDIA = "https://media.printables.com/"
# Printables blocks curl-ish clients at Cloudflare and has introspection off.
# Field names below were found by probing; see reference:Printables in the wiki.
QUERY = """
query ($query: String!, $limit: Int!, $offset: Int!) {
  searchPrints2(query: $query, limit: $limit, offset: $offset, ordering: latest) {
    items {
      id name slug summary firstPublish likesCount downloadCount nsfw
      user { publicUsername }
      image { filePath }
      category { name }
    }
  }
}
"""


def fetch(query, limit, offset):
    response = requests.post(
        API,
        json={
            "query": QUERY,
            "variables": {"query": query, "limit": limit, "offset": offset},
        },
        headers={
            "User-Agent": UA,
            "Origin": "https://www.printables.com",
            "Referer": "https://www.printables.com/",
        },
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    if "errors" in data:
        raise RuntimeError(json.dumps(data["errors"]))
    return data["data"]["searchPrints2"]["items"]


def model_url(item):
    return f"https://www.printables.com/model/{item['id']}-{item['slug']}"


def matches(item, search):
    text = f"{item['name']} {item.get('summary') or ''}".lower()
    if any(word.lower() in text for word in search.get("exclude", [])):
        return False
    required = search.get("require", [])
    if required and not any(word.lower() in text for word in required):
        return False
    if item.get("nsfw") and not search.get("nsfw", False):
        return False
    return True


def collect(search, watermark, limit, max_pages):
    """Fetch newest-first (sorted by firstPublish) until reaching the watermark."""
    found = []
    for page in range(max_pages):
        items = fetch(search["query"], limit, page * limit)
        if not items:
            break
        new = [item for item in items if item["firstPublish"] > watermark]
        found.extend(new)
        if len(new) < len(items):
            break
    return found


def render_text(sections):
    lines = []
    for search, items in sections:
        lines.append(f"## {search['query']} ({len(items)})")
        lines.append("")
        for item in items:
            lines.append(f"- {item['name']} by {item['user']['publicUsername']}")
            lines.append(f"  {model_url(item)}")
            if item.get("summary"):
                lines.append(f"  {item['summary'].strip()}")
        lines.append("")
    return "\n".join(lines)


def render_html(sections):
    parts = ["<html><body style='font-family:sans-serif'>"]
    for search, items in sections:
        parts.append(f"<h2>{html.escape(search['query'])} ({len(items)})</h2>")
        for item in items:
            url = model_url(item)
            img = ""
            if item.get("image"):
                img = (
                    f"<a href='{url}'><img src='{MEDIA}{html.escape(item['image']['filePath'])}'"
                    " style='width:160px;height:120px;object-fit:cover;float:left;margin:0 12px 12px 0'></a>"
                )
            meta = (
                f"{html.escape(item['user']['publicUsername'])} · "
                f"{item['firstPublish'][:10]} · "
                f"{item.get('likesCount', 0)} likes · {item.get('downloadCount', 0)} downloads"
            )
            if item.get("category"):
                meta += f" · {html.escape(item['category']['name'])}"
            summary = html.escape((item.get("summary") or "").strip())
            parts.append(
                "<div style='clear:both;overflow:hidden;margin-bottom:16px'>"
                f"{img}<b><a href='{url}'>{html.escape(item['name'])}</a></b><br>"
                f"<small>{meta}</small><br>{summary}</div>"
            )
    parts.append("</body></html>")
    return "\n".join(parts)


def send_mail(config, sections, dry_run):
    total = sum(len(items) for _, items in sections)
    message = EmailMessage()
    message["Subject"] = (
        config["mail"]
        .get("subject", "Printables: {total} new models")
        .format(total=total)
    )
    message["From"] = config["mail"]["from"]
    message["To"] = config["mail"]["to"]
    message.set_content(render_text(sections))
    message.add_alternative(render_html(sections), subtype="html")
    if dry_run:
        print(message.as_string())
        return
    with smtplib.SMTP(config["mail"].get("host", "localhost")) as smtp:
        smtp.send_message(message)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", type=Path, default=Path(__file__).resolve().parent / "watch.toml"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print mail instead of sending, do not update state.json",
    )
    parser.add_argument(
        "--reseed", action="store_true", help="move all watermarks to now, send nothing"
    )
    args = parser.parse_args()

    with open(args.config, "rb") as fp:
        config = tomllib.load(fp)
    state_path = args.config.with_name("state.json")
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    limit = config.get("limit", 50)
    max_pages = config.get("max_pages", 4)

    sections = []
    for search in config["search"]:
        query = search["query"]
        seeding = args.reseed or query not in state
        watermark = "" if seeding else state[query]
        try:
            items = collect(
                search, watermark, 1 if seeding else limit, 1 if seeding else max_pages
            )
        except Exception as error:
            print(f"{query}: {error}", file=sys.stderr)
            continue
        if items:
            state[query] = max(item["firstPublish"] for item in items)
        if seeding:
            print(
                f"{query}: watermark set to {state.get(query)}, not mailing",
                file=sys.stderr,
            )
            continue
        items = [item for item in items if matches(item, search)]
        if items:
            sections.append((search, items))

    if sections:
        send_mail(config, sections, args.dry_run)
    if not args.dry_run:
        state["_updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        state_path.write_text(json.dumps(state, indent=1))


if __name__ == "__main__":
    main()
