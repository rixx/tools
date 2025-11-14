#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
How to use:
- take a book out for a loan (1h)
- open web dev network console
- go to first page, hard-reload
- copy as curl, paste as COMMAND below
- replace the reference to the page with {page} – it's the last part of the file= path, just before the .jp2
- go to last page, copy as curl to find last page number
- set PAGES to the last page number
- set BOOK to the book identifier (or whatever you want in your file name)

Run.

Once downloads start failing (after 50-100 pages, usually), you'll have to copy a new curl command. The script won't re-download existing images.

Once you are done, you'll want to combine the images. Several options:
- just zip them and rename the archive to .cbz
- for not too many pages, use convert directly: convert *.jpg -quality 100 book.pdf
- if that gets killed, you'll have to convert in two steps:
    - ls *.jpg | xargs -I% convert % %.pdf
    - pdftk *.pdf cat output book.pdf && rm *.jpg.pdf
"""
import pathlib
import subprocess

BOOK = ""
PAGES = 0
COMMAND = """curl """


COMMAND += " --output {file_name}.gz"
# It's too easy to forget to set the scale, so we're hacking it
scale_key = "scale="
scale_loc = COMMAND.find(scale_key) + len(scale_key)
COMMAND = COMMAND[:scale_loc] + "1" + COMMAND[scale_loc + 1 :]

for page in range(1, PAGES + 1):
    page_format = f"{page:04}"
    file_name = f"{BOOK}-{page_format}.jpg"
    if pathlib.Path(file_name).exists():
        continue
    cmd = COMMAND.format(book=BOOK, page=page_format, file_name=file_name)
    subprocess.run(cmd, shell=True)
    file_type = subprocess.check_output(f"file {file_name}.gz", shell=True)
    if "gzip compressed data" in file_type.decode():
        subprocess.run(f"gunzip {file_name}.gz", shell=True)
    else:
        print(file_type.decode())
        subprocess.run(f"mv {file_name}.gz {file_name}", shell=True)
    file_type = subprocess.check_output(f"file {file_name}", shell=True)
    if "HTML" in file_type.decode():
        print(f"Failed to download page {page}")
        subprocess.run(f"rm {file_name}", shell=True)
        raise Exception("Download stopped, please enter new command!")
