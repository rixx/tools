import textwrap

import bs4
import inquirer

from mastodon import Mastodon


def main():
    # only on first run!
    # Mastodon.create_app(
    #     "rixxtools",
    #     api_base_url="https://chaos.social",
    #     to_file="rixxtools_client.secret",
    # )

    # BEGIN uncomment when logged out
    # mastodon = Mastodon(
    #     client_id = 'rixxtools_client.secret',
    #     api_base_url = 'https://chaos.social'
    # )
    # mastodon.log_in(
    #     'email@example.org',
    #     'supersecretpassword',
    #     to_file = 'rixxtools_user.secret'
    # )
    # return
    # END uncomment when logged out
    mastodon = Mastodon(
        access_token="rixxtools_user.secret",
        api_base_url="https://chaos.social",
        ratelimit_method="wait",
    )
    last_max_id = open("last_id", "r").read().strip()

    while True:
        statuses = mastodon.account_statuses(id=2, max_id=last_max_id)

        for status in statuses:
            display_status(status)
            if not should_keep_status(status):
                remove_status(status, mastodon)
            last_max_id = status["id"]
            write_last_id(last_max_id)


def write_last_id(num):
    with open("last_id", "w") as fp:
        fp.write(str(num))


def display_status(status, text_width=70):
    status_line_top = f"[{status['visibility']}] {'REPLY' if status['in_reply_to_id'] else ''}{' REBLOG' if status.get('reblog') else ''} · {status['created_at'].strftime('%Y-%m-%d %H:%M')}"
    status_line_bottom = f"{status['reblogs_count']} boosts · {status['favourites_count']} favs · {status['replies_count']} replies"
    buffer_width = text_width + 2
    print_lines = [status_line_top, ""]

    if status["spoiler_text"]:
        print_lines += [f"{status['spoiler_text']} [SHOW LESS]", ""]

    lines = (status["content"] or status.get("reblog", {}).get("content") or "").split("</p><p>")
    for line in lines:
        text = bs4.BeautifulSoup(line, "html.parser").text
        print_lines += textwrap.wrap(text, text_width)

    if status["media_attachments"]:
        print_lines.append("")
        print_lines.append(f"* with media files")

    print_lines.append("")
    print_lines.append(status_line_bottom)
    print_lines.append("")
    print_lines.append(f"https://chaos.social/web/@rixx/{status['id']}")

    print("┏" + "━" * buffer_width + "┓")
    print("┃" + " " * buffer_width + "┃")
    for line in print_lines:
        print("┃ " + line.ljust(text_width) + " ┃")
    print("┃" + " " * buffer_width + "┃")
    print("┗" + "━" * buffer_width + "┛")


def should_keep_status(status):
    if status["reblogs_count"] > 10:
        print(f"Keeping because it has {status['reblogs_count']} boosts")
        return True
    if status["favourites_count"] > 20:
        print(f"Keeping because it has {status['favourites_count']} favs")
        return True
    return inquirer.list_input(
        message="Keep status?",
        choices=[("yes", True), ("no", False)],
        default=True,
        carousel=True,
    )


def remove_status(status, mastodon):
    print("DELETING")
    if status["account"]["id"] == 2:
        mastodon.status_delete(status["id"])
    else:
        mastodon.status_unreblog(status["id"])


if __name__ == "__main__":
    main()
