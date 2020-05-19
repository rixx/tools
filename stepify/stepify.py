import json
import os
import sys

import spotipy
import spotipy.util as util
import sqlite_utils
from tqdm import tqdm

with open("auth.json") as fp:
    data = json.load(fp)

CLIENT_ID = data["client_id"]
CLIENT_SECRET = data["client_secret"]
REDIRECT_URI = data["redirect_uri"]

os.environ["SPOTIPY_CLIENT_ID"] = CLIENT_ID
os.environ["SPOTIPY_CLIENT_SECRET"] = CLIENT_SECRET
os.environ["SPOTIPY_REDIRECT_URI"] = REDIRECT_URI

playlist_name = data["playlist"]
username = data["username"]


def get_playlist(sp):
    playlists = sp.current_user_playlists()
    playlist = [p for p in playlists["items"] if p["name"] == playlist_name]
    if not playlist:
        raise Exception(f"Playlist {playlist_name} not found.")
    return playlist[0]


def get_tracks(sp, playlist):
    results = sp.playlist(playlist["id"], fields="tracks,next")
    results["next"] = results["tracks"]["next"]
    tracks = results["tracks"]["items"]
    while results["next"]:
        results = sp.next(results)
        tracks += results["items"]
    return [track["track"] for track in tracks]


def get_songs(db):
    return [song for song in db["songs"].rows]


def update_songs(db, songs):
    db["songs"].insert_all(songs, pk="id", replace=True, alter=True)


def main():
    token = util.prompt_for_user_token(username, scope="playlist-modify-public")
    if not token:
        print("Can't get token for", username)
        return

    db = sqlite_utils.Database(sys.argv[-1])
    sp = spotipy.Spotify(auth=token)
    sp.trace = False

    playlist = get_playlist(sp)
    tracks = get_tracks(sp, playlist)
    track_titles = [track["name"].lower() for track in tracks]

    songs = get_songs(db)
    total_songs = len(songs)
    songs = [song for song in songs if not song.get("spotify")]
    new_songs = 0
    known_songs = total_songs - len(songs)
    updates = []

    for song in tqdm(songs):
        if song["title"].lower() in track_titles:
            song["spotify"] = True
            updates.append(song)
            print(f"We know that one: {song['title']}")

    update_songs(db, updates)

    print(f"Total stepmania songs:   {total_songs}")
    print(f"New songs in playlist:   {new_songs}")
    print(f"Total songs in playlist: {known_songs}")


# dict_keys(['album', 'artists', 'available_markets', 'disc_number', 'duration_ms', 'episode', 'explicit', 'external_ids', 'external_urls', 'href', 'id', 'is_local', 'name', 'popularity', 'preview_url', 'track', 'track_number', 'type', 'uri'])
# dict_keys(['album_type', 'artists', 'available_markets', 'external_urls', 'href', 'id', 'images', 'name', 'release_date', 'release_date_precision', 'total_tracks', 'type', 'uri'])
# dict_keys(['external_urls', 'href', 'id', 'name', 'type', 'uri'])


if __name__ == "__main__":
    main()
