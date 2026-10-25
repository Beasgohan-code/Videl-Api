# MIT License - Copyright (c) 2026 Videl Network

import shutil
import time
from pathlib import Path

from urllib.parse import urlparse

from fastapi import HTTPException, status
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from .config import settings


def _validate_proxy(proxy: str) -> str:
    parsed = urlparse(proxy)
    if not parsed.scheme or not parsed.netloc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid proxy URL")
    if parsed.scheme not in {"http", "https", "socks4", "socks5"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported proxy scheme")
    return proxy


def _validate_cookies(cookies: str | None, cookies_file: str | None) -> None:
    if cookies and cookies_file:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provide either cookies or a cookies file, not both")

    if cookies is not None and not cookies.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cookies string cannot be empty")

    if cookies_file is not None:
        cookie_path = Path(cookies_file)
        if not cookie_path.exists():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cookies file does not exist")


def _load_proxy_from_file(proxy_file: str | None) -> str | None:
    if not proxy_file:
        return None

    proxy_path = Path(proxy_file)
    if not proxy_path.exists():
        return None

    for line in proxy_path.read_text(encoding="utf-8").splitlines():
        cleaned = line.strip()
        if not cleaned or cleaned.startswith("#"):
            continue
        return cleaned

    return None


def download_audio(video_id: str, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    url = f"https://www.youtube.com/watch?v={video_id}"
    download_template = str(output_dir / f"{video_id}.%(ext)s")

    options = {
        "format": settings.yt_dlp_format,
        "outtmpl": download_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": settings.yt_dlp_socket_timeout,
        "retries": settings.yt_dlp_retries,
        "fragment_retries": settings.yt_dlp_retries,
        "continuedl": True,
    }

    _validate_cookies(settings.yt_dlp_cookies, settings.yt_dlp_cookies_file)

    proxy_value = settings.yt_dlp_proxy or _load_proxy_from_file(settings.yt_dlp_proxy_file)
    if proxy_value:
        options["proxy"] = _validate_proxy(proxy_value)

    if settings.yt_dlp_cookies:
        options["cookies"] = settings.yt_dlp_cookies

    if settings.yt_dlp_cookies_file:
        options["cookiesfrombrowser"] = None
        options["cookiefile"] = settings.yt_dlp_cookies_file

    last_error: Exception | None = None
    for attempt in range(1, settings.yt_dlp_retries + 1):
        try:
            with YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=True)
            break
        except DownloadError as exc:
            last_error = exc
        except Exception as exc:  # pragma: no cover - yt-dlp failure surface
            last_error = exc

        if attempt < settings.yt_dlp_retries:
            time.sleep(1)
    else:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Unable to download track after retries: {last_error}",
        ) from last_error

    if info is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Track not found")

    for candidate in sorted(output_dir.glob(f"{video_id}.*")):
        if candidate.is_file():
            return candidate

    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Downloaded file was not created")


def cleanup_download(path: Path) -> None:
    if path.exists():
        path.unlink(missing_ok=True)
    parent = path.parent
    if parent.exists() and not any(parent.iterdir()):
        shutil.rmtree(parent, ignore_errors=True)


def cleanup_stale_downloads(base_dir: Path) -> None:
    if not base_dir.exists():
        return

    cutoff = time.time() - settings.download_cleanup_seconds
    for candidate in base_dir.iterdir():
        if not candidate.is_dir():
            continue
        try:
            if candidate.stat().st_mtime < cutoff:
                shutil.rmtree(candidate, ignore_errors=True)
        except FileNotFoundError:
            continue
