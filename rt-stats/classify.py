import json

import click
import rt


def get_tracker(auth_data):
    tracker = rt.Rt(auth_data["url"], auth_data["username"], auth_data["password"])
    if not tracker.login() is True:
        click.echo("Error logging in!")
        sys.exit(-1)
    return tracker


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

    url = click.prompt("URL", default="https://rt.cccv.de/REST/1.0/")
    user = click.prompt("Username")
    password = click.prompt("Password")
    auth_data = {"url": url, "username": user, "password": password}
    get_tracker(auth_data)
    open(auth, "w").write(json.dumps(auth_data, indent=4) + "\n")
    click.echo()
    click.echo("Your authentication credentials have been saved to {}.".format(auth))
    click.echo()
