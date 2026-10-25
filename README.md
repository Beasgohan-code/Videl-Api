# Videl-Api — Ultimate Multi-Source Media REST API

Powerful all-in-one media API for music bots, anime streaming, manga scraping, and more.

## Supported Sources

**Music:** YouTube, YouTube Music, SoundCloud, Bandcamp, Spotify, Apple Music, Deezer, Piped, Invidious

**Anime:** AnimePahe, AnimeFlix, Zoro/AniWatch, GogoAnime, KickassAnime, AnimeWorld, 9Anime, Putlocker

**Manga:** MangaDex, MangaKakalot, Manganelo, Webtoons, Manhwa

**Media:** M3U8/HLS, MPEG-DASH, YTS Movies, 1337x, The Pirate Bay

Plus 1000+ additional sites natively supported.

## Quick Start

```bash
git clone https://github.com/Beasgohan-code/Videl-Api.git
cd Videl-Api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
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
- Short-lived token for secure WebView access

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

### Telegram Bot (`@videl_api_bot`)

| Command | Description |
|---------|-------------|
| `/start` | Welcome & main menu |
| `/help` | All commands |
| `/search` | Search music & media |
| `/download` | Download a track |
| `/info` | Track/album info |
| `/lyrics` | Get lyrics |
| `/key` | Manage API keys |
| `/createkey` | Create a new API key |
| `/tier` | View subscription tier |
| `/buy` | Buy Pro with Telegram Stars |
| `/playlist` | Manage playlists |
| `/history` | Download history |
| `/settings` | User settings |
| `/notify` | Notification preferences |
| `/sources` | List supported sources |
| `/status` | System status |
| `/feedback` | Send feedback |
| `/language` | Change language |
| `/admin` | Admin panel (owner) |
| `/broadcast` | Broadcast (owner) |
| `/users` | User management (owner) |
| `/stats` | Bot statistics (owner) |

Features: rich inline keyboards, inline queries, callback queries, Telegram Stars payments, admin/owner access control.

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

### Download Manager (aria2c)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/v1/download/add` | Yes | Add download |
| GET | `/v1/download/status/{gid}` | Yes | Download status |
| POST | `/v1/download/remove/{gid}` | Yes | Remove download |

### API Keys
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/v1/keys` | No | Create key (bootstrap) |
| GET | `/v1/keys` | Yes | List your keys |
| DELETE | `/v1/keys/{key}` | Yes | Revoke key |

### Users
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/v1/users` | Admin | Create user |
| GET | `/v1/users` | Admin | List users |
| GET | `/v1/users/{id}` | Yes | Get user |
| PUT | `/v1/users/{id}` | Yes/Owner | Update user |
| DELETE | `/v1/users/{id}` | Admin | Delete user |

### Tiers
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/v1/tiers` | Yes | List tiers |
| POST | `/v1/users/{id}/tier` | Admin | Change user tier |

### Payments (Telegram Stars)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/v1/payments/invoice` | Yes | Create Stars invoice |
| POST | `/v1/payments/webhook` | Yes | Payment webhook |
| GET | `/v1/payments/history` | Yes | Payment history |

### Playlists
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/v1/playlists` | Yes | Create playlist |
| GET | `/v1/playlists` | Yes | List playlists |
| GET | `/v1/playlists/{id}` | Yes | Get playlist |
| PUT | `/v1/playlists/{id}` | Yes | Update playlist |
| DELETE | `/v1/playlists/{id}` | Yes | Delete playlist |
| POST | `/v1/playlists/{id}/items` | Yes | Add item |
| DELETE | `/v1/playlists/{id}/items/{item}` | Yes | Remove item |

### Webhooks
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/v1/webhooks` | Admin | Create webhook |
| GET | `/v1/webhooks` | Admin | List webhooks |
| DELETE | `/v1/webhooks/{id}` | Admin | Delete webhook |
| POST | `/v1/webhooks/{id}/trigger` | Admin | Trigger webhook |

### Notifications
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/v1/notifications` | Yes | Create notification |
| GET | `/v1/notifications` | Yes | List notifications |
| PUT | `/v1/notifications/{id}/read` | Yes | Mark read |

### Batch Operations
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/v1/batch` | Yes | Create batch job |
| GET | `/v1/batch/{id}` | Yes | Batch status |

### Files
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/v1/files` | Yes | List files |
| DELETE | `/v1/files/{folder}/{file}` | Yes | Delete file |

### System
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/v1/version` | Yes | Version info |
| GET | `/v1/maintenance` | Yes | Maintenance status |
| POST | `/v1/maintenance` | Admin | Toggle maintenance |
| GET | `/v1/stats/global` | Admin | Global stats |
| GET | `/v1/stats/usage` | Yes | Usage stats |
| GET | `/v1/stats/sources` | Yes | Source stats |
| GET | `/v1/logs` | Admin | View logs |
| DELETE | `/v1/logs` | Admin | Clear logs |
| POST | `/v1/cache/clear` | Admin | Clear cache |
| GET | `/v1/cache/stats` | Yes | Cache stats |

### Telegram Bot Webhook
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/v1/telegram/webhook` | No | Receive bot updates |
| POST | `/v1/telegram/set-webhook` | Admin | Set webhook URL |
| POST | `/v1/telegram/delete-webhook` | Admin | Delete webhook |
| GET | `/v1/telegram/bot-info` | Yes | Bot info |

## Telegram WebApp (TypeScript + CSS)

The WebApp at `/app` provides a Telegram-native dashboard for:

- Sign in with Telegram (WebApp initData verification)
- Create API keys with tier selection (free/pro/owner)
- View usage stats (requests, bandwidth today/month)
- Manage keys (revoke, rotate, view details)
- Browse supported sources

Built with TypeScript, CSS, and the Telegram WebApp SDK. Source in `webapp/src/`, compiled bundle in `webapp/app.js`.

## Environment Variables

See `.env.example` for the full list. Key settings:

- `TELEGRAM_BOT_TOKEN` — Telegram bot token for WebApp auth
- `ADMIN_KEYS` — comma-separated master admin keys (owner access)
- `API_KEY_PREFIX` — key prefix (default: `videl_`)
- `QUOTA_DAILY_REQUESTS` / `QUOTA_MONTHLY_REQUESTS` — per-key quotas
- `QUOTA_DAILY_BYTES` / `QUOTA_MONTHLY_BYTES` — bandwidth quotas
- `DOWNLOAD_MAX_THREADS` — segment download threads
- `SPOTIFY_CLIENT_ID/SECRET` — Spotify API credentials
- `LYRICS_PROVIDERS` — lyrics provider fallback order
- `METADATA_EMBED` — embed ID3 tags + album art
- `SSRF_GUARD` — block private/internal hosts
- `CREDENTIAL_REDACTION` — mask secrets in logs

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

## License

MIT
