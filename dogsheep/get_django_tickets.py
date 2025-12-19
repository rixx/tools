#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests",
#     "tqdm",
# ]
# ///
import json
import sqlite3
from datetime import datetime

import requests
from tqdm import tqdm

BASE_URL = "https://code.djangoproject.com/jsonrpc"
DJANGO_MAX_TICKET = 33562


def get_ticket(*, ticket_id, session):
    response = requests.post(
        BASE_URL,
        json.dumps(
            {
                "method": "ticket.get",
                "params": [ticket_id],
                "id": ticket_id,  # Could also be 23 every time
            }
        ),
        headers={"Content-Type": "application/json"},
    )
    response.raise_for_status()
    result = response.json()
    if result and result.get("error") and result["error"].get("code") == 404:
        return
    return result


def store_ticket(*, cursor, data):
    ticket_id = data["result"][0]
    ticket_data = data["result"][-1]
    ticket_data["created"] = ticket_data["time"]
    insert_keys = [
        "changetime",
        "owner",
        "keywords",
        "severity",
        "needs_tests",
        "version",
        "easy",
        "type",
        "status",
        "description",
        "reporter",
        "component",
        "has_patch",
        "stage",
        "needs_better_patch",
        "summary",
        "created",
        "needs_docs",
        "ui_ux",
        "resolution",
    ]
    insert_data = {
        key: get_value_from_data(key=key, value=ticket_data[key]) for key in insert_keys
    }
    insert_data["last_pulled_from_trac"] = datetime.now()
    insert_data["id"] = int(ticket_id)
    cursor.execute(
        f"""
        INSERT INTO tickets ({", ".join(insert_data.keys())})
        VALUES ({", ".join("?" for _ in range(len(insert_data)))})
    """,
        list(insert_data.values()),
    )


def get_value_from_data(*, key, value):
    if not value:
        return
    if key in ["changetime", "created"]:
        return datetime.strptime(value["__jsonclass__"][-1], "%Y-%m-%dT%H:%M:%S")
    if key in [
        "needs_tests",
        "easy",
        "has_patch",
        "needs_better_patch",
        "needs_docs",
        "ui_ux",
    ]:
        return bool(int(value))
    return value


def create_db(*, connection):
    cursor = connection.cursor()
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS tickets (
        id int primary key,
        created datetime,
        changetime datetime,
        last_pulled_from_trac datetime,
        stage text,
        status text,
        component text,
        type text,
        severity text,
        version text,
        resolution text,
        summary text,
        description text,
        owner text,
        reporter text,
        keywords text,
        easy boolean,
        has_patch boolean,
        needs_better_patch boolean,
        needs_tests boolean,
        needs_docs boolean,
        ui_ux boolean
    )"""
    )
    connection.commit()


def collect_data(*, connection, start=None, end=None, total=None):
    cursor = connection.cursor()
    start = start or 1
    if not end and total:
        end = start + total - 1
    if not end:
        end = DJANGO_MAX_TICKET
    with requests.Session() as session:
        for ticket_id in tqdm(range(start, end + 1)):
            data = get_ticket(ticket_id=ticket_id, session=session)
            if data:
                try:
                    store_ticket(data=data, cursor=cursor)
                except Exception as e:
                    print("FAILED " + str(ticket_id))
                    print(e)
                connection.commit()


def main():
    connection = sqlite3.connect("django_tickets.db")
    create_db(connection=connection)
    cursor = connection.cursor()
    result = cursor.execute(
        "SELECT id FROM tickets ORDER BY id DESC LIMIT 1"
    ).fetchone()
    start = result[0] if result else 0
    collect_data(connection=connection, start=start)


if __name__ == "__main__":
    main()
