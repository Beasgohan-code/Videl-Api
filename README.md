# Videl-Api

Powerful multi-source music & stream REST API for music bots and more — built to exceed
[Eldian-Network/eldian-music-api](https://github.com/Eldian-Network/eldian-music-api)
and [MakcRe/KuGouMusicApi](https://github.com/MakcRe/KuGouMusicApi).

Integrates the best ideas from:
- **yt-dlp** — 1000+ sites, search, playlists
- **aria2/aria2** — multipart parallel downloads, JSON-RPC API
- **spotDL/spotify-downloader** — Spotify metadata, lyrics, album art
- **Tyrrrz/YoutubeDownloader** — metadata tagging, sponsorblock, cookies
- **bezzad/Downloader** — pause/resume, queue, concurrency control
- **nilaoda/N_m3u8DL-RE** — HLS/DASH/MSS streaming, AES-128 decryption, multi-thread
- **nilaoda/N_m3u8DL-CLI** — AES-128-CBC decryption, custom headers, segment range
- **globocom/m3u8** — Python m3u8/HLS playlist parser
- **Eldian-Network/eldian-music-api** — fully cloned, credits changed to Videl

## Capability Comparison

| Feature | Eldian | KuGou | spotDL | Videl-Api |
|---------|--------|-------|--------|-----------|
| Sources | YouTube only | KuGou only | YouTube+Spotify meta | **17+ sources, 1000+ sites** |
| Search | ❌ | ✅ | ✅ | ✅ (multi-source) |
| Track info | ❌ | ✅ | ✅ | ✅ (full metadata) |
| Playlists/Albums | ❌ | ✅ | ✅ | ✅ |
| Lyrics | ❌ | ✅ | ✅ | ✅ (5 providers) |
| Spotify metadata | ❌ | ❌ | ✅ | ✅ (spotdl integration) |
| Album art embedding | ❌ | ❌ | ✅ | ✅ |
| SponsorBlock | ❌ | ❌ | ❌ | ✅ |
| aria2c multipart | ❌ | ❌ | ❌ | ✅ |
| M3U8/HLS/DASH | ❌ | ❌ | ❌ | ✅ (N_m3u8DL) |
| AES-128 decryption | ❌ | ❌ | ❌ | ✅ |
| Download queue + pause/resume | ❌ | ❌ | ❌ | ✅ |
| aria2 JSON-RPC | ❌ | ❌ | ❌ | ✅ |
| API key auth | ✅ (MongoDB) | ❌ | ❌ | ✅ (MongoDB + JSON) |
| Rate limiting | ❌ | ❌ | ❌ | ✅ |
| CORS | ❌ | ❌ | ❌ | ✅ |
| Auto temp cleanup | ✅ | ✅ | ✅ | ✅ |
| Eldian source (credits→Videl) | — | — | — | ✅ (`/eldian/`) |

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

### Meta
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | No | API info |
| GET | `/health` | No | Health + enabled features |
| GET | `/v1/sources` | Yes | List supported sources |

### Search
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/v1/search` | Yes | Search music |
| POST | `/v1/search` | Yes | Search (JSON body) |

### Track / Info
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/v1/info` | Yes | Track/playlist/album info |
| POST | `/v1/info` | Yes | Info (JSON body) |

### Lyrics
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/v1/lyrics` | Yes | Lyrics for a track URL |
| POST | `/v1/lyrics` | Yes | Lyrics (JSON body) |
| POST | `/v1/lyrics/search` | Yes | Lyrics by title + artist |

### Metadata (Spotify)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/v1/metadata` | Yes | Spotify metadata enrichment |
| POST | `/v1/metadata` | Yes | Metadata (JSON body) |

### Download (yt-dlp)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/v1/download` | Yes | Download audio file |
| POST | `/v1/download` | Yes | Download (JSON body) |
| POST | `/v1/download/queue` | Yes | Enqueue background download job |
| GET | `/v1/download/queue` | Yes | List all jobs |
| GET | `/v1/download/status/{id}` | Yes | Job status |
| POST | `/v1/download/cancel/{id}` | Yes | Cancel a job |
| GET | `/v1/file/{folder}/{file}` | Yes | Serve file (auto-cleanup) |
| GET | `/v1/stream` | Yes | Direct stream URL |

### M3U8 / HLS / DASH (N_m3u8DL + globocom/m3u8)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/v1/m3u8/parse` | Yes | Parse M3U8/HLS playlist |
| POST | `/v1/m3u8/download` | Yes | Download M3U8/HLS stream |
| POST | `/v1/m3u8/download/queue` | Yes | Enqueue M3U8 background job |
| GET | `/v1/m3u8/download/queue` | Yes | List M3U8 jobs |
| GET | `/v1/m3u8/download/status/{id}` | Yes | M3U8 job status |
| POST | `/v1/m3u8/download/cancel/{id}` | Yes | Cancel M3U8 job |

### aria2c JSON-RPC (aria2/aria2)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/v1/aria2/add` | Yes | Add download to aria2 RPC |
| GET | `/v1/aria2/status/{gid}` | Yes | aria2 download status |
| POST | `/v1/aria2/remove/{gid}` | Yes | Remove aria2 download |

### API Keys
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/v1/keys` | No | Create API key (bootstrap) |
| GET | `/v1/keys` | Yes | List keys |
| DELETE | `/v1/keys/{key}` | Yes | Revoke key |

### Eldian (cloned, credits→Videl)
The `/eldian/` directory contains the full Eldian Music API source with all credits
changed from "Eldian Network" to "Videl-Api". Run separately:
```
cd eldian && pip install -r requirements.txt && python -m uvicorn app.main:app
```

## Examples

### Download with Spotify metadata + lyrics + aria2c

```bash
curl -X POST "http://localhost:8000/v1/download" \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://open.spotify.com/track/...","fetch_lyrics":true,"embed_metadata":true,"use_aria2c":true}'
```

### Parse an M3U8/HLS playlist

```bash
curl -X POST "http://localhost:8000/v1/m3u8/parse" \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com/stream.m3u8"}'
```

### Download M3U8 with AES-128 decryption + 16 threads

```bash
curl -X POST "http://localhost:8000/v1/m3u8/download" \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com/stream.m3u8","max_threads":16,"decrypt":true,"merge_method":"ffmpeg"}'
```

### Add download to aria2c

```bash
curl -X POST "http://localhost:8000/v1/aria2/add" \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"uris":["https://example.com/file.zip"],"max_connections":16,"split":16}'
```

### Search SoundCloud

```bash
curl -H "X-API-Key: YOUR_KEY" \
  "http://localhost:8000/v1/search?q=lofi%20hip%20hop&source=soundcloud&limit=10"
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
| aria2c | Multipart parallel downloads + JSON-RPC | `apt install aria2` |
| ffmpeg | Audio conversion, M3U8 merge muxing | `apt install ffmpeg` |
| spotdl | Spotify metadata + audio matching | `pip install spotdl` |
| cryptography | AES-128-CBC decryption for HLS | `pip install cryptography` |

Set `ARIA2C_PATH`, `FFMPEG_PATH`, `SPOTDL_PATH` in `.env` if not in PATH.

Enable aria2c RPC: `ARIA2C_RPC_ENABLED=true` + run `aria2c --enable-rpc --rpc-secret=...`

## Environment Variables

See `.env.example` for the full list. Highlights:

- `ARIA2C_ENABLED=true` — use aria2c for multipart yt-dlp downloads
- `ARIA2C_ARGS=-x 16 -s 16` — 16 connections per download
- `ARIA2C_RPC_ENABLED=true` — enable aria2c JSON-RPC endpoints
- `M3U8_ENABLED=true` — enable M3U8/HLS/DASH downloader
- `M3U8_MAX_THREADS=16` — segment download threads
- `M3U8_MERGE_METHOD=binary` — `binary` or `ffmpeg`
- `M3U8_DECRYPT=true` — AES-128-CBC automatic decryption
- `SPOTDL_ENABLED=true` — enable spotdl Spotify integration
- `SPOTIFY_CLIENT_ID/SECRET` — Spotify API credentials
- `LYRICS_PROVIDERS=synced,genius,musixmatch,azlyrics` — fallback order
- `METADATA_EMBED=true` — embed ID3 tags + album art
- `SPONSORBLOCK=true` — remove sponsored segments
- `DOWNLOAD_MAX_CONCURRENT=3` — max simultaneous download jobs

## Supported Sources

YouTube, YouTube Music, SoundCloud, Bandcamp, Spotify, Apple Music, Deezer,
Vimeo, Dailymotion, TikTok, Facebook, Instagram, X/Twitter, Piped, Invidious,
M3U8/HLS, MPEG-DASH — plus any of the 1000+ sites yt-dlp supports natively.

## Deployment

Run behind a reverse proxy (Nginx/Caddy/Traefik) with TLS. Use strong
`ADMIN_KEYS` and enable rate limiting.

```ini
[Unit]
Description=Videl-Api Music & Stream API
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
