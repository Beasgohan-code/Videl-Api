# Videl-Api

Powerful multi-source music REST API for music bots and more — built to exceed [Eldian-Network/eldian-music-api](https://github.com/Eldian-Network/eldian-music-api) and [MakcRe/KuGouMusicApi](https://github.com/MakcRe/KuGouMusicApi).

## Features

| Feature | Eldian | KuGou | Videl-Api |
|---------|--------|-------|-----------|
| Audio download | YouTube only | KuGou only | **YouTube, SoundCloud, Bandcamp, Spotify, Deezer, Apple Music, Vimeo, Dailymotion, TikTok, Facebook, Instagram, X/Twitter + 1000+ yt-dlp sites** |
| Search | ❌ | ✅ | ✅ (multi-source) |
| Track info | ❌ | ✅ | ✅ (duration, artist, album, genres, lyrics, thumbnails) |
| Playlists/Albums | ❌ | ✅ | ✅ |
| Lyrics | ❌ | ✅ | ✅ |
| Direct stream URL | ❌ | ✅ | ✅ (`/v1/stream`) |
| API key auth | ✅ (MongoDB) | ❌ | ✅ (MongoDB + JSON fallback) |
| Admin/master keys | ❌ | ❌ | ✅ |
| Rate limiting | ❌ | ❌ | ✅ |
| CORS | ❌ | ❌ | ✅ |
| Auto temp-file cleanup | ✅ | ✅ | ✅ |
| Stale download pruning | ✅ | ❌ | ✅ |

## Quick Start

```bash
# Clone
git clone https://github.com/Beasgohan-code/Videl-Api.git
cd Videl-Api

# Create virtualenv
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure
cp .env.example .env
# (edit .env if needed)

# Run
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

API docs are available at `http://localhost:8000/docs`.

## Endpoints

### Meta

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/` | API info | No |
| GET | `/health` | Health check | No |
| GET | `/v1/sources` | List supported music sources | Yes |

### Search

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/v1/search?q=...&source=...&limit=...` | Search music | Yes |
| POST | `/v1/search` | Search music (JSON body) | Yes |

### Track / Info

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/v1/info?url=...&source=...` | Extract track/album/playlist info | Yes |
| POST | `/v1/info` | Extract info (JSON body) | Yes |

### Lyrics

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/v1/lyrics?url=...` | Get lyrics for a track | Yes |
| POST | `/v1/lyrics` | Get lyrics (JSON body) | Yes |

### Download / Stream

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/v1/download?url=...&format=...` | Download audio file | Yes |
| POST | `/v1/download` | Download audio (JSON body) | Yes |
| GET | `/v1/file/{folder}/{filename}` | Serve downloaded file (auto-cleanup) | Yes |
| GET | `/v1/stream?url=...` | Resolve direct stream URL | Yes |

### API Keys

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | `/v1/keys?owner_id=...` | Create a new API key | No (open bootstrap) |
| GET | `/v1/keys?owner_id=...` | List your API keys | Yes |
| DELETE | `/v1/keys/{key}?owner_id=...` | Revoke an API key | Yes |

## Authentication

By default API key auth is enabled (`API_KEYS=true` in `.env`). All music endpoints require an `X-API-Key` header.

- Create a key: `POST /v1/keys?owner_id=123` (no auth required — bootstrap)
- Use it: `curl -H "X-API-Key: <key>" http://localhost:8000/v1/sources`
- Admin keys: set `ADMIN_KEYS=key1,key2` in `.env` for master keys that bypass all checks
- Disable auth: set `API_KEYS=false` in `.env`

MongoDB is used for key storage when `MONGODB_URI` is reachable. Falls back to a local `api_keys.json` file automatically.

## Environment Variables

See `.env.example` for the full list. Key settings:

- `API_HOST`, `API_PORT` — bind address
- `API_KEYS` — enable/disable auth (default: true)
- `ADMIN_KEYS` — comma-separated master admin keys
- `MONGODB_URI` — MongoDB connection string (optional, falls back to JSON file)
- `RATE_LIMIT_ENABLED`, `RATE_LIMIT_DEFAULT` — per-key rate limiting
- `YT_DLP_FORMAT` — audio format selector (default: `bestaudio/best`)
- `YOUTUBE_PROXY` / `YOUTUBE_COOKIES` — proxy and cookies for restricted content
- `CORS_ORIGINS` — CORS allowed origins (default: `*`)

## Supported Sources

YouTube, SoundCloud, Bandcamp, Spotify, Deezer, Apple Music, Vimeo, Dailymotion, TikTok, Facebook, Instagram, X/Twitter — plus any of the 1000+ sites yt-dlp supports natively.

## Deployment

Run behind a reverse proxy (Nginx, Caddy, Traefik) with TLS. Set `API_KEYS=true`, use strong `ADMIN_KEYS`, and consider enabling rate limiting.

Example systemd service:

```ini
[Unit]
Description=Videl-Api Music API
After=network.target

[Service]
User=videl
WorkingDirectory=/opt/videl-api
EnvironmentFile=/opt/videl-api/.env
ExecStart=/opt/videl-api/.venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

## License

MIT
