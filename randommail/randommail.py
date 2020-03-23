import random
import smtplib
from email.message import EmailMessage

import click

@click.command()
@click.argument("source", type=click.File("r"))
@click.argument("address")
@click.option('--number', default=1, help='Number of lines to select')
@click.option('--subject', default="Random reminder", help='Subject to use in the email')
@click.option('--template', type=click.File("r"), help='Template to use. Should contain the string "REPLACEME"')
def send(source, address, number, subject, template):
    """Simple program that greets NAME for a total of COUNT times."""
    selection = "\n".join(random.sample(list(source), number))
    if template:
        template = "\n".join(template)
    else:
        template = "REPLACEME"
    template = template.replace("REPLACEME", selection)

    message = EmailMessage()
    message.set_content(template)
    message["Subject"] = subject
    message["From"] = address
    message["To"] = address
    print(template)
    smtp = smtplib.SMTP("localhost")
    smtp.sendmail(message)

send()
