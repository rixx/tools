#!/usr/bin/env -S uv run
# /// script
# dependencies = [
#   "click",
#   "httpx",
#   "rt",
#   "tqdm",
# ]
# ///

import json
import time

import click
import httpx
import rt.rest2
from tqdm import tqdm


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


def was_moved_from_destination(ticket_id, destination_queue, source_queue, tracker):
    """Check if ticket was previously moved from destination to source (reverse move)."""
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


@click.command()
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
@click.argument("source")
@click.argument("destination")
@click.argument("subject_pattern")
def automove(auth, dry_run, source, destination, subject_pattern):
    """Move tickets from SOURCE queue to DESTINATION queue.

    Moves all 'new' or 'open' tickets that do NOT match SUBJECT_PATTERN.
    Tickets that were previously moved from DESTINATION to SOURCE are skipped.
    """
    auth_data = json.load(open(auth))
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

    #pattern = re.compile(subject_pattern, re.IGNORECASE)
    pattern = subject_pattern

    tickets = list(tracker.search(
        queue=source_name,
        raw_query="(Status='new' OR Status='open')",
    ))
    moved = 0
    skipped_pattern = 0
    skipped_reverse = 0

    for ticket in tqdm(tickets, desc="Processing tickets"):
        subject = ticket.get("Subject", "")

        # Skip tickets that match the pattern
        if pattern in subject:
            skipped_pattern += 1
            continue

        # Skip tickets that were previously moved from destination to source
        if was_moved_from_destination(ticket["id"], dest_name, source_name, tracker):
            skipped_reverse += 1
            continue

        # Move the ticket
        if dry_run:
            click.echo(f"Would move ticket #{ticket['id']}: {subject}")
        else:
            try:
                tracker.edit_ticket(ticket["id"], Queue=dest_name)
                click.echo(f"Moved ticket #{ticket['id']}: {subject}")
            except Exception as e:
                click.echo(f"Failed to move ticket #{ticket['id']}: {e}")
                continue
        moved += 1

    click.echo()
    click.echo(f"{'Would move' if dry_run else 'Moved'}: {moved}")
    click.echo(f"Skipped (matched pattern): {skipped_pattern}")
    click.echo(f"Skipped (already active): {skipped_reverse}")


if __name__ == "__main__":
    automove()
