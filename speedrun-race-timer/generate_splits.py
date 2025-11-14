#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
MYLA = ["Mound", "Greenpath", "Dash", "Claw", "Blue Lake", "Sly", "Cdash"]

TE = ["Mound", "Greenpath", "Dash", "Blue Lake", "Elder Hu", "Claw", "Glade", "Gorgeous Husk", "Lantern", "Cdash", "Shade Soul", "Lurien", "BV", "LK", "FC", "Hornet", "Shade Cloak", "Markoth", "Gorb", "Monomon", "No Eyes", "Marmu", "TL", "Galien", "Herrah", "WP Entrance", "WP Exit", "Void Heart", "Black Egg", "THK"]

TE_SCSBCP = ["Mound", "Greenpath", "Dash", "Blue Lake", "Elder Hu", "Claw", "Glade", "Gorgeous Husk", "Lantern", "Cdash", "Wraiths", "No Eyes", "Gorb", "BV", "LK", "Dream Gate", "Hornet", "Shriek", "Shade Cloak", "Markoth", "Lurien", "FC", "Monomon", "Marmu", "TL", "Herrah", "WP Entrance", "WP Exit", "Void Heart", "Black Egg", "THK"]

ALL_SKILLS = ["Mound", "Greenpath", "Dash", "Claw", "Blue Lake", "Gorgeous Husk", "Dash Slash", "Shade Soul", "Dive", "King's", "Cdash", "Ddark", "Dnail", "Lurien", "Basin", "BV", "Hornet", "Cyclone", "Monomon", "Great Slash", "Wraiths", "Herrah", "Shade Cloak", "Enter THK"]

ANY = ["Mound", "Greenpath", "Dash quitout", "Claw quitout", "Blue Lake", "Watcher room", "Lurien room", "Sly room", "Cdash quitout", "Monomon", "QGA", "Beasts Den", "Herrah", "Enter THK"]

POP = ["Mound", "Greenpath", "Dash", "Blue Lake", "Elder Hu", "Claw", "Galien", "Xero", "Gorgeous Husk", "Lantern", "Cdash", "Shade Soul", "Dive", "Tyrant", "Basin", "BV", "LK", "Failed Champ", "Gorb", "No Eyes", "Enter White Palace", "Enter Path of Pain"]

ONE_07 = ["Fury", "Mound", "Greenpath", "Dash", "Claw", "City", "Dive", "Storerooms", "Cdash", "Ddark", "Soul Eater", "Shade Soul", "Tyrant", "Flukenest", "Dung Defender", "BV", "LK", "Failed Champ", "Cyclone", "Grimm Lantern", "Unn", "Storerooms Fragment", "Thorns", "Greenpath Fragment", "Wraiths", "No Eyes", "CG2", "Deep Focus", "King's Arena", "Hornet", "Shade Cloak", "Markoth", "Quick Slash", "TMG", "Bretta", "Mantis Lords", "Fungal Shard", "Monomon", "Love Key", "Marmu", "Herrah", "Galien", "Nosk", "Hive", "Hiveblood", "Collector", "Lurien", "Nail hut", "White Defender", "Sly", "Seer ascended", "Flower Quest", "Colo 1", "Colo 2", "Colo 3", "Nail hut", "White palace", "Void Heart", "NKG", "GPZ", "Enter Radiance",
]

AWR = ["Mound", "Greenpath", "Dash", "Blue Lake", "Mantis Claw", "RG Root", "Waterways Root", "City Root", "Cdash", "Cliffs Root", "Crossroads Root", "Mound Root", "Fungal Root", "Glade Root", "Gardens Root", "Greenpath Root", "Deepnest Root", "Hive Root"]

SPLITS = ANY
RUNNERS = 2

runner_lines = '          <td><input type="text" /></td>\n' * RUNNERS
runner_headers = '          <th contenteditable>R1 (editme)</th>' * RUNNERS
result = "\n".join(
    [
        f"""        <tr>
          <td>{split}</td>
          {runner_lines}
          <td></td>
          <td></td>
        </tr>"""
        for split in SPLITS + ["gg"]
    ]
)

with open("template.html", "r") as fp:
    content = fp.read()

content = content.replace("#PLACEHOLDER", result)
content = content.replace("#RUNNERS", runner_headers)

with open("index.html", "w") as fp:
    fp.write(content)
