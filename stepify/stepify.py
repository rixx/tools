import glob
import subprocess
from pathlib import Path


DEBUG = True


class SongException(Exception):
    pass


class Song:
    def __init__(self, path):
        self.path = path
        self.song_path = self.get_song_path()
        self.metadata = self.parse_metadata()
        self.title = self.metadata.get("title")
        self.artist = self.metadata.get("artist")
        if not (self.title and self.artist):
            raise SongException(
                f"Title or artist missing: {self.path}. Metadata: {self.metadata}"
            )
        self.bpms = self.parse_bpms()
        if not self.bpms:
            raise SongException(f"No BPM found: {self.path}")
        self.bpm = self.bpms[0] if len(self.bpms) == 1 else None
        self.seconds = self.get_duration()

    def get_song_path(self):
        files = list(self.path.parent.glob("*.ogg"))
        if not files:
            files = list(self.path.parent.glob("*.mp3"))
        if not files:
            raise SongException(
                f"No song file found for glob {self.path.parent / '*.ogg|mp3'}"
            )
        return files[0]

    def parse_metadata(self):
        # utf-8-sig strips BOMs
        with open(self.path, mode="r", encoding="utf-8-sig") as fp:
            metadata = {}
            for line in fp.readlines():
                if line.startswith("#NOTES"):
                    break
                if line.startswith("#"):
                    try:
                        key, value = line.strip().strip("#;").split(":", maxsplit=1)
                    except Exception as e:
                        if DEBUG:
                            print(f"Skipping metadata line: {line}")
                        continue
                    metadata[key.lower()] = value.strip()
        return metadata

    def parse_bpms(self):
        return [
            int(float(value.split("=")[-1]))
            for value in self.metadata["bpms"].split(",")
        ]

    def get_duration(self):
        data = subprocess.check_output(
            ["ffprobe", self.song_path], stderr=subprocess.STDOUT
        ).decode()
        duration_line = [
            line.strip()
            for line in data.split("\n")
            if line.strip().startswith("Duration")
        ][0]
        durations = duration_line[len("Duration: ") :].split(", ")[0].split(":")
        return int(float(durations[-1])) + 60 * int(durations[-2])


def get_songs(debug=False):
    songs = []
    for path in Path.home().glob(".stepmania*/Songs/**/**/*.sm"):
        try:
            songs.append(Song(path))
        except UnicodeDecodeError:
            continue
        except SongException as e:
            if DEBUG:
                print(e)
            continue
        except Exception as e:
            if DEBUG:
                print(path)
                raise
            continue
    return songs


def print_songs(songs):
    title_length = max(len(song.title) for song in songs)
    artist_length = max(len(song.artist) for song in songs)
    line = "| {0:" + str(title_length) + "} | {1:" + str(artist_length) + "} | {2:5} |"
    for song in songs:
        print(line.format(song.title, song.artist, song.bpm))

    total_duration = sum(song.seconds for song in songs)
    total_seconds = total_duration % 60
    total_minutes = total_duration // 60
    total_hours = total_minutes // 60
    total_minutes -= total_hours * 60
    print(
        f"Total duration: {total_hours} hours, {total_minutes:02d} minutes, {total_seconds:02d} seconds"
    )


def main():
    total_duration = 0
    songs = get_songs()
    print_songs(
        [
            song
            for song in songs
            if song.bpm and ((165 <= song.bpm <= 180) or (85 <= song.bpm <= 90))
        ]
    )


if __name__ == "__main__":
    main()
