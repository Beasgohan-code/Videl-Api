"""Multi-source media downloader for Videl-Api.

Features:
- yt-dlp info extraction & download across 1000+ sites
- External downloader support for multipart segmented downloads
- Subprocess integration for Spotify metadata + audio matching
- Lyrics extraction (synced, genius, musixmatch, azlyrics)
- Metadata embedding (ID3, album art, ISRC, etc.) via mutagen
- SponsorBlock chapter removal
- Download queue with pause/resume support
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yt_dlp
from yt_dlp.utils import DownloadError

from config import settings

# ---------------------------------------------------------------------------
# Download job state (in-memory queue; persists only for the process lifetime)
# ---------------------------------------------------------------------------

class DownloadJob:
    __slots__ = ("job_id", "url", "source", "status", "progress", "file_path",
                 "error", "created_at", "updated_at", "cancelled")

    def __init__(self, job_id: str, url: str, source: Optional[str]):
        self.job_id = job_id
        self.url = url
        self.source = source
        self.status = "queued"  # queued | downloading | completed | failed | cancelled | paused
        self.progress = 0.0
        self.file_path: Optional[str] = None
        self.error: Optional[str] = None
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.updated_at = self.created_at
        self.cancelled = False

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "url": self.url,
            "source": self.source,
            "status": self.status,
            "progress": round(self.progress, 2),
            "file_path": self.file_path,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


# Global job store + concurrency control
JOBS: dict[str, DownloadJob] = {}
JOB_QUEUE: list[str] = []
_SEMAPHORE: Optional[asyncio.Semaphore] = None
_QUEUE_LOCK = asyncio.Lock()


def _get_semaphore() -> asyncio.Semaphore:
    global _SEMAPHORE
    if _SEMAPHORE is None:
        _SEMAPHORE = asyncio.Semaphore(settings.download_max_concurrent)
    return _SEMAPHORE


# ---------------------------------------------------------------------------
# External tool detection
# ---------------------------------------------------------------------------

def _has_aria2c() -> bool:
    return bool(settings.aria2c_path and Path(settings.aria2c_path).exists())


def _has_ffmpeg() -> bool:
    return bool(settings.ffmpeg_path and Path(settings.ffmpeg_path).exists()) or shutil.which("ffmpeg") is not None


def _has_spotdl() -> bool:
    try:
        subprocess.run(
            [settings.spotdl_path, "--version"],
            capture_output=True, check=False, timeout=5,
        )
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# yt-dlp options builder
# ---------------------------------------------------------------------------

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
    use_aria2c: bool = False,
    sponsorblock: bool = True,
    noplayer: bool = True,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    template = str(output_dir / "%(id)s.%(ext)s")

    opts: dict[str, Any] = {
        "format": format_selector,
        "outtmpl": template,
        "noplaylist": False,
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

    # --- cookies ---
    if cookies:
        opts["cookies"] = cookies
    if cookies_file:
        opts["cookiefile"] = cookies_file

    # --- proxy ---
    if proxy:
        opts["proxy"] = proxy

    # --- External downloader (multipart, faster) ---
    if use_aria2c and _has_aria2c():
        opts["external_downloader"] = "aria2c"
        opts["external_downloader_args"] = settings.aria2c_args.split()

    # --- ffmpeg path ---
    if _has_ffmpeg():
        opts["ffmpeg_location"] = settings.ffmpeg_path or shutil.which("ffmpeg")

    # --- SponsorBlock ---
    if sponsorblock and settings.sponsorblock:
        opts["sponsorblock_mark"] = ["all"]
        opts["sponsorblock_remove"] = ["all"]

    return opts


def _resolve_proxy(source_id: Optional[str]) -> Optional[str]:
    if settings.yt_dlp_proxy:
        return settings.yt_dlp_proxy
    return None


def _resolve_cookies(source_id: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    cookies = settings.yt_dlp_cookies
    cookies_file = settings.yt_dlp_cookies_file
    if source_id and source_id in settings.yt_dlp_cookies_files:
        cookies_file = settings.yt_dlp_cookies_files[source_id]
    return cookies, cookies_file


def _guess_source(url: str, force: Optional[str]) -> Optional[str]:
    if force:
        return force
    from urllib.parse import urlparse
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return None
    for sid, info in settings.MUSIC_SOURCES.items() if hasattr(settings, 'MUSIC_SOURCES') else []:
        pass
    from config import MUSIC_SOURCES
    for sid, info in MUSIC_SOURCES.items():
        for domain in info["domains"]:
            if host == domain or host.endswith("." + domain):
                return sid
    return None


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
# Sync yt-dlp wrappers
# ---------------------------------------------------------------------------

def extract_info_sync(
    url: str,
    *,
    source: Optional[str] = None,
    skip_download: bool = False,
    format_selector: Optional[str] = None,
    use_aria2c: bool = False,
    sponsorblock: bool = True,
) -> dict:
    resolved_source = _guess_source(url, source)
    cookies, cookies_file = _resolve_cookies(resolved_source)
    proxy = _resolve_proxy(resolved_source)
    fmt = format_selector or settings.yt_dlp_format

    tmp_dir = settings.download_dir / "_extract"
    opts = _build_ydl_opts(
        output_dir=tmp_dir,
        format_selector=fmt,
        cookies=cookies,
        cookies_file=cookies_file,
        proxy=proxy,
        skip_download=skip_download,
        use_aria2c=use_aria2c,
        sponsorblock=sponsorblock,
    )

    last_error: Optional[Exception] = None
    for attempt in range(1, settings.yt_dlp_retries + 1):
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False, process=True)
            return _safe_info(info)
        except DownloadError as exc:
            last_error = exc
        except Exception as exc:
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
    use_aria2c: bool = False,
    job: Optional[DownloadJob] = None,
) -> Path:
    resolved_source = _guess_source(url, source)
    cookies, cookies_file = _resolve_cookies(resolved_source)
    proxy = _resolve_proxy(resolved_source)
    fmt = format_selector or settings.yt_dlp_format

    # Progress hook for job updates
    def progress_hook(d: dict) -> None:
        if job is None:
            return
        status = d.get("status")
        if status == "downloading":
            p = d.get("_percent_str", "0%").replace("%", "")
            try:
                job.progress = float(p)
            except ValueError:
                pass
            job.status = "downloading"
            job.updated_at = datetime.now(timezone.utc).isoformat()
        elif status == "finished":
            job.progress = 100.0
            job.status = "completed"
            job.updated_at = datetime.now(timezone.utc).isoformat()

    opts = _build_ydl_opts(
        output_dir=output_dir,
        format_selector=fmt,
        cookies=cookies,
        cookies_file=cookies_file,
        proxy=proxy,
        max_filesize_mb=settings.download_max_filesize_mb or None,
        use_aria2c=use_aria2c,
        sponsorblock=True,
    )
    opts["progress_hooks"] = [progress_hook]

    last_error: Optional[Exception] = None
    downloaded: Optional[Path] = None
    for attempt in range(1, settings.yt_dlp_retries + 1):
        if job and job.cancelled:
            raise RuntimeError("Download cancelled by user")
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
            info = _safe_info(info)
            video_id = info.get("id") or url
            for candidate in sorted(output_dir.glob(f"{video_id}.*")):
                if candidate.is_file():
                    downloaded = candidate
                    break
            if downloaded is None:
                files = [p for p in output_dir.iterdir() if p.is_file()]
                if files:
                    downloaded = max(files, key=lambda p: p.stat().st_mtime)
            break
        except DownloadError as exc:
            last_error = exc
        except Exception as exc:
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
    from config import search_prefix_for
    prefix = search_prefix_for(source)
    if not prefix:
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
        except Exception as exc:
            last_error = exc
        if attempt < settings.yt_dlp_retries:
            time.sleep(0.8 * attempt)
    raise RuntimeError(f"yt-dlp search failed: {last_error}")


# ---------------------------------------------------------------------------
# Subprocess integration for Spotify metadata
# ---------------------------------------------------------------------------

def _spotdl_available() -> bool:
    return _has_spotdl()


def spotdl_download_sync(
    query: str,
    *,
    output_dir: Path,
    audio_provider: str = "youtube",
    lyrics_provider: str = "synced",
    save_file: bool = False,
) -> dict:
    """Use spotdl to download a Spotify track with full metadata."""
    if not _spotdl_available():
        raise RuntimeError("spotdl is not installed or not in PATH")

    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        settings.spotdl_path,
        "download",
        query,
        "--output", str(output_dir / "{artists} - {title}.{ext}"),
        "--audio", audio_provider,
        "--lyrics", lyrics_provider,
        "--write-to", "m3u",
        "--save-file", str(output_dir / "spotdl_cache.json") if save_file else "none",
    ]

    if settings.spotify_client_id and settings.spotify_client_secret:
        cmd += ["--client-id", settings.spotify_client_id, "--client-secret", settings.spotify_client_secret]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=300,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("spotdl download timed out")
    except FileNotFoundError:
        raise RuntimeError("spotdl command not found")

    if result.returncode != 0:
        raise RuntimeError(f"spotdl failed: {result.stderr.strip()[:500]}")

    # Find the downloaded file
    files = [p for p in output_dir.iterdir() if p.is_file() and p.suffix.lower() in {".mp3", ".m4a", ".opus", ".flac", ".wav"}]
    if not files:
        raise RuntimeError("spotdl did not produce an output file")

    downloaded = max(files, key=lambda p: p.stat().st_mtime)

    return {
        "file_path": str(downloaded),
        "title": downloaded.stem,
        "filesize": downloaded.stat().st_size,
        "provider": "spotdl",
    }


# ---------------------------------------------------------------------------
# Lyrics extraction via syncedlyrics
# ---------------------------------------------------------------------------

def extract_lyrics_sync(
    title: str,
    artist: Optional[str] = None,
    provider: Optional[str] = None,
) -> Optional[str]:
    """Fetch lyrics using syncedlyrics library."""
    try:
        import syncedlyrics
    except ImportError:
        return None

    prov = provider or settings.lyrics_default_provider
    query = f"{artist} - {title}" if artist else title

    try:
        if prov == "synced":
            return syncedlyrics.search(query)
        elif prov in {"genius", "musixmatch", "azlyrics"}:
            return syncedlyrics.search(query, providers=[prov])
        else:
            return syncedlyrics.search(query)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Metadata embedding via mutagen
# ---------------------------------------------------------------------------

def embed_metadata_sync(
    file_path: Path,
    *,
    title: Optional[str] = None,
    artist: Optional[str] = None,
    album: Optional[str] = None,
    album_art_url: Optional[str] = None,
    genres: Optional[list[str]] = None,
    year: Optional[int] = None,
    track_number: Optional[int] = None,
    isrc: Optional[str] = None,
    lyrics: Optional[str] = None,
) -> None:
    """Embed ID3 / Vorbis comments metadata into an audio file."""
    if not settings.metadata_embed:
        return

    try:
        from mutagen import File
        from mutagen.id3 import ID3, TIT2, TPE1, TALB, TPE2, TDRC, TRCK, TCON, TSRC, USLT, APIC
        from mutagen.mp4 import MP4
        from mutagen.flac import FLAC
        from mutagen.oggvorbis import OggVorbis
    except ImportError:
        return

    ext = file_path.suffix.lower()

    try:
        if ext == ".mp3":
            audio = ID3(str(file_path))
            if title: audio.add(TIT2(encoding=3, text=title))
            if artist: audio.add(TPE1(encoding=3, text=artist))
            if album: audio.add(TALB(encoding=3, text=album))
            if album and artist: audio.add(TPE2(encoding=3, text=artist))
            if year: audio.add(TDRC(encoding=3, text=str(year)))
            if track_number: audio.add(TRCK(encoding=3, text=str(track_number)))
            if genres: audio.add(TCON(encoding=3, text=", ".join(genres)))
            if isrc: audio.add(TSRC(encoding=3, text=isrc))
            if lyrics:
                audio.add(USLT(encoding=3, lang="eng", desc="", text=lyrics))
            if album_art_url:
                try:
                    import urllib.request
                    img_data = urllib.request.urlopen(album_art_url, timeout=10).read()
                    audio.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=img_data))
                except Exception:
                    pass
            audio.save(v2_version=3)
        elif ext in {".m4a", ".mp4"}:
            audio = MP4(str(file_path))
            if title: audio["\xa9nam"] = [title]
            if artist: audio["\xa9ART"] = [artist]
            if album: audio["\xa9alb"] = [album]
            if year: audio["\xa9day"] = [str(year)]
            if track_number: audio["trkn"] = [(track_number, 0)]
            if genres: audio["\xa9gen"] = [", ".join(genres)]
            if lyrics: audio["\xa9lyr"] = [lyrics]
            audio.save()
        elif ext == ".flac":
            audio = FLAC(str(file_path))
            if title: audio["title"] = [title]
            if artist: audio["artist"] = [artist]
            if album: audio["album"] = [album]
            if year: audio["date"] = [str(year)]
            if track_number: audio["tracknumber"] = [str(track_number)]
            if genres: audio["genre"] = [", ".join(genres)]
            if isrc: audio["isrc"] = [isrc]
            if lyrics: audio["lyrics"] = [lyrics]
            audio.save()
        elif ext in {".ogg", ".opus"}:
            audio = OggVorbis(str(file_path))
            if title: audio["title"] = [title]
            if artist: audio["artist"] = [artist]
            if album: audio["album"] = [album]
            if year: audio["date"] = [str(year)]
            if track_number: audio["tracknumber"] = [str(track_number)]
            if genres: audio["genre"] = [", ".join(genres)]
            if lyrics: audio["lyrics"] = [lyrics]
            audio.save()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Async API used by main.py
# ---------------------------------------------------------------------------

async def extract_info(
    url: str,
    *,
    source: Optional[str] = None,
    skip_download: bool = False,
    format_selector: Optional[str] = None,
    use_aria2c: bool = False,
    sponsorblock: bool = True,
) -> dict:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: extract_info_sync(
            url, source=source, skip_download=skip_download,
            format_selector=format_selector, use_aria2c=use_aria2c,
            sponsorblock=sponsorblock,
        ),
    )


async def download_audio(
    url: str,
    *,
    source: Optional[str] = None,
    output_dir: Path,
    format_selector: Optional[str] = None,
    use_aria2c: bool = False,
    job: Optional[DownloadJob] = None,
) -> Path:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: download_audio_sync(
            url, source=source, output_dir=output_dir,
            format_selector=format_selector, use_aria2c=use_aria2c, job=job,
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


async def extract_lyrics(
    title: str,
    *,
    artist: Optional[str] = None,
    provider: Optional[str] = None,
) -> Optional[str]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: extract_lyrics_sync(title, artist=artist, provider=provider),
    )


async def embed_metadata(
    file_path: Path,
    **kwargs,
) -> None:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: embed_metadata_sync(file_path, **kwargs),
    )


# ---------------------------------------------------------------------------
# Download queue management
# ---------------------------------------------------------------------------

async def enqueue_download(job: DownloadJob) -> None:
    async with _QUEUE_LOCK:
        JOBS[job.job_id] = job
        JOB_QUEUE.append(job.job_id)
    # Start processing in background
    asyncio.create_task(_process_queue())


async def _process_queue() -> None:
    while True:
        async with _QUEUE_LOCK:
            if not JOB_QUEUE:
                return
            job_id = JOB_QUEUE.pop(0)
            job = JOBS.get(job_id)
            if not job or job.status in {"completed", "failed", "cancelled"}:
                continue
            job.status = "downloading"
            job.updated_at = datetime.now(timezone.utc).isoformat()

        sem = _get_semaphore()
        async with sem:
            if job.cancelled:
                job.status = "cancelled"
                job.updated_at = datetime.now(timezone.utc).isoformat()
                continue
            try:
                from urllib.parse import urlparse
                host = urlparse(job.url).netloc.lower()
                from config import MUSIC_SOURCES
                use_aria2c = settings.aria2c_enabled and _has_aria2c()
                # Spotify URLs: use spotdl
                if job.source == "spotify" or "open.spotify.com" in host or "spotify.com" in host:
                    if settings.spotdl_enabled and _spotdl_available():
                        out_dir = settings.download_dir / job.job_id
                        result = await asyncio.get_running_loop().run_in_executor(
                            None,
                            lambda: spotdl_download_sync(
                                job.url, output_dir=out_dir,
                                audio_provider="youtube",
                                lyrics_provider=settings.lyrics_default_provider,
                            ),
                        )
                        job.file_path = result["file_path"]
                        job.status = "completed"
                        job.progress = 100.0
                    else:
                        # Fall back to yt-dlp on the Spotify URL
                        out_dir = settings.download_dir / job.job_id
                        file_path = await download_audio(
                            job.url, source=job.source, output_dir=out_dir,
                            use_aria2c=use_aria2c, job=job,
                        )
                        job.file_path = str(file_path)
                        job.status = "completed"
                        job.progress = 100.0
                else:
                    out_dir = settings.download_dir / job.job_id
                    file_path = await download_audio(
                        job.url, source=job.source, output_dir=out_dir,
                        use_aria2c=use_aria2c, job=job,
                    )
                    job.file_path = str(file_path)
                    job.status = "completed"
                    job.progress = 100.0
            except Exception as exc:  # noqa: BLE001
                job.status = "failed"
                job.error = str(exc)
                job.updated_at = datetime.now(timezone.utc).isoformat()


async def get_job(job_id: str) -> Optional[dict]:
    job = JOBS.get(job_id)
    return job.to_dict() if job else None


async def cancel_job(job_id: str) -> bool:
    job = JOBS.get(job_id)
    if not job:
        return False
    job.cancelled = True
    if job.status == "queued":
        job.status = "cancelled"
        job.updated_at = datetime.now(timezone.utc).isoformat()
    return True


async def list_jobs() -> list[dict]:
    return [j.to_dict() for j in JOBS.values()]


async def cleanup_stale_downloads() -> None:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, lambda: _cleanup_stale(settings.download_dir))
