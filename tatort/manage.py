import csv

import bs4
import requests


response = requests.get("https://de.wikipedia.org/wiki/Liste_der_Tatort-Folgen")
content = bs4.BeautifulSoup(response.content.decode(), "html.parser")
table = content.find("table")


def get_episode(line):
    fields = line.findAll("td")
    if not fields:
        return
    return {
        "episode": fields[0].text.strip(),
        "wiki_link": fields[1].find("a").attrs["href"],
        "titel": fields[1].text.strip(),
        "sender": fields[2].text.strip(),
        "datum": fields[3].text.strip(),
        "ermittler": fields[4].text.strip(),
        "ermittler_link": fields[4].find("a").attrs["href"],
        "ermittler_episode": fields[5].text.strip(),
        "kommentar": fields[8].text.strip(),
    }


episodes = [get_episode(line) for line in table.findAll("tr")]
episodes = [e for e in episodes if e]

print(f"{len(episodes)} Episoden gefunden!")

with open("episodes.csv", "w") as fp:
    writer = csv.DictWriter(
        fp,
        fieldnames=[
            "episode",
            "titel",
            "datum",
            "ermittler",
            "ermittler_episode",
            "wiki_link",
            "ermittler_link",
            "sender",
            "kommentar",
        ],
    )
    writer.writeheader()
    writer.writerows(episodes)
