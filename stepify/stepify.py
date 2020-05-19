import glob
import subprocess
from pathlib import Path


def parse_content(content):
    title = ""
    artist = ""
    bpm = None
    for line in content.split("\n"):
        if title and artist and bpm:
            break
        if line.startswith("#NOTES"):
            break
        if line.startswith("#TITLE:"):
            title = line[len("#TITLE:"):].strip(":;")
        elif line.startswith("#ARTIST:"):
            artist = line[len("#ARTIST:"):].strip(":;")
        elif line.startswith("#BPMS:"):
            bpms = line[len("#BPMS:"):].strip(":;")
            if "," in bpms:
                return
            try:
                bpm = int(float(bpms.split("=")[-1]))
            except:
                return
    if not bpm:
        return
    return {"title": title, "artist": artist, "bpm": bpm}


results = []
total_duration = 0
for path in glob.glob("Songs/**/**/*.sm"):
    try:
        with open(path) as fp:
            content = fp.read()
        song = parse_content(content)
        if song and ((165 <= song["bpm"] <= 180) or (80 <= song["bpm"] <= 90)):
            song_path = glob.glob(str(Path(path).parent / "*.ogg"))[0]
            data = subprocess.check_output(["ffprobe", song_path], stderr=subprocess.STDOUT).decode().split("\n")
            duration = [d.strip() for d in data if d.strip().startswith("Duration")][0][len("Duration: "):].split(", ")[0].split(":")
            seconds = int(float(duration[-1])) + 60*int(duration[-2])
            song["path"] = song_path
            song["duration"] = seconds
            total_duration += seconds
            results.append(song)
    except Exception as e:
        continue


title_length = max(len(s["title"]) for s in results)
artist_length = max(len(s["artist"]) for s in results)

line = "| {0:" + str(title_length) + "} | {1:" + str(artist_length) + "} | {2:5} |"
for song in results:
    print(line.format(song["title"], song["artist"], song["bpm"]))

total_seconds = total_duration % 60
total_minutes = total_duration // 60
total_hours = total_minutes // 60
total_minutes -= (total_hours * 60)
print(f"Total duration: {total_hours} hours, {total_minutes:02d} minutes, {total_seconds:02d} seconds")
