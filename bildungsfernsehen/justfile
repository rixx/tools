set shell := ["bash", "-euo", "pipefail", "-c"]
set quiet
set fallback
set default-list

# Serve the hub on http://127.0.0.1:8765 (foreground)
run:
    ./hub.py serve

# Start server if needed, resync, open in browser
open:
    ./hub.py open

# Resync all playlists from YouTube
sync:
    ./hub.py sync

# Run the test suite
test *args="tests":
    uvx --with fastapi,uvicorn,httpx,yt-dlp,google-auth-oauthlib,requests,pytest pytest -q -p no:warnings {{ args }}
