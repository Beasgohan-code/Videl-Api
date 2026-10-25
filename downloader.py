"""Multi-source media downloader powered by yt-dlp.

Handles info extraction, search, lyrics, and audio download across YouTube,
SoundCloud, Bandcamp, Spotify, Deezer, Apple Music, Vimeo, Dailymotion,
TikTok, Facebook, Instagram, X/Twitter and 1000+ other yt-dlp sites.
"""

from __future__ import annotations

import asyncio
import shutil
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import yt_dlp
from yt_dlp.utils import DownloadError

from config import settings, MUSIC_SOURCES, search_prefix_for

# Default formats to try when the user's format selector fails.
_AUDIO_FORMATS = [
    "bestaudio/best",
    "bestaudio[ext=m4a]/bestaudio/best",
    "bestaudio[ext=mp3]/bestaudio/best",
    "bestaudio[ext=opus]/bestaudio/best",
    "best",
]


def _build_ydl_opts(
    *,
    output_dir: Path,
    format_selector: str,
    cookies: Optional[str] = None,
    cookies_file: Optional[str] = None,
    proxy: Optional[str] = None,
    skip_download: bool = False,
    socket_timeout: Optional[int] = None,
    retries: Optional[int] = None,
    fragment_retries: Optional[int] = None,
    max_filesize_mb: Optional[int] = None,
    noplayer: bool = True,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    template = str(output_dir / "%(id)s.%(ext)s")

    opts: dict[str, Any] = {
        "format": format_selector,
        "outtmpl": template,
        "noplaylist": False,  # we handle playlists explicitly where needed
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": socket_timeout or settings.yt_dlp_socket_timeout,
        "retries": retries or settings.yt_dlp_retries,
        "fragment_retries": fragment_retries or settings.yt_dlp_fragment_retries,
        "continuedl": True,
        "nopart": True,
    }

    if skip_download:
        opts["skip_download"] = True

    if max_filesize_mb:
        opts["max_filesize"] = max_filesize_mb * 1024 * 1024

    # --- cookies -----------------------------------------------------------
    if cookies:
        opts["cookies"] = cookies
    if cookies_file:
        opts["cookiefile"] = cookies_file

    # --- proxy -------------------------------------------------------------
    if proxy:
        opts["proxy"] = proxy

    return opts


def _resolve_proxy(source_id: Optional[str]) -> Optional[str]:
    """Resolve proxy for a given source. Falls back to global proxy."""
    if settings.yt_dlp_proxy:
        return settings.yt_dlp_proxy
    # Per-source proxy file could be added here later.
    return None


def _resolve_cookies(source_id: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Resolve cookies (string or file) for a given source."""
    cookies = settings.yt_dlp_cookies
    cookies_file = settings.yt_dlp_cookies_file

    # Per-source cookie file override.
    if source_id and source_id in settings.yt_dlp_cookies_files:
        cookies_file = settings.yt_dlp_cookies_files[source_id]

    return cookies, cookies_file


def _pick_source(url: str, force: Optional[str]) -> Optional[str]:
    """Guess the source id from a URL, or return the forced source."""
    if force:
        return force
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return None
    for sid, info in MUSIC_SOURCES.items():
        for domain in info["domains"]:
            if host == domain or host.endswith("." + domain):
                return sid
    return None


def _extract_id(url: str, source: Optional[str]) -> str:
    """Return a stable id: the URL itself (yt-dlp works best with full URLs)."""
    return url


def _safe_info(info: Optional[dict]) -> dict:
    return info or {}


def _cleanup_file(path: Path) -> None:
    if path.exists():
        path.unlink(missing_ok=True)
    parent = path.parent
    if parent.exists() and not any(parent.iterdir()):
        shutil.rmtree(parent, ignore_errors=True)


def _cleanup_stale(base_dir: Path) -> None:
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


# ---------------------------------------------------------------------------
# Sync yt-dlp wrappers (run in executor so FastAPI event loop is not blocked)
# ---------------------------------------------------------------------------


def extract_info_sync(
    url: str,
    *,
    source: Optional[str] = None,
    skip_download: bool = False,
    format_selector: Optional[str] = None,
    process: bool = True,
) -> dict:
    """Extract info from a URL using yt-dlp. Returns the raw info dict."""
    resolved_source = _pick_source(url, source)
    cookies, cookies_file = _resolve_cookies(resolved_source)
    proxy = _resolve_proxy(resolved_source)
    fmt = format_selector or settings.yt_dlp_format

    # Build a temporary dir next to downloads for extraction-only work.
    tmp_dir = settings.download_dir / "_extract"
    opts = _build_ydl_opts(
        output_dir=tmp_dir,
        format_selector=fmt,
        cookies=cookies,
        cookies_file=cookies_file,
        proxy=proxy,
        skip_download=skip_download,
        noplayer=True,
    )

    last_error: Optional[Exception] = None
    for attempt in range(1, settings.yt_dlp_retries + 1):
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False, process=process)
            return _safe_info(info)
        except DownloadError as exc:
            last_error = exc
        except Exception as exc:  # noqa: BLE001 - yt-dlp failure surface
            last_error = exc
        if attempt < settings.yt_dlp_retries:
            time.sleep(0.8 * attempt)
    raise RuntimeError(f"yt-dlp extraction failed: {last_error}")


def download_audio_sync(
    url: str,
    *,
    source: Optional[str] = None,
    output_dir: Path,
    format_selector: Optional[str] = None,
) -> Path:
    """Download the best audio for a URL. Returns the downloaded file path."""
    resolved_source = _pick_source(url, source)
    cookies, cookies_file = _resolve_cookies(resolved_source)
    proxy = _resolve_proxy(resolved_source)
    fmt = format_selector or settings.yt_dlp_format

    opts = _build_ydl_opts(
        output_dir=output_dir,
        format_selector=fmt,
        cookies=cookies,
        cookies_file=cookies_file,
        proxy=proxy,
        max_filesize_mb=settings.download_max_filesize_mb or None,
    )

    last_error: Optional[Exception] = None
    downloaded: Optional[Path] = None
    for attempt in range(1, settings.yt_dlp_retries + 1):
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
            info = _safe_info(info)
            # Locate the produced file.
            video_id = info.get("id") or url
            for candidate in sorted(output_dir.glob(f"{video_id}.*")):
                if candidate.is_file():
                    downloaded = candidate
                    break
            if downloaded is None:
                # Fallback: pick the newest file in the dir.
                files = [p for p in output_dir.iterdir() if p.is_file()]
                if files:
                    downloaded = max(files, key=lambda p: p.stat().st_mtime)
            break
        except DownloadError as exc:
            last_error = exc
        except Exception as exc:  # noqa: BLE001
            last_error = exc
        if attempt < settings.yt_dlp_retries:
            time.sleep(0.8 * attempt)
    else:
        raise RuntimeError(f"yt-dlp download failed: {last_error}")

    if downloaded is None or not downloaded.exists():
        raise RuntimeError("Downloaded file was not created by yt-dlp")
    return downloaded


def search_sync(
    query: str,
    *,
    source: str = "youtube",
    limit: int = 20,
) -> list[dict]:
    """Search a source using yt-dlp's built-in search prefix where available."""
    prefix = search_prefix_for(source)
    if not prefix:
        # Fall back to a generic youtube search (still useful) — but be honest
        # that the source is not natively searchable.
        raise ValueError(f"Source '{source}' does not support native search")

    search_url = f"{prefix}{limit}:{query}"
    tmp_dir = settings.download_dir / "_extract"
    opts = _build_ydl_opts(
        output_dir=tmp_dir,
        format_selector=settings.yt_dlp_format,
        skip_download=True,
    )

    last_error: Optional[Exception] = None
    for attempt in range(1, settings.yt_dlp_retries + 1):
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(search_url, download=False, process=True)
            entries = _safe_info(info).get("entries") or []
            return [e for e in entries if e]
        except DownloadError as exc:
            last_error = exc
        except Exception as exc:  # noqa: BLE001
            last_error = exc
        if attempt < settings.yt_dlp_retries:
            time.sleep(0.8 * attempt)
    raise RuntimeError(f"yt-dlp search failed: {last_error}")


# ---------------------------------------------------------------------------
# Async helpers used by the API layer
# ---------------------------------------------------------------------------


async def extract_info(
    url: str,
    *,
    source: Optional[str] = None,
    skip_download: bool = False,
    format_selector: Optional[str] = None,
) -> dict:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: extract_info_sync(
            url,
            source=source,
            skip_download=skip_download,
            format_selector=format_selector,
        ),
    )


async def download_audio(
    url: str,
    *,
    source: Optional[str] = None,
    output_dir: Path,
    format_selector: Optional[str] = None,
) -> Path:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: download_audio_sync(
            url,
            source=source,
            output_dir=output_dir,
            format_selector=format_selector,
        ),
    )


async def search(
    query: str,
    *,
    source: str = "youtube",
    limit: int = 20,
) -> list[dict]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: search_sync(query, source=source, limit=limit),
    )


async def cleanup_stale_downloads() -> None:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, lambda: _cleanup_stale(settings.download_dir))
