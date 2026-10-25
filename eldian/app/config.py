# MIT License - Copyright (c) 2026 Videl Network

from dataclasses import dataclass
import os
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Settings:
    mongodb_uri: str = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    mongodb_db: str = os.getenv("MONGODB_DB", "videl_music")
    api_host: str = os.getenv("API_HOST", "0.0.0.0")
    api_port: int = int(os.getenv("API_PORT", "8000"))
    api_base_url: str = os.getenv("API_BASE_URL", "http://localhost:8000")
    yt_dlp_format: str = os.getenv("YT_DLP_FORMAT", "bestaudio/best")
    yt_dlp_socket_timeout: int = int(os.getenv("YT_DLP_SOCKET_TIMEOUT", "20"))
    yt_dlp_retries: int = int(os.getenv("YT_DLP_RETRIES", "3"))
    download_cleanup_seconds: int = int(os.getenv("DOWNLOAD_CLEANUP_SECONDS", "900"))
    yt_dlp_proxy: str | None = os.getenv("YOUTUBE_PROXY") or os.getenv("YT_DLP_PROXY")
    yt_dlp_proxy_file: str | None = os.getenv("YOUTUBE_PROXY_FILE") or str(APP_DIR / "proxies.txt")
    yt_dlp_cookies: str | None = os.getenv("YOUTUBE_COOKIES") or os.getenv("YT_DLP_COOKIES")
    yt_dlp_cookies_file: str | None = os.getenv("YOUTUBE_COOKIES_FILE") or os.getenv("YT_DLP_COOKIES_FILE") or str(APP_DIR / "cookies_and_proxies.example")
    owner_id: int = int(os.getenv("OWNER_ID", "0"))
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")


settings = Settings()
