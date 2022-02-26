MYLA = ["Mound", "Greenpath", "Dash", "Claw", "Blue Lake", "Sly", "Cdash"]

TE = ["Mound", "Greenpath", "Dash", "Blue Lake", "Elder Hu", "Claw", "Glade", "Gorgeous Husk", "Lantern", "Cdash", "Lurien", "BV", "LK", "FC", "Hornet", "Shade Cloak", "Markoth", "Gorb", "Monomon", "No Eyes", "Marmu", "TL", "Galien", "Herrah", "WP Entrance", "WP Exit", "Void Heart", "Black Egg", "THK"]

TE_SCSBCP = ["Mound", "Greenpath", "Dash", "Blue Lake", "Elder Hu", "Claw", "Glade", "Gorgeous Husk", "Lantern", "Cdash", "Wraiths", "No Eyes", "Gorb", "BV", "LK", "Dream Gate", "Hornet", "Shriek", "Shade Cloak", "Markoth", "Lurien", "FC", "Monomon", "Marmu", "TL", "Herrah", "WP Entrance", "WP Exit", "Void Heart", "Black Egg", "THK"]

ALL_SKILLS = ["Mound", "Greenpath", "Dash", "Claw", "Blue Lake", "Gorgeous Husk", "Dash Slash", "Shade Soul", "Dive", "King's", "Cdash", "Ddark", "Dnail", "Lurien", "Basin", "BV", "Hornet", "Cyclone", "Monomon", "Great Slash", "Wraiths", "Herrah", "Shade Cloak", "Enter THK"]

ANY = ["Mound", "Greenpath", "Dash", "Claw", "Blue Lake", "Watcher Room", "Lurien", "Lantern", "Cdash", "Monomon", "QG", "Beasts Den", "Herrah", "Enter THK"]

SPLITS = TE_SCSBCP
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
        for split in SPLITS
    ]
)

with open("index.html", "r") as fp:
    content = fp.read()

content = content.replace("#PLACEHOLDER", result)
content = content.replace("#RUNNERS", runner_headers)

with open("index.html", "w") as fp:
    fp.write(content)
