# bildungsfernsehen

Local web UI for a YouTube watch-later playlist: random pick with duration/channel filters, skip marks, watched/removed state, browse + sort, history. Videos open on YouTube.

## run

```
./hub.py open           # start server if needed, resync, open browser (fish: `,bildungsfernsehen`)
./hub.py                # serve on http://127.0.0.1:8765 in the foreground (`just run`)
./hub.py add <url>      # add a playlist from the shell
./hub.py sync           # resync all playlists
./hub.py auth           # connect the YouTube account (see below)
just test
```

Data in `data/` (gitignored): `hub.sqlite`, `client_secret.json`, `token.json`, `serve.log`. API in `API.md`.

## youtube account (optional, recommended)

Without it: `yt-dlp` reads the public playlist (title, duration, channel, views in one request; publish dates one request per video in the background). Add dates are unknown, YouTube is never modified.

With it: YouTube Data API gives real add dates, publish dates and durations in one pass, and watched/remove delete the video from the YouTube playlist (undo re-inserts it).

Setup, once:

1. https://console.cloud.google.com → new project → APIs & Services → enable "YouTube Data API v3".
2. OAuth consent screen: external, add your own Google account as test user. Scope `…/auth/youtube`.
3. Credentials → create OAuth client ID → Desktop app → download JSON → save as `data/client_secret.json`.
4. `./hub.py auth` opens the browser, stores `data/token.json`. Next sync uses the API.

Quota: 10 000 units/day. A sync costs ~6 units per 50 videos, each delete/insert 50.

## how it works

* Pick = uniform random among active videos matching the filters with the lowest skip count in that set. Skipped videos come back only when every candidate has been skipped as often.
* `added_at` without API = first time the hub saw the video.
* Resync keeps hub state; videos deleted on YouTube become `gone`, re-added ones come back.
