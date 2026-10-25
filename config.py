"""Videl-Api configuration (env-driven, sane defaults)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from shutil import which

APP_DIR = Path(__file__).resolve().parent


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _env_csv(name: str) -> list[str]:
    raw = os.getenv(name, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


def _env_json(name: str, default=None):
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


@dataclass
class Settings:
    # ---- Server ----
    api_host: str = field(default_factory=lambda: _env("API_HOST", "0.0.0.0"))
    api_port: int = field(default_factory=lambda: _env_int("API_PORT", 8000))
    api_base_url: str = field(default_factory=lambda: _env("API_BASE_URL", "http://localhost:8000"))
    api_version: str = field(default_factory=lambda: _env("API_VERSION", "2.5.0"))

    # ---- Auth ----
    api_keys_enabled: bool = field(default_factory=lambda: _env_bool("API_KEYS", True))
    admin_keys: list[str] = field(default_factory=lambda: _env_csv("ADMIN_KEYS"))
    api_key_prefix: str = field(default_factory=lambda: _env("API_KEY_PREFIX", "videl_"))
    api_key_hash_rounds: int = field(default_factory=lambda: _env_int("API_KEY_HASH_ROUNDS", 1))
    bearer_token_ttl_minutes: int = field(default_factory=lambda: _env_int("BEARER_TOKEN_TTL_MINUTES", 15))
    owner_token_ttl_days: int = field(default_factory=lambda: _env_int("OWNER_TOKEN_TTL_DAYS", 30))

    # ---- Telegram Bot ----
    telegram_bot_token: str | None = field(default_factory=lambda: _env("TELEGRAM_BOT_TOKEN", "") or None)
    telegram_bot_username: str = field(default_factory=lambda: _env("TELEGRAM_BOT_USERNAME", "videl_api_bot"))

    # ---- Quotas & rate limiting ----
    rate_limit_enabled: bool = field(default_factory=lambda: _env_bool("RATE_LIMIT_ENABLED", True))
    rate_limit_default: int = field(default_factory=lambda: _env_int("RATE_LIMIT_DEFAULT", 60))
    quota_daily_requests: int = field(default_factory=lambda: _env_int("QUOTA_DAILY_REQUESTS", 1000))
    quota_monthly_requests: int = field(default_factory=lambda: _env_int("QUOTA_MONTHLY_REQUESTS", 30000))
    quota_daily_bytes: int = field(default_factory=lambda: _env_int("QUOTA_DAILY_BYTES", 0))
    quota_monthly_bytes: int = field(default_factory=lambda: _env_int("QUOTA_MONTHLY_BYTES", 0))

    # ---- MongoDB (optional) ----
    mongodb_uri: str = field(default_factory=lambda: _env("MONGODB_URI", "mongodb://localhost:27017"))
    mongodb_db: str = field(default_factory=lambda: _env("MONGODB_DB", "videl_music"))

    # ---- Downloader ----
    download_format: str = field(default_factory=lambda: _env("DOWNLOAD_FORMAT", "bestaudio/best"))
    download_socket_timeout: int = field(default_factory=lambda: _env_int("DOWNLOAD_SOCKET_TIMEOUT", 20))
    download_retries: int = field(default_factory=lambda: _env_int("DOWNLOAD_RETRIES", 3))
    download_fragment_retries: int = field(default_factory=lambda: _env_int("DOWNLOAD_FRAGMENT_RETRIES", 3))
    download_cleanup_seconds: int = field(default_factory=lambda: _env_int("DOWNLOAD_CLEANUP_SECONDS", 900))
    download_max_filesize_mb: int = field(default_factory=lambda: _env_int("DOWNLOAD_MAX_FILESIZE_MB", 0))
    download_dir: Path = field(default_factory=lambda: Path(_env("DOWNLOAD_DIR", "downloads")))

    download_proxy: str | None = field(default_factory=lambda: _env("DOWNLOAD_PROXY", "") or None)
    download_proxy_file: str | None = field(default_factory=lambda: _env("DOWNLOAD_PROXY_FILE", "") or None)
    download_cookies: str | None = field(default_factory=lambda: _env("DOWNLOAD_COOKIES", "") or None)
    download_cookies_file: str | None = field(default_factory=lambda: _env("DOWNLOAD_COOKIES_FILE", "") or None)
    download_cookies_files: dict = field(default_factory=lambda: _env_json("DOWNLOAD_COOKIES_FILES", {}) or {})

    # ---- External downloader ----
    downloader_path: str = field(default_factory=lambda: _env("ARIA2C_PATH", which("aria2c") or ""))
    downloader_args: str = field(default_factory=lambda: _env("ARIA2C_ARGS", "-x 16 -s 16 -k 1M"))
    downloader_enabled: bool = field(default_factory=lambda: _env_bool("ARIA2C_ENABLED", True))

    # ---- Downloader JSON-RPC ----
    downloader_rpc_url: str = field(default_factory=lambda: _env("ARIA2C_RPC_URL", "http://localhost:6800/jsonrpc"))
    downloader_rpc_secret: str = field(default_factory=lambda: _env("ARIA2C_RPC_SECRET", ""))
    downloader_rpc_enabled: bool = field(default_factory=lambda: _env_bool("ARIA2C_RPC_ENABLED", False))

    # ---- HLS / DASH downloader ----
    hls_enabled: bool = field(default_factory=lambda: _env_bool("HLS_ENABLED", True))
    hls_max_threads: int = field(default_factory=lambda: _env_int("HLS_MAX_THREADS", 16))
    hls_merge_method: str = field(default_factory=lambda: _env("HLS_MERGE_METHOD", "binary"))
    hls_decrypt: bool = field(default_factory=lambda: _env_bool("HLS_DECRYPT", True))
    hls_default_headers: dict = field(default_factory=lambda: _env_json("HLS_DEFAULT_HEADERS", {}))
    hls_timeout: int = field(default_factory=lambda: _env_int("HLS_TIMEOUT", 30))

    # ---- Spotify ----
    spotify_enabled: bool = field(default_factory=lambda: _env_bool("SPOTIFY_ENABLED", True))
    spotify_path: str = field(default_factory=lambda: _env("SPOTIFY_PATH", "spotify"))
    spotify_client_id: str | None = field(default_factory=lambda: _env("SPOTIFY_CLIENT_ID", "") or None)
    spotify_client_secret: str | None = field(default_factory=lambda: _env("SPOTIFY_CLIENT_SECRET", "") or None)

    # ---- Metadata & lyrics ----
    metadata_embed: bool = field(default_factory=lambda: _env_bool("METADATA_EMBED", True))
    metadata_album_art: bool = field(default_factory=lambda: _env_bool("METADATA_ALBUM_ART", True))
    # ---- FFmpeg ----
    ffmpeg_path: str = field(default_factory=lambda: _env("FFMPEG_PATH", which("ffmpeg") or ""))

    # ---- Metadata & lyrics ----
    lyrics_providers: list[str] = field(default_factory=lambda: _env_csv("LYRICS_PROVIDERS"))
    lyrics_default_provider: str = field(default_factory=lambda: _env("LYRICS_DEFAULT_PROVIDER", "synced"))
    sponsorblock: bool = field(default_factory=lambda: _env_bool("SPONSORBLOCK", True))

    # ---- Download queue / concurrency ----
    download_max_concurrent: int = field(default_factory=lambda: _env_int("DOWNLOAD_MAX_CONCURRENT", 3))
    download_chunk_connections: int = field(default_factory=lambda: _env_int("DOWNLOAD_CHUNK_CONNECTIONS", 16))

    # ---- Security ----
    ssrf_guard: bool = field(default_factory=lambda: _env_bool("SSRF_GUARD", True))
    ssrf_allow_private: bool = field(default_factory=lambda: _env_bool("SSRF_ALLOW_PRIVATE", False))
    credential_redaction: bool = field(default_factory=lambda: _env_bool("CREDENTIAL_REDACTION", True))

    # ---- Source health / probing ----
    source_health_enabled: bool = field(default_factory=lambda: _env_bool("SOURCE_HEALTH_ENABLED", True))
    source_probe_timeout: int = field(default_factory=lambda: _env_int("SOURCE_PROBE_TIMEOUT", 10))

    # ---- CORS ----
    cors_origins: list[str] = field(default_factory=lambda: _env_csv("CORS_ORIGINS"))

    # ---- Search defaults ----
    search_default_limit: int = field(default_factory=lambda: _env_int("SEARCH_DEFAULT_LIMIT", 20))
    search_max_limit: int = field(default_factory=lambda: _env_int("SEARCH_MAX_LIMIT", 100))

    # ---- Telegram Bot ----
    telegram_bot_token: str | None = field(default_factory=lambda: _env("TELEGRAM_BOT_TOKEN", "") or None)
    telegram_bot_username: str = field(default_factory=lambda: _env("TELEGRAM_BOT_USERNAME", "videl_api_bot"))
    telegram_bot_webhook_url: str | None = field(default_factory=lambda: _env("TELEGRAM_BOT_WEBHOOK_URL", "") or None)
    telegram_bot_polling: bool = field(default_factory=lambda: _env_bool("TELEGRAM_BOT_POLLING", False))
    telegram_bot_admins: list[int] = field(default_factory=lambda: _env_csv("TELEGRAM_BOT_ADMINS") and [int(x) for x in _env_csv("TELEGRAM_BOT_ADMINS")] or [])
    telegram_bot_owner_id: int | None = field(default_factory=lambda: _env_int("TELEGRAM_BOT_OWNER_ID", 0) or None)

    # ---- Telegram Stars / Payments ----
    telegram_stars_enabled: bool = field(default_factory=lambda: _env_bool("TELEGRAM_STARS_ENABLED", True))
    telegram_stars_pro_price: int = field(default_factory=lambda: _env_int("TELEGRAM_STARS_PRO_PRICE", 100))
    telegram_stars_currency: str = field(default_factory=lambda: _env("TELEGRAM_STARS_CURRENCY", "XTR"))

    # ---- User Management ----
    user_registration_enabled: bool = field(default_factory=lambda: _env_bool("USER_REGISTRATION_ENABLED", True))
    user_default_tier: str = field(default_factory=lambda: _env("USER_DEFAULT_TIER", "free"))
    user_max_keys: int = field(default_factory=lambda: _env_int("USER_MAX_KEYS", 5))
    user_max_playlists: int = field(default_factory=lambda: _env_int("USER_MAX_PLAYLISTS", 10))
    user_max_downloads_per_day: int = field(default_factory=lambda: _env_int("USER_MAX_DOWNLOADS_PER_DAY", 100))

    # ---- Webhooks ----
    webhook_enabled: bool = field(default_factory=lambda: _env_bool("WEBHOOK_ENABLED", False))
    webhook_max_retries: int = field(default_factory=lambda: _env_int("WEBHOOK_MAX_RETRIES", 3))
    webhook_timeout_seconds: int = field(default_factory=lambda: _env_int("WEBHOOK_TIMEOUT_SECONDS", 10))
    webhook_secret_token: str | None = field(default_factory=lambda: _env("WEBHOOK_SECRET_TOKEN", "") or None)

    # ---- Notifications ----
    notification_enabled: bool = field(default_factory=lambda: _env_bool("NOTIFICATION_ENABLED", True))
    notification_max_per_user: int = field(default_factory=lambda: _env_int("NOTIFICATION_MAX_PER_USER", 100))

    # ---- Playlists ----
    playlist_max_items: int = field(default_factory=lambda: _env_int("PLAYLIST_MAX_ITEMS", 200))
    playlist_allow_public: bool = field(default_factory=lambda: _env_bool("PLAYLIST_ALLOW_PUBLIC", True))

    # ---- Batch Operations ----
    batch_max_items: int = field(default_factory=lambda: _env_int("BATCH_MAX_ITEMS", 50))
    batch_max_concurrent: int = field(default_factory=lambda: _env_int("BATCH_MAX_CONCURRENT", 5))

    # ---- Analytics ----
    analytics_enabled: bool = field(default_factory=lambda: _env_bool("ANALYTICS_ENABLED", True))
    analytics_retention_days: int = field(default_factory=lambda: _env_int("ANALYTICS_RETENTION_DAYS", 90))

    # ---- Maintenance ----
    maintenance_mode: bool = field(default_factory=lambda: _env_bool("MAINTENANCE_MODE", False))
    maintenance_message: str = field(default_factory=lambda: _env("MAINTENANCE_MESSAGE", "System under maintenance. Please try again later."))


settings = Settings()


# --- Music source registry --------------------------------------------------
# Each source: id, name, domains, and capabilities.

MUSIC_SOURCES: dict[str, dict] = {
    "youtube": {
        "name": "YouTube",
        "domains": ["youtube.com", "youtu.be", "music.youtube.com"],
        "search_prefix": "ytsearch",
        "supports_search": True,
        "supports_playlist": True,
        "description": "Videos, music, playlists, shorts.",
        "direct_audio": False,
    },
    "youtube_music": {
        "name": "YouTube Music",
        "domains": ["music.youtube.com"],
        "search_prefix": "ytmsearch",
        "supports_search": True,
        "supports_playlist": True,
        "description": "YouTube Music tracks, albums, playlists.",
        "direct_audio": False,
    },
    "soundcloud": {
        "name": "SoundCloud",
        "domains": ["soundcloud.com"],
        "search_prefix": "scsearch",
        "supports_search": True,
        "supports_playlist": True,
        "description": "Independent artists, tracks, DJ sets, playlists.",
        "direct_audio": False,
    },
    "bandcamp": {
        "name": "Bandcamp",
        "domains": ["bandcamp.com"],
        "search_prefix": None,
        "supports_search": False,
        "supports_album": True,
        "description": "Direct-from-artist music, albums, merch.",
        "direct_audio": True,
    },
    "spotify": {
        "name": "Spotify",
        "domains": ["open.spotify.com", "spotify.com"],
        "search_prefix": None,
        "supports_search": False,
        "supports_playlist": True,
        "description": "Tracks, albums, playlists.",
        "direct_audio": False,
    },
    "apple_music": {
        "name": "Apple Music",
        "domains": ["music.apple.com"],
        "search_prefix": None,
        "supports_search": False,
        "supports_playlist": True,
        "description": "Tracks, albums, playlists.",
        "direct_audio": False,
    },
    "deezer": {
        "name": "Deezer",
        "domains": ["deezer.com"],
        "search_prefix": None,
        "supports_search": False,
        "supports_playlist": True,
        "description": "Tracks, albums, playlists.",
        "direct_audio": False,
    },
    "audius": {
        "name": "Audius",
        "domains": ["audius.co", "audius.fm"],
        "search_prefix": None,
        "supports_search": False,
        "supports_playlist": False,
        "description": "Direct audio streaming.",
        "direct_audio": True,
    },
    "jiosaavn": {
        "name": "JioSaavn",
        "domains": ["jiosaavn.com"],
        "search_prefix": None,
        "supports_search": False,
        "supports_playlist": False,
        "description": "Direct audio streaming.",
        "direct_audio": True,
    },
    "vimeo": {
        "name": "Vimeo",
        "domains": ["vimeo.com"],
        "search_prefix": None,
        "supports_search": False,
        "supports_playlist": True,
        "description": "High-quality video and music uploads.",
        "direct_audio": False,
    },
    "dailymotion": {
        "name": "Dailymotion",
        "domains": ["dailymotion.com"],
        "search_prefix": None,
        "supports_search": False,
        "supports_playlist": True,
        "description": "Video and music content.",
        "direct_audio": False,
    },
    "tiktok": {
        "name": "TikTok",
        "domains": ["tiktok.com", "vt.tiktok.com"],
        "search_prefix": None,
        "supports_search": False,
        "supports_playlist": False,
        "description": "Short-form videos with audio.",
        "direct_audio": False,
    },
    "facebook": {
        "name": "Facebook",
        "domains": ["facebook.com", "fb.watch"],
        "search_prefix": None,
        "supports_search": False,
        "supports_playlist": False,
        "description": "Videos and reels.",
        "direct_audio": False,
    },
    "instagram": {
        "name": "Instagram",
        "domains": ["instagram.com"],
        "search_prefix": None,
        "supports_search": False,
        "supports_playlist": False,
        "description": "Reels, stories, videos.",
        "direct_audio": False,
    },
    "twitter": {
        "name": "X / Twitter",
        "domains": ["twitter.com", "x.com"],
        "search_prefix": None,
        "supports_search": False,
        "supports_playlist": False,
        "description": "Videos and audio posts.",
        "direct_audio": False,
    },
    "piped": {
        "name": "Piped",
        "domains": ["piped.video", "piped.kavin.rocks"],
        "search_prefix": None,
        "supports_search": False,
        "supports_playlist": False,
        "description": "Privacy-focused YouTube frontend.",
        "direct_audio": False,
    },
    "invidious": {
        "name": "Invidious",
        "domains": ["invidious.io", "invidious.nerdvpn.de"],
        "search_prefix": None,
        "supports_search": False,
        "supports_playlist": False,
        "description": "Alternative YouTube frontend.",
        "direct_audio": False,
    },
}

# --- Anime source registry --------------------------------------------------

ANIME_SOURCES: dict[str, dict] = {
    "animepahe": {
        "name": "AnimePahe",
        "base_url": "https://animepahe.com",
        "supports_search": True,
        "supports_stream": True,
        "supports_download": True,
        "description": "Anime streaming with multiple servers.",
    },
    "animeflix": {
        "name": "AnimeFlix",
        "base_url": "https://animeflix.cc",
        "supports_search": True,
        "supports_stream": True,
        "supports_download": True,
        "description": "HD anime streaming.",
    },
    "zoro": {
        "name": "Zoro / AniWatch",
        "base_url": "https://zoro.to",
        "supports_search": True,
        "supports_stream": True,
        "supports_download": False,
        "description": "Popular anime streaming site.",
    },
    "gogoanime": {
        "name": "GogoAnime",
        "base_url": "https://gogoanime.ai",
        "supports_search": True,
        "supports_stream": True,
        "supports_download": True,
        "description": "Classic anime streaming.",
    },
    "kickassanime": {
        "name": "KickassAnime",
        "base_url": "https://kickassanime.online",
        "supports_search": True,
        "supports_stream": True,
        "supports_download": True,
        "description": "Anime with multiple quality options.",
    },
    "animeworld": {
        "name": "AnimeWorld",
        "base_url": "https://animeworld.tv",
        "supports_search": True,
        "supports_stream": True,
        "supports_download": False,
        "description": "International anime.",
    },
    "nineanime": {
        "name": "9Anime",
        "base_url": "https://9anime.to",
        "supports_search": True,
        "supports_stream": True,
        "supports_download": False,
        "description": "High-quality anime streams.",
    },
    "putlocker": {
        "name": "Putlocker Anime",
        "base_url": "https://putlocker.gg",
        "supports_search": True,
        "supports_stream": True,
        "supports_download": False,
        "description": "Anime movies and series.",
    },
}

# --- Manga source registry --------------------------------------------------

MANGA_SOURCES: dict[str, dict] = {
    "mangadex": {
        "name": "MangaDex",
        "api_url": "https://api.mangadex.org",
        "supports_search": True,
        "supports_chapters": True,
        "supports_download": True,
        "description": "Large manga database with API.",
    },
    "mangakakalot": {
        "name": "MangaKakalot",
        "base_url": "https://mangakakalot.com",
        "supports_search": True,
        "supports_chapters": True,
        "supports_download": True,
        "description": "Popular manga reader.",
    },
    "manganelo": {
        "name": "Manganelo",
        "base_url": "https://manganelo.com",
        "supports_search": True,
        "supports_chapters": True,
        "supports_download": True,
        "description": "Manga chapters and updates.",
    },
    "webtoons": {
        "name": "Webtoons",
        "base_url": "https://www.webtoons.com",
        "supports_search": True,
        "supports_chapters": True,
        "supports_download": False,
        "description": "Digital comics and webtoons.",
    },
    "manhwa": {
        "name": "Manhwa",
        "base_url": "",
        "supports_search": True,
        "supports_chapters": True,
        "supports_download": True,
        "description": "Korean manhwa comics.",
    },
}

# --- Media source registry --------------------------------------------------

MEDIA_SOURCES: dict[str, dict] = {
    "m3u8": {
        "name": "M3U8 / HLS",
        "domains": [".m3u8", ".m3u8?"],
        "supports_search": False,
        "supports_playlist": True,
        "description": "HLS streaming playlists.",
    },
    "dash": {
        "name": "MPEG-DASH",
        "domains": [".mpd"],
        "supports_search": False,
        "supports_playlist": True,
        "description": "DASH streaming manifests.",
    },
    "yts": {
        "name": "YTS Movies",
        "api_url": "https://yts.mx/api/v2",
        "supports_search": True,
        "supports_download": True,
        "description": "Movie torrents and streaming.",
    },
    "1337x": {
        "name": "1337x",
        "base_url": "https://1337x.to",
        "supports_search": True,
        "supports_download": True,
        "description": "Torrent indexer.",
    },
    "thepiratebay": {
        "name": "The Pirate Bay",
        "base_url": "https://thepiratebay.org",
        "supports_search": True,
        "supports_download": True,
        "description": "Torrent indexer.",
    },
}

# --- Unified source registry ------------------------------------------------

ALL_SOURCES: dict[str, dict] = {}
for _sid, _info in MUSIC_SOURCES.items():
    ALL_SOURCES[f"music:{_sid}"] = {"type": "music", **_info}
for _sid, _info in ANIME_SOURCES.items():
    ALL_SOURCES[f"anime:{_sid}"] = {"type": "anime", **_info}
for _sid, _info in MANGA_SOURCES.items():
    ALL_SOURCES[f"manga:{_sid}"] = {"type": "manga", **_info}
for _sid, _info in MEDIA_SOURCES.items():
    ALL_SOURCES[f"media:{_sid}"] = {"type": "media", **_info}


def list_all_sources() -> list[dict]:
    out = []
    for sid, info in ALL_SOURCES.items():
        out.append({
            "id": sid,
            "type": info["type"],
            "name": info["name"],
            "supports_search": info.get("supports_search", False),
            "supports_stream": info.get("supports_stream", False),
            "supports_download": info.get("supports_download", False),
            "supports_chapters": info.get("supports_chapters", False),
            "description": info.get("description", ""),
        })
    return out


def list_sources() -> list[dict]:
    """Return music sources only (for backward compatibility)."""
    out = []
    for sid, info in MUSIC_SOURCES.items():
        out.append({
            "id": sid,
            "type": "music",
            "name": info["name"],
            "supports_search": info.get("supports_search", False),
            "supports_stream": info.get("supports_stream", False),
            "supports_download": info.get("supports_download", False),
            "supports_chapters": info.get("supports_chapters", False),
            "description": info.get("description", ""),
        })
    return out


# --- Branding ----------------------------------------------------------------

API_BRAND = "Videl-Api"
API_BRAND_URL = "https://github.com/Beasgohan-code/Videl-Api"
API_BRAND_DESC = "Powerful multi-source media REST API for music bots and more"
