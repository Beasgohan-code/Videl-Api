# Videl-Api — Ultimate Multi-Source Media REST API

Powerful all-in-one media API for music bots, anime streaming, manga scraping, and more — exceeding VYRON, Eldian, KuGouMusicApi, and N_m3u8DL.

## What's Integrated

| Project | Features Integrated |
|---------|-------------------|
| **yt-dlp** | 1000+ sites, search, playlists, music/video download |
| **aria2/aria2** | Multipart parallel downloads (-x16 -s16), JSON-RPC API |
| **spotDL/spotify-downloader** | Spotify metadata, lyrics, album art, YouTube audio matching |
| **Tyrrrz/YoutubeDownloader** | Metadata tagging, SponsorBlock, cookies, format selection |
| **bezzad/Downloader** | Pause/resume, queue, concurrency control |
| **nilaoda/N_m3u8DL-RE** | HLS/DASH/MSS streaming, AES-128 decryption, multi-thread |
| **nilaoda/N_m3u8DL-CLI** | AES-128-CBC decryption, custom headers, segment range |
| **globocom/m3u8** | Python m3u8/HLS playlist parser |
| **Eldian-Network/eldian-music-api** | Fully cloned, all credits changed to Videl (`/eldian/`) |
| **Telegram WebApp** | TypeScript key dashboard, tier-based limits, owner access |

## Supported Sources (17+ categories, 1000+ sites)

**Music:** YouTube, YouTube Music, SoundCloud, Bandcamp, Spotify, Apple Music, Deezer, Piped, Invidious

**Anime:** AnimePahe, AnimeFlix, Zoro/AniWatch, GogoAnime, KickassAnime, AnimeWorld, 9Anime, Putlocker

**Manga:** MangaDex, MangaKakalot, Manganelo, Webtoons, Manhwa

**Media:** M3U8/HLS, MPEG-DASH, YTS Movies, 1337x, The Pirate Bay

## Capability Comparison

| Feature | Eldian | KuGou | VYRON | Videl-Api |
|---------|--------|-------|-------|-----------|
| Sources | YouTube only | KuGou only | YouTube+Spotify | **1000+ sites across music/anime/manga/media** |
| Search | ❌ | ✅ | ✅ | ✅ (all categories) |
| Track/Anime/Manga info | ❌ | ✅ | ✅ | ✅ (full metadata) |
| Lyrics | ❌ | ✅ | ✅ (LRCLIB) | ✅ (5 providers) |
| Spotify metadata | ❌ | ❌ | ✅ | ✅ (spotDL integration) |
| Album art embedding | ❌ | ❌ | ✅ | ✅ |
| SponsorBlock | ❌ | ❌ | ❌ | ✅ |
| aria2c multipart | ❌ | ❌ | ✅ | ✅ |
| M3U8/HLS/DASH | ❌ | ❌ | ❌ | ✅ (N_m3u8DL) |
| AES-128 decryption | ❌ | ❌ | ❌ | ✅ |
| Download queue + pause/resume | ❌ | ❌ | ❌ | ✅ |
| aria2 JSON-RPC | ❌ | ❌ | ❌ | ✅ |
| API key scopes + expiry | ❌ | ❌ | ✅ | ✅ (free/pro/owner tiers) |
| Per-key quotas (req + bytes) | ❌ | ❌ | ✅ | ✅ |
| Key rotation (no rotation) | ❌ | ❌ | ✅ | ✅ |
| Bearer tokens (vyt_) | ❌ | ❌ | ✅ | ✅ (15-min TTL) |
| Owner tokens (vown_) | ❌ | ❌ | ✅ | ✅ (30-day TTL) |
| SSRF guard + credential redaction | ❌ | ❌ | ✅ | ✅ |
| Prometheus metrics | ❌ | ❌ | ✅ | ✅ |
| Telegram WebApp dashboard | ❌ | ❌ | ❌ | ✅ (TypeScript + CSS) |
| Eldian source (credits→Videl) | — | — | — | ✅ (`/eldian/`) |

## Quick Start

```bash
git clone https://github.com/Beasgohan-code/Videl-Api.git
cd Videl-Api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env: set TELEGRAM_BOT_TOKEN, ADMIN_KEYS, etc.
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

API docs: `http://localhost:8000/docs`

WebApp: `http://localhost:8000/app` (open in Telegram)

## Authentication

### API Keys (`videl_*`)
- Create: `POST /v1/keys?owner_id=123` (no auth — bootstrap)
- Use: `X-API-Key: videl_...` header
- Tiers: `free` (100 req/day), `pro` (1,000 req/day + downloads), `owner` (unlimited)
- Scopes: `read`, `search`, `download`, `admin`
- Per-key rate limit override, expiry, daily/monthly quotas

### Bearer Tokens (`vyt_*`)
- 15-minute TTL for WebView/Mini App
- `POST /v1/token` — mint short-lived token

### Owner Tokens (`vown_*`)
- 30-day TTL, HMAC-signed
- Full access at 120 req/min
- `X-Owner-Token` header or `X-API-Key: vown_...`

## Endpoints

### Meta
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | No | API info |
| GET | `/health` | No | Health + features |
| GET | `/v1/sources` | Yes | List all sources |
| GET | `/v1/metrics` | No | Prometheus metrics |

### Telegram WebApp
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/app` | No | WebApp entry point |
| POST | `/v1/web/auth/telegram` | No | Verify Telegram WebApp auth |
| POST | `/v1/web/keys/create` | Yes | Create API key (tier-based) |
| GET | `/v1/web/keys/list` | Yes | List your keys |
| GET | `/v1/web/keys/{id}` | Yes | Key details |
| PATCH | `/v1/web/keys/{id}` | Owner | Edit key (scopes, rate, expiry) |
| DELETE | `/v1/web/keys/{id}` | Yes | Revoke key |
| POST | `/v1/web/keys/{id}` | Owner | Rotate key |
| GET | `/v1/web/stats` | Yes | Usage statistics |
| GET | `/v1/web/owner/keys` | Owner | List ALL keys |

### Music
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET/POST | `/v1/search` | Yes | Search music |
| GET/POST | `/v1/info` | Yes | Track/playlist info |
| GET/POST | `/v1/lyrics` | Yes | Get lyrics |
| POST | `/v1/lyrics/search` | Yes | Lyrics by title+artist |
| GET/POST | `/v1/metadata` | Yes | Spotify metadata |
| GET/POST | `/v1/download` | Yes | Download audio |
| POST | `/v1/download/queue` | Yes | Background download job |
| GET | `/v1/file/{folder}/{file}` | Yes | Serve file (auto-cleanup) |
| GET | `/v1/stream` | Yes | Direct stream URL |

### Anime
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/v1/anime/search` | Yes | Search anime |
| POST | `/v1/anime/info` | Yes | Anime details |
| POST | `/v1/anime/download` | Yes | Download anime |

### Manga
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/v1/manga/search` | Yes | Search manga |
| POST | `/v1/manga/info` | Yes | Manga details |
| POST | `/v1/manga/download` | Yes | Download manga chapters |

### M3U8 / HLS / DASH
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/v1/m3u8/parse` | Yes | Parse playlist |
| POST | `/v1/m3u8/download` | Yes | Download stream |
| POST | `/v1/m3u8/download/queue` | Yes | Background job |
| GET | `/v1/m3u8/download/status/{id}` | Yes | Job status |
| POST | `/v1/m3u8/download/cancel/{id}` | Yes | Cancel job |

### aria2c JSON-RPC
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/v1/aria2/add` | Yes | Add download |
| GET | `/v1/aria2/status/{gid}` | Yes | Download status |
| POST | `/v1/aria2/remove/{gid}` | Yes | Remove download |

### API Keys
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/v1/keys` | No | Create key (bootstrap) |
| GET | `/v1/keys` | Yes | List your keys |
| DELETE | `/v1/keys/{key}` | Yes | Revoke key |

## Telegram WebApp (TypeScript + CSS)

The WebApp at `/app` provides a Telegram-native dashboard for:

- **Sign in** with Telegram (WebApp initData verification)
- **Create API keys** with tier selection (free/pro/owner)
- **View usage stats** (requests, bandwidth today/month)
- **Manage keys** (revoke, rotate, view details)
- **Browse supported sources**

Built with TypeScript, CSS, and the Telegram WebApp SDK. Source in `webapp/src/`, compiled bundle in `webapp/app.js`.

### Environment Variables for WebApp

```bash
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
TELEGRAM_BOT_USERNAME=videl_api_bot
```

## Environment Variables

See `.env.example` for the full list. Key settings:

- `TELEGRAM_BOT_TOKEN` — Telegram bot token for WebApp auth
- `ADMIN_KEYS` — comma-separated master admin keys (owner access)
- `API_KEY_PREFIX` — key prefix (default: `videl_`)
- `QUOTA_DAILY_REQUESTS` / `QUOTA_MONTHLY_REQUESTS` — per-key quotas
- `QUOTA_DAILY_BYTES` / `QUOTA_MONTHLY_BYTES` — bandwidth quotas
- `ARIA2C_ENABLED=true` — use aria2c for multipart downloads
- `ARIA2C_RPC_ENABLED=true` — enable aria2c JSON-RPC endpoints
- `M3U8_ENABLED=true` — enable M3U8/HLS/DASH downloader
- `M3U8_MAX_THREADS=16` — segment download threads
- `SPOTDL_ENABLED=true` — enable spotDL Spotify integration
- `SPOTIFY_CLIENT_ID/SECRET` — Spotify API credentials
- `LYRICS_PROVIDERS=synced,genius,musixmatch,azlyrics`
- `METADATA_EMBED=true` — embed ID3 tags + album art
- `SPONSORBLOCK=true` — remove sponsored segments
- `SSRF_GUARD=true` — block private/internal hosts
- `CREDENTIAL_REDACTION=true` — mask secrets in logs

## External Tools (optional)

| Tool | Purpose | Install |
|------|---------|---------|
| aria2c | Multipart downloads + JSON-RPC | `apt install aria2` |
| ffmpeg | Audio conversion, M3U8 merge | `apt install ffmpeg` |
| spotdl | Spotify metadata + audio matching | `pip install spotdl` |

Enable aria2c RPC: `aria2c --enable-rpc --rpc-secret=SECRET --rpc-listen-all`

## Deployment

Run behind Nginx/Caddy/Traefik with TLS:

```ini
[Unit]
Description=Videl-Api Ultimate Media API
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

## Eldian Source

The `/eldian/` directory contains the full Eldian-Network/eldian-music-api source with all credits changed from "Eldian Network" to "Videl-Api". Run separately:

```bash
cd eldian && pip install -r requirements.txt && python -m uvicorn app.main:app
```

## License

MIT
