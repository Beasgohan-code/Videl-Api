# Videl-Api

Powerful multi-source music REST API for music bots and more — built to exceed
[Eldian-Network/eldian-music-api](https://github.com/Eldian-Network/eldian-music-api)
and [MakcRe/KuGouMusicApi](https://github.com/MakcRe/KuGouMusicApi).

Integrates the best ideas from:
- **yt-dlp** — 1000+ sites, search, playlists
- **aria2c** — multipart parallel downloads (faster)
- **spotDL/spotify-downloader** — Spotify metadata, lyrics, album art
- **Tyrrrz/YoutubeDownloader** — metadata tagging, sponsorblock, cookies
- **bezzad/Downloader** — pause/resume, queue, concurrency control

## Capability Comparison

| Feature | Eldian | KuGou | spotDL | Videl-Api |
|---------|--------|-------|--------|-----------|
| Sources | YouTube only | KuGou only | YouTube+Spotify meta | **15+ sources, 1000+ sites** |
| Search | ❌ | ✅ | ✅ | ✅ (multi-source) |
| Track info | ❌ | ✅ | ✅ | ✅ (full metadata) |
| Playlists/Albums | ❌ | ✅ | ✅ | ✅ |
| Lyrics | ❌ | ✅ | ✅ | ✅ (5 providers) |
| Spotify metadata | ❌ | ❌ | ✅ | ✅ (spotdl integration) |
| Album art embedding | ❌ | ❌ | ✅ | ✅ |
| SponsorBlock | ❌ | ❌ | ❌ | ✅ |
| aria2c multipart | ❌ | ❌ | ❌ | ✅ |
| Download queue + pause/resume | ❌ | ❌ | ❌ | ✅ |
| API key auth | ✅ (MongoDB) | ❌ | ❌ | ✅ (MongoDB + JSON) |
| Rate limiting | ❌ | ❌ | ❌ | ✅ |
| CORS | ❌ | ❌ | ❌ | ✅ |
| Auto temp cleanup | ✅ | ✅ | ✅ | ✅ |

## Quick Start

```bash
git clone https://github.com/Beasgohan-code/Videl-Api.git
cd Videl-Api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env if needed
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

API docs: `http://localhost:8000/docs`

## Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | No | API info |
| GET | `/health` | No | Health + enabled features |
| GET | `/v1/sources` | Yes | List supported sources |
| GET | `/v1/search` | Yes | Search music |
| POST | `/v1/search` | Yes | Search (JSON body) |
| GET | `/v1/info` | Yes | Track/playlist/album info |
| POST | `/v1/info` | Yes | Info (JSON body) |
| GET | `/v1/lyrics` | Yes | Lyrics for a track URL |
| POST | `/v1/lyrics` | Yes | Lyrics (JSON body) |
| POST | `/v1/lyrics/search` | Yes | Lyrics by title + artist |
| GET | `/v1/metadata` | Yes | Spotify metadata enrichment |
| POST | `/v1/metadata` | Yes | Metadata (JSON body) |
| GET | `/v1/download` | Yes | Download audio file |
| POST | `/v1/download` | Yes | Download (JSON body) |
| POST | `/v1/download/queue` | Yes | Enqueue background download job |
| GET | `/v1/download/queue` | Yes | List all jobs |
| GET | `/v1/download/status/{id}` | Yes | Job status |
| POST | `/v1/download/cancel/{id}` | Yes | Cancel a job |
| GET | `/v1/file/{folder}/{file}` | Yes | Serve file (auto-cleanup) |
| GET | `/v1/stream` | Yes | Direct stream URL |
| POST | `/v1/keys` | No | Create API key (bootstrap) |
| GET | `/v1/keys` | Yes | List keys |
| DELETE | `/v1/keys/{key}` | Yes | Revoke key |

### Example: Download with Spotify metadata + lyrics

```bash
curl -X POST "http://localhost:8000/v1/download" \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://open.spotify.com/track/...","fetch_lyrics":true,"embed_metadata":true,"use_aria2c":true}'
```

### Example: Search SoundCloud

```bash
curl -H "X-API-Key: YOUR_KEY" \
  "http://localhost:8000/v1/search?q=lofi%20hip%20hop&source=soundcloud&limit=10"
```

### Example: Lyrics by title+artist

```bash
curl -X POST "http://localhost:8000/v1/lyrics/search" \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"title":"Blinding Lights","artist":"The Weeknd","provider":"synced"}'
```

## Authentication

`X-API-Key` header required on all music endpoints. Bootstrap your first key:

```
POST /v1/keys?owner_id=123   # no auth required
```

Set `ADMIN_KEYS` in `.env` for master keys. Disable auth with `API_KEYS=false`.
MongoDB is used when reachable; falls back to `api_keys.json` automatically.

## External Tools (optional, auto-detected)

| Tool | Purpose | Install |
|------|---------|---------|
| aria2c | Multipart parallel downloads (faster) | `apt install aria2` |
| ffmpeg | Audio conversion, post-processing | `apt install ffmpeg` |
| spotdl | Spotify metadata + audio matching | `pip install spotdl` |

Set `ARIA2C_PATH`, `FFMPEG_PATH`, `SPOTDL_PATH` in `.env` if not in PATH.

## Environment Variables

See `.env.example` for the full list. Highlights:

- `ARIA2C_ENABLED=true` — use aria2c for multipart downloads
- `ARIA2C_ARGS=-x 16 -s 16` — 16 connections per download
- `SPOTDL_ENABLED=true` — enable spotdl Spotify integration
- `SPOTIFY_CLIENT_ID/SECRET` — Spotify API credentials
- `LYRICS_PROVIDERS=synced,genius,musixmatch,azlyrics` — fallback order
- `METADATA_EMBED=true` — embed ID3 tags + album art
- `SPONSORBLOCK=true` — remove sponsored segments
- `DOWNLOAD_MAX_CONCURRENT=3` — max simultaneous download jobs

## Supported Sources

YouTube, YouTube Music, SoundCloud, Bandcamp, Spotify, Apple Music, Deezer,
Vimeo, Dailymotion, TikTok, Facebook, Instagram, X/Twitter, Piped, Invidious —
plus any of the 1000+ sites yt-dlp supports natively.

## Deployment

Run behind a reverse proxy (Nginx/Caddy/Traefik) with TLS. Use strong
`ADMIN_KEYS` and enable rate limiting.

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
