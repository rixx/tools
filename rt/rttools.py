#!/usr/bin/env -S uv run
# /// script
# dependencies = [
#   "click",
#   "httpx",
#   "rt",
#   "tqdm",
# ]
# ///

import datetime as dt
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import click
import httpx
import rt.rest2
from tqdm import tqdm

# --- Utilities ---


def get_tracker(auth_data):
    return rt.rest2.Rt(
        url=auth_data["url"],
        http_auth=httpx.BasicAuth(
            auth_data["username"],
            auth_data["password"],
        ),
    )


def get_ticket_history(ticket_id, tracker):
    for _ in range(5):
        try:
            return tracker.get_ticket_history(ticket_id)
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


def get_time(time_str):
    return dt.datetime.strptime(time_str, "%Y-%m-%dT%H:%M:%SZ")


def format_delta(delta):
    days = delta.days
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    result = ""
    if days:
        result += f"{days}d "
    result += f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return result


def print_leaderboard(data, title):
    total = sum(data.values())
    print(f"#### {title}: {total}")
    for user, count in sorted(data.items(), key=lambda x: x[1], reverse=True):
        percent = count / total * 100
        print(f"  {user:20} {count:5} ({percent:5.1f}%)")
    print()


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
    if all(auth_data.get("key") for key in ("url", "username", "password")):
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


@cli.command()
@click.option(
    "-a",
    "--auth",
    type=click.Path(file_okay=True, dir_okay=False, allow_dash=False),
    default="auth.json",
    help="Path to auth data, defaults to ./auth.json.",
)
@click.argument("queue")
@click.option(
    "--users",
    type=click.STRING,
    help="Only show tickets created by these users",
    default="",
)
@click.option(
    "--ignore-users",
    type=click.STRING,
    help="Ignore tickets created by these users",
    default="",
)
def stats(queue, auth, ignore_users, users):
    "Show statistics for a queue"
    auth_data = load_auth(auth)
    tracker = get_tracker(auth_data)
    queue = tracker.get_queue(queue)
    tickets = tracker.search(queue=queue["Name"])
    users = set([u for u in users.split(",") if u])
    ignore_users = set([u for u in ignore_users.split(",") if u])
    if not users:
        ignore_users.add("RT_System")

    total = 0
    emails_received = 0
    action_types = defaultdict(int)
    actions_by_user = defaultdict(int)
    replies_by_user = defaultdict(int)
    time_first_reply = []
    unknown_types = set()

    for ticket in tqdm(tickets, desc="Tickets", total=float("inf")):
        total += 1
        history = get_ticket_history(ticket["id"], tracker)
        if not history:
            print("Giving up on this ticket, continuing without")
        response_time = None
        track_response_time = True
        for transaction in history:
            if "@" in transaction["Creator"]["Name"]:
                # Externally created user
                if transaction["Type"] in ("Correspond", "Create"):
                    emails_received += 1
                continue
            if users and transaction["Creator"]["Name"] not in users:
                continue
            if ignore_users and transaction["Creator"]["Name"] in ignore_users:
                continue
            if transaction["Type"] in (
                "AddReminder",
                "ResolveReminder",
                "AddWatcher",
                "DelWatcher",
                "SetWatcher",
                "ForwardTransaction",
                "Forward Transaction",
                "Forward Ticket",
                "CustomField",
                "Told",
                "DeleteLink",
            ):
                continue

            action_types[transaction["Type"]] += 1

            if transaction["Type"] == "Create":
                # This ticket was created by us, no need to track response times
                track_response_time = False

            if transaction["Type"] in (
                "Create",
                "AddLink",
                "Comment",
                "Set",
                "Status",
                "Take",
                "Give",
                "Steal",
            ):
                actions_by_user[transaction["Creator"]["Name"]] += 1
            elif transaction["Type"] == "Correspond":
                replies_by_user[transaction["Creator"]["Name"]] += 1
                if not response_time and track_response_time:
                    response_time = get_time(transaction["Created"]) - get_time(
                        ticket["Created"]
                    )
            else:
                unknown_types.add(transaction["Type"])
                continue
        if track_response_time and response_time and response_time > dt.timedelta():
            time_first_reply.append(response_time)

    print(f"\n\n#### {queue['Name']}")
    print(f"Found {total} tickets in queue {queue['Name']}.")
    print(f"Received {emails_received} incoming emails.\n")
    print_leaderboard(replies_by_user, "Replies")
    print_leaderboard(actions_by_user, "Actions")

    if time_first_reply:
        # exclude outliers on the upper end (top 1%)
        exclude = len(time_first_reply) // 100
        time_first_reply = sorted(time_first_reply)[: len(time_first_reply) - exclude]

        avg_time = sum(time_first_reply, dt.timedelta()) / len(time_first_reply)
        min_time = min(time_first_reply)
        max_time = max(time_first_reply)
        median_time = sorted(time_first_reply)[len(time_first_reply) // 2]

        print("#### Response times (without upper 1%)")
        print(f"Average response time: {format_delta(avg_time)}")
        print(f"Median response time:  {format_delta(median_time)}")
        print(f"Min response time:     {format_delta(min_time)}")
        print(f"Max response time:     {format_delta(max_time)}\n")

    print_leaderboard(action_types, "Action types")
    if unknown_types:
        print(f"\nUnknown types: {unknown_types}")


def ticket_has_been_modified(ticket_id, tracker):
    """Check if ticket has any Set transactions (indicating manual changes)."""
    history = get_ticket_history(ticket_id, tracker)
    if not history:
        return False

    for transaction in history:
        if transaction["Type"] == "Set":
            return True

        # TODO: get_transaction currently throws an HTTP 500
        # if transaction["Type"] == "Set":
        #     try:
        #         details = tracker.get_transaction(transaction["id"])
        #         if details.get("Field") == "Queue":
        #             old_value = details.get("OldValue", "")
        #             new_value = details.get("NewValue", "")
        #             if old_value == destination_queue and new_value == source_queue:
        #                 return True
        #     except Exception:
        #         continue
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
