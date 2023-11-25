import datetime as dt
import json
import pathlib
import sys
from collections import defaultdict

import click
import httpx
import rt.rest2
from tqdm import tqdm


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
        # align users to 20 chars, counts to 5 chars and percent to 5 chars
        print(f"  {user:20} {count:5} ({percent:5.1f}%)")
    print()


def get_tracker(auth_data):
    return rt.rest2.Rt(
        url=auth_data["url"],
        http_auth=httpx.BasicAuth(
            auth_data["username"],
            auth_data["password"],
        ),
    )


@click.group()
@click.version_option()
def cli():
    "Classify RT tickets"


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
    auth_data = {}
    if pathlib.Path(auth).exists():
        auth_data = json.load(open(auth))
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
    open(auth, "w").write(json.dumps(auth_data, indent=4) + "\n")
    click.echo()
    click.echo(f"Your authentication credentials have been saved to {auth}.")
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
    auth = json.load(open(auth))
    rt = get_tracker(auth)
    queue = rt.get_queue(queue)
    tickets = rt.search(queue=queue["Name"])
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
        history = rt.get_ticket_history(ticket["id"])
        response_time = None
        track_response_time = True
        for transaction in history:
            if users and transaction["Creator"]["Name"] not in users:
                continue
            if ignore_users and transaction["Creator"]["Name"] in ignore_users:
                continue
            if "@" in transaction["Creator"]["Name"]:
                # Externally created user
                if transaction["Type"] in ("Correspond", "Create"):
                    emails_received += 1
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
    print(
        f"Found {total} tickets in queue {queue['Name']} and received {emails_received} incoming emails.\n"
    )
    print_leaderboard(replies_by_user, "Replies")
    print_leaderboard(actions_by_user, "Actions")

    if time_first_reply:
        # exclude outliers on the upper end (top 2%)
        exclude = len(time_first_reply) // 50
        time_first_reply = sorted(time_first_reply)[: len(time_first_reply) - exclude]

        avg_time = sum(time_first_reply, dt.timedelta()) / len(time_first_reply)
        min_time = min(time_first_reply)
        max_time = max(time_first_reply)
        median_time = sorted(time_first_reply)[len(time_first_reply) // 2]

        print("#### Response times (without upper 2%)")
        print(f"Average response time: {format_delta(avg_time)}")
        print(f"Median response time:  {format_delta(median_time)}")
        print(f"Min response time:     {format_delta(min_time)}")
        print(f"Max response time:     {format_delta(max_time)}\n")

    print_leaderboard(action_types, "Action types")
    if unknown_types:
        print(f"\nUnknown types: {unknown_types}")


if __name__ == "__main__":
    cli()
