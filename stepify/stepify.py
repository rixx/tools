import json
import os
import sys

import spotipy
import spotipy.util as util
import sqlite_utils

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
    return [
        song
        for song in db["songs"].rows
        if song["bpm"]
        and (165 <= song["bpm"] <= 180)
        and song.get("spotify") not in ["ignore", "no"]
    ]


def update_songs(db, songs):
    db["songs"].insert_all(songs, pk="id", replace=True, alter=True)


def main():
    token = util.prompt_for_user_token(
        username, scope="user-modify-playback-state playlist-modify-public"
    )
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

    for song in songs:
        if song["title"].lower() in track_titles:
            song["spotify"] = "yes"
            updates.append(song)
            new_songs += 1
        else:
            parts = song["artist"].split(" ")
            parts.sort(key=lambda x: len(x))
            artist = parts[-1]
            query = f"{song['title']} artist:{artist}"
            results = sp.search(q=query)["tracks"]
            found_tracks = results["items"]

            if results["total"] == 0:
                print(
                    f"Found no matches for Track '{song['title']}' by {song['artist']}"
                )
                song["spotify"] = "no"
                updates.append(song)
                continue

            print(
                f"Found {results['total']} matches for Track '{song['title']}' by {song['artist']}"
            )
            for index, track in enumerate(found_tracks):
                print(f"{index + 1}. {track['name']} by {track['artists'][0]['name']}")
            action = ""
            while not action or action[0] not in ["p", "a", "s", "n", "q", "i"]:
                action = input(
                    "What do you want to do? (p)lay, (a)dd, (s)uccess, (n)ext, (i)gnore, (q)uit: "
                )
                try:
                    if action and action[0] == "p":
                        selected = int(action[1:]) - 1 if len(action) > 1 else 0
                        sp.start_playback(uris=[found_tracks[selected]["uri"]])
                        action = None
                except Exception as e:
                    print(e)
                    action = None
                    pass
            if action == "q":
                break
            if action == "n":
                continue
            if action == "i":
                song["spotify"] = "ignore"
                updates.append(song)
            elif action == "s":
                song["spotify"] = "yes"
                updates.append(song)
                new_songs += 1
            elif action == "a":
                selected = int(action[1:]) - 1 if len(action) > 1 else 0
                sp.user_playlist_add_tracks(
                    username, playlist["id"], [found_tracks[selected]["uri"]]
                )
                song["spotify"] = "yes"
                updates.append(song)
                new_songs += 1

    print("Saving changes ...")
    update_songs(db, updates)

    print(f"Total stepmania songs:   {total_songs}")
    print(f"New songs in playlist:   {new_songs}")
    print(f"Total songs in playlist: {known_songs}")


# dict_keys(['album', 'artists', 'available_markets', 'disc_number', 'duration_ms', 'episode', 'explicit', 'external_ids', 'external_urls', 'href', 'id', 'is_local', 'name', 'popularity', 'preview_url', 'track', 'track_number', 'type', 'uri'])
# dict_keys(['album_type', 'artists', 'available_markets', 'external_urls', 'href', 'id', 'images', 'name', 'release_date', 'release_date_precision', 'total_tracks', 'type', 'uri'])
# dict_keys(['external_urls', 'href', 'id', 'name', 'type', 'uri'])


if __name__ == "__main__":
    main()
