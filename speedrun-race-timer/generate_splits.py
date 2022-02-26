MYLA = ["Mound", "Greenpath", "Dash", "Claw", "Blue Lake", "Sly", "Cdash"]

SPLITS = MYLA


result = "\n".join(
    [
        f"""        <tr>
          <td>{split}</td>
          <td><input type="text" /></td>
          <td><input type="text" /></td>
          <td></td>
          <td></td>
        </tr>"""
        for split in SPLITS
    ]
)

with open("index.html", "r") as fp:
    content = fp.read()

content = content.replace("#PLACEHOLDER", result)

with open("index.html", "w") as fp:
    fp.write(content)
