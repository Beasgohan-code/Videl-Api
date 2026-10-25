"""Videl-Api configuration (env-driven, sane defaults)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

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
    # Server
    api_host: str = field(default_factory=lambda: _env("API_HOST", "0.0.0.0"))
    api_port: int = field(default_factory=lambda: _env_int("API_PORT", 8000))
    api_base_url: str = field(default_factory=lambda: _env("API_BASE_URL", "http://localhost:8000"))

    # Auth
    api_keys_enabled: bool = field(default_factory=lambda: _env_bool("API_KEYS", True))
    admin_keys: list[str] = field(default_factory=lambda: _env_csv("ADMIN_KEYS"))

    # MongoDB (optional)
    mongodb_uri: str = field(default_factory=lambda: _env("MONGODB_URI", "mongodb://localhost:27017"))
    mongodb_db: str = field(default_factory=lambda: _env("MONGODB_DB", "videl_music"))

    # Rate limiting
    rate_limit_enabled: bool = field(default_factory=lambda: _env_bool("RATE_LIMIT_ENABLED", True))
    rate_limit_default: int = field(default_factory=lambda: _env_int("RATE_LIMIT_DEFAULT", 60))

    # yt-dlp downloader
    yt_dlp_format: str = field(default_factory=lambda: _env("YT_DLP_FORMAT", "bestaudio/best"))
    yt_dlp_socket_timeout: int = field(default_factory=lambda: _env_int("YT_DLP_SOCKET_TIMEOUT", 20))
    yt_dlp_retries: int = field(default_factory=lambda: _env_int("YT_DLP_RETRIES", 3))
    yt_dlp_fragment_retries: int = field(default_factory=lambda: _env_int("YT_DLP_FRAGMENT_RETRIES", 3))
    download_cleanup_seconds: int = field(default_factory=lambda: _env_int("DOWNLOAD_CLEANUP_SECONDS", 900))
    download_max_filesize_mb: int = field(default_factory=lambda: _env_int("DOWNLOAD_MAX_FILESIZE_MB", 0))
    download_dir: Path = field(default_factory=lambda: Path(_env("DOWNLOAD_DIR", "downloads")))

    yt_dlp_proxy: str | None = field(default_factory=lambda: _env("YOUTUBE_PROXY", "") or None)
    yt_dlp_proxy_file: str | None = field(default_factory=lambda: _env("YOUTUBE_PROXY_FILE", "") or None)
    yt_dlp_cookies: str | None = field(default_factory=lambda: _env("YOUTUBE_COOKIES", "") or None)
    yt_dlp_cookies_file: str | None = field(default_factory=lambda: _env("YOUTUBE_COOKIES_FILE", "") or None)
    yt_dlp_cookies_files: dict = field(default_factory=lambda: _env_json("YOUTUBE_COOKIES_FILES", {}) or {})

    # CORS
    cors_origins: list[str] = field(default_factory=lambda: _env_csv("CORS_ORIGINS"))

    # Search defaults
    search_default_limit: int = field(default_factory=lambda: _env_int("SEARCH_DEFAULT_LIMIT", 20))
    search_max_limit: int = field(default_factory=lambda: _env_int("SEARCH_MAX_LIMIT", 100))


settings = Settings()


# --- Music source registry --------------------------------------------------
# Each source: id, name, domains, and the yt-dlp search prefix (if any).
# This is a curated list of the most useful music/video sources yt-dlp can
# handle natively. yt-dlp itself supports 1000+ sites; anything not listed
# here is still reachable via the generic extractor.

MUSIC_SOURCES: dict[str, dict] = {
    "youtube": {
        "name": "YouTube",
        "domains": ["youtube.com", "youtu.be", "music.youtube.com"],
        "search_prefix": "ytsearch",
        "supports_search": True,
        "supports_playlist": True,
        "description": "Videos, music, playlists, shorts.",
    },
    "soundcloud": {
        "name": "SoundCloud",
        "domains": ["soundcloud.com"],
        "search_prefix": "scsearch",
        "supports_search": True,
        "supports_playlist": True,
        "description": "Independent artists, tracks, DJ sets, playlists.",
    },
    "bandcamp": {
        "name": "Bandcamp",
        "domains": ["bandcamp.com"],
        "search_prefix": None,
        "supports_search": False,
        "supports_album": True,
        "description": "Direct-from-artist music, albums, merch.",
    },
    "spotify": {
        "name": "Spotify",
        "domains": ["open.spotify.com", "spotify.com"],
        "search_prefix": None,
        "supports_search": False,
        "supports_playlist": True,
        "description": "Tracks, albums, playlists (DRM-protected tracks may fail).",
    },
    "apple_music": {
        "name": "Apple Music",
        "domains": ["music.apple.com"],
        "search_prefix": None,
        "supports_search": False,
        "supports_playlist": True,
        "description": "Tracks, albums, playlists.",
    },
    "deezer": {
        "name": "Deezer",
        "domains": ["deezer.com"],
        "search_prefix": None,
        "supports_search": False,
        "supports_playlist": True,
        "description": "Tracks, albums, playlists.",
    },
    "vimeo": {
        "name": "Vimeo",
        "domains": ["vimeo.com"],
        "search_prefix": None,
        "supports_search": False,
        "supports_playlist": True,
        "description": "High-quality video and music uploads.",
    },
    "dailymotion": {
        "name": "Dailymotion",
        "domains": ["dailymotion.com"],
        "search_prefix": None,
        "supports_search": False,
        "supports_playlist": True,
        "description": "Video and music content.",
    },
    "tiktok": {
        "name": "TikTok",
        "domains": ["tiktok.com", "vt.tiktok.com"],
        "search_prefix": None,
        "supports_search": False,
        "supports_playlist": False,
        "description": "Short-form videos with audio.",
    },
    "facebook": {
        "name": "Facebook",
        "domains": ["facebook.com", "fb.watch"],
        "search_prefix": None,
        "supports_search": False,
        "supports_playlist": False,
        "description": "Videos and reels.",
    },
    "instagram": {
        "name": "Instagram",
        "domains": ["instagram.com"],
        "search_prefix": None,
        "supports_search": False,
        "supports_playlist": False,
        "description": "Reels, stories, videos.",
    },
    "twitter": {
        "name": "X / Twitter",
        "domains": ["twitter.com", "x.com"],
        "search_prefix": None,
        "supports_search": False,
        "supports_playlist": False,
        "description": "Videos and audio posts.",
    },
}

# Any source not in MUSIC_SOURCES but supported by yt-dlp's generic extractor.
GENERIC_SOURCE_ID = "generic"


def list_sources() -> list[dict]:
    out = []
    for sid, info in MUSIC_SOURCES.items():
        out.append(
            {
                "id": sid,
                "name": info["name"],
                "domains": info["domains"],
                "supports_search": info.get("supports_search", False),
                "supports_playlist": info.get("supports_playlist", False),
                "supports_album": info.get("supports_album", False),
                "description": info.get("description", ""),
            }
        )
    return out


def is_searchable(source_id: str) -> bool:
    info = MUSIC_SOURCES.get(source_id)
    if not info:
        return False
    return bool(info.get("supports_search", False))


def search_prefix_for(source_id: str) -> str | None:
    info = MUSIC_SOURCES.get(source_id)
    if not info:
        return None
    return info.get("search_prefix")
