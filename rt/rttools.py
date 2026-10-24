#!/usr/bin/env -S uv run
# /// script
# dependencies = [
#   "click",
#   "rt",
#   "tqdm",
# ]
# ///

import json
import sys
import time
from pathlib import Path

import click
from tqdm import tqdm

import rt.rest2

# --- Utilities ---


def get_tracker(auth_data):
    return rt.rest2.Rt(
        url=auth_data["url"],
        http_auth=(getattr(rt.rest2, "httpx2", None) or rt.rest2.httpx).BasicAuth(
            auth_data["username"],
            auth_data["password"],
        ),
    )


def fetch_ticket_history(ticket_id, tracker):
    items = []
    page = 1
    while True:
        response = tracker.session.get(
            f"{tracker.url}ticket/{ticket_id}/history",
            params={
                "fields": "Type,Creator,Created",
                "fields[Creator]": "Name",
                "page": page,
                "per_page": 100,
            },
        )
        response.raise_for_status()
        result = response.json()
        items.extend(
            {
                "Type": item["Type"],
                "Created": item["Created"],
                "Creator": item["Creator"]["Name"],
            }
            for item in result["items"]
        )
        if not result["items"] or len(items) >= result.get("total", 0):
            return items
        page += 1


def get_ticket_history(ticket_id, tracker):
    for _ in range(5):
        try:
            return fetch_ticket_history(ticket_id, tracker)
        except Exception:
            print(f"Failed to get ticket history for {ticket_id}")
            time.sleep(2)
    return None


def resolve_auth_path(auth_path):
    path = Path(auth_path)
    if not path.is_absolute():
        path = Path(__file__).parent / path
    return path


def load_auth(auth_path):
    path = resolve_auth_path(auth_path)
    return json.load(open(path))


# --- CLI ---


@click.group()
@click.version_option()
def cli():
    "RT ticket tools"


@cli.command()
@click.option(
    "-a",
    "--auth",
    type=click.Path(file_okay=True, dir_okay=False, allow_dash=False),
    default="auth.json",
    help="Path to save auth data to, defaults to ./auth.json.",
)
def auth(auth):
    "Save authentication credentials to a JSON file"
    auth_path = resolve_auth_path(auth)
    auth_data = {}
    if auth_path.exists():
        auth_data = json.load(open(auth_path))
    if all(auth_data.get(key) for key in ("url", "username", "password")):
        click.echo("Credentials are already present.")
        sys.exit(0)

    url = click.prompt("URL", default="https://rt.cccv.de/REST/2.0/")
    user = click.prompt("Username")
    password = click.prompt("Password")
    auth_data = {"url": url, "username": user, "password": password}
    tracker = get_tracker(auth_data)
    if not tracker.get_all_queues():
        click.echo("Error logging in!")
        sys.exit(-1)
    open(auth_path, "w").write(json.dumps(auth_data, indent=4) + "\n")
    click.echo()
    click.echo(f"Your authentication credentials have been saved to {auth_path}.")
    click.echo()


def ticket_has_been_modified(ticket_id, tracker):
    """Check if ticket has any Set transactions (indicating manual changes)."""
    history = get_ticket_history(ticket_id, tracker)
    if not history:
        return False

    for transaction in history:
        if transaction["Type"] == "Set":
            return True

    return False


@cli.command()
@click.option(
    "-a",
    "--auth",
    type=click.Path(file_okay=True, dir_okay=False, allow_dash=False),
    default="auth.json",
    help="Path to auth data, defaults to ./auth.json.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Don't actually move tickets, just show what would be moved.",
)
@click.option(
    "--silent",
    is_flag=True,
    help="Suppress all output.",
)
@click.argument("source")
@click.argument("destination")
@click.argument("subject_pattern")
def automove(auth, dry_run, silent, source, destination, subject_pattern):
    """Move tickets from SOURCE queue to DESTINATION queue.

    Moves all 'new' or 'open' tickets that do NOT match SUBJECT_PATTERN.
    Tickets that have been manually modified are skipped.
    """
    auth_data = load_auth(auth)
    tracker = get_tracker(auth_data)

    source_queue = tracker.get_queue(source)
    dest_queue = tracker.get_queue(destination)

    if not source_queue:
        click.echo(f"Error: Source queue '{source}' not found.")
        raise SystemExit(1)
    if not dest_queue:
        click.echo(f"Error: Destination queue '{destination}' not found.")
        raise SystemExit(1)

    source_name = source_queue["Name"]
    dest_name = dest_queue["Name"]

    pattern = subject_pattern

    tickets = list(
        tracker.search(
            queue=source_name,
            raw_query="(Status='new' OR Status='open')",
        )
    )
    moved = 0
    skipped_pattern = 0
    skipped_modified = 0

    for ticket in tqdm(tickets, desc="Processing tickets", disable=silent):
        subject = ticket.get("Subject", "")

        # Skip tickets that match the pattern
        if pattern in subject:
            skipped_pattern += 1
            continue

        # Skip tickets that have been manually modified
        if ticket_has_been_modified(ticket["id"], tracker):
            skipped_modified += 1
            continue

        # Move the ticket
        if dry_run:
            click.echo(f"Would move ticket #{ticket['id']}: {subject}")
        else:
            try:
                tracker.edit_ticket(ticket["id"], Queue=dest_name)
                if not silent:
                    click.echo(f"Moved ticket #{ticket['id']}: {subject}")
            except Exception as e:
                if not silent:
                    click.echo(f"Failed to move ticket #{ticket['id']}: {e}")
                continue
        moved += 1

    if not silent:
        click.echo()
        click.echo(f"{'Would move' if dry_run else 'Moved'}: {moved}")
        click.echo(f"Skipped (matched pattern): {skipped_pattern}")
        click.echo(f"Skipped (already active): {skipped_modified}")


if __name__ == "__main__":
    cli()
