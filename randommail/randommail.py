#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "click",
# ]
# ///
import random
import smtplib
from email.message import EmailMessage

import click


@click.command()
@click.argument("source", type=click.File("r"))
@click.argument("address")
@click.option("--number", default=1, help="Number of lines to select")
@click.option(
    "--subject", default="Random reminder", help="Subject to use in the email"
)
@click.option(
    "--template",
    type=click.File("r"),
    help='Template to use. Should contain the string "REPLACEME"',
)
def send(source, address, number, subject, template):
    """Simple program that greets NAME for a total of COUNT times."""
    l = [element.strip() for element in list(source)]
    l = [element for element in l if element and not element.startswith("#")]
    selection = "\n".join(random.sample(l, number))
    if template:
        template = "".join(template)
    else:
        template = "REPLACEME"
    template = template.replace("REPLACEME", selection)

    message = EmailMessage()
    message.set_content(template)
    message["Subject"] = subject
    message["From"] = address
    message["To"] = address
    smtp = smtplib.SMTP("localhost")
    smtp.send_message(message)


send()
