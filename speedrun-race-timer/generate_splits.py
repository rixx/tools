MYLA = ["Mound", "Greenpath", "Dash", "Claw", "Blue Lake", "Sly", "Cdash"]

SPLITS = MYLA



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
