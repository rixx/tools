import base64
import html
import subprocess

fname = "/home/rixx/tmp/downloads/original message before SpamAssassin.txt"
with open(fname) as f:
    content = f.read().split("\n")

encoding = 'Content-Transfer-Encoding: base64'
index = content.index(encoding)
content = base64.decodebytes((content[index + 2]).encode()).decode()
link_index = content.find("a href")
link_start = content[link_index + 8:]
url = link_start[:link_start.find('"')]
url = html.unescape(url)
# url = url.replace("&amp;", "&")
subprocess.call(["xdg-open", url])
subprocess.call(["rm", fname])
