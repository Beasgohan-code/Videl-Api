"""Videl-Api — powerful multi-source music REST API."""

from __future__ import annotations

import time
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, status
from starlette.background import BackgroundTask
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse

from auth import create_api_key, list_api_keys, revoke_api_key, validate_api_key
from config import settings, list_sources, MUSIC_SOURCES
from downloader import _cleanup_file, cleanup_stale_downloads, download_audio, extract_info, search
from models import (
    DownloadResponse,
    HealthResponse,
    LyricsResponse,
    SearchResponse,
    SourcesResponse,
    TrackInfoResponse,
)

START_TIME = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.download_dir.mkdir(parents=True, exist_ok=True)
    await cleanup_stale_downloads()
    yield


app = FastAPI(
    title="Videl-Api",
    description="Multi-source music REST API for music bots and more.",
    version="2.0.0",
    lifespan=lifespan,
)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins if settings.cors_origins != ["*"] else ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


async def get_auth(_: dict = Depends(validate_api_key)) -> dict:
    return _


@app.get("/", tags=["meta"])
async def root():
    return {
        "name": "Videl-Api",
        "version": "2.0.0",
        "description": "Multi-source music REST API for music bots.",
        "docs": "/docs",
        "health": "/health",
        "sources": "/v1/sources",
        "auth": "X-API-Key header",
    }


@app.get("/health", response_model=HealthResponse, tags=["meta"])
async def health():
    return HealthResponse(
        status="ok",
        sources=len(list_sources()),
        uptime_seconds=time.time() - START_TIME,
    )


@app.get("/v1/sources", response_model=SourcesResponse, tags=["meta"])
async def sources_list(_: dict = Depends(get_auth)):
    return SourcesResponse(sources=list_sources())


def _payload_field(payload, name, default=None):
    if isinstance(payload, dict):
        return payload.get(name, default)
    return getattr(payload, name, default)


def _guess_source(url: str) -> Optional[str]:
    from urllib.parse import urlparse

    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return None
    for sid, info in MUSIC_SOURCES.items():
        for domain in info["domains"]:
            if host == domain or host.endswith("." + domain):
                return sid
    return None


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


async def _do_search(q: str, source: str, limit: int) -> SearchResponse:
    limit = max(1, min(limit, settings.search_max_limit))
    try:
        raw = await search(q, source=source, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Search failed: {exc}",
        )

    results = []
    source_info = MUSIC_SOURCES.get(source, {})
    for entry in raw:
        results.append(
            {
                "id": entry.get("id", ""),
                "title": entry.get("title", "Unknown"),
                "source": source,
                "source_name": source_info.get("name", source),
                "uploader": entry.get("uploader") or entry.get("creator"),
                "duration": entry.get("duration"),
                "view_count": entry.get("view_count"),
                "thumbnail": entry.get("thumbnail"),
                "url": entry.get("url") or entry.get("webpage_url"),
                "webpage_url": entry.get("webpage_url"),
                "is_playlist": entry.get("_type") == "playlist",
                "is_album": False,
            }
        )
    return SearchResponse(query=q, source=source, results=results, total=len(results))


@app.get("/v1/search", response_model=SearchResponse, tags=["search"])
async def search_get(q: str, source: str = "youtube", limit: int = 20, _: dict = Depends(get_auth)):
    return await _do_search(q, source, limit)


@app.post("/v1/search", response_model=SearchResponse, tags=["search"])
async def search_post(payload, _: dict = Depends(get_auth)):
    q = _payload_field(payload, "q")
    source = _payload_field(payload, "source", "youtube")
    limit = _payload_field(payload, "limit", 20)
    return await _do_search(q, source, limit)


# ---------------------------------------------------------------------------
# Info
# ---------------------------------------------------------------------------


async def _do_info(url: str, source: Optional[str]) -> TrackInfoResponse:
    try:
        info = await extract_info(url, source=source, skip_download=True)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Info extraction failed: {exc}",
        )

    if not info:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Track not found")

    source_id = source or _guess_source(url)
    source_info = MUSIC_SOURCES.get(source_id, {})
    entries = info.get("entries") or []
    is_playlist = info.get("_type") == "playlist" or bool(entries and len(entries) > 1)

    mini_entries = []
    for e in entries:
        mini_entries.append(
            {
                "id": e.get("id", ""),
                "title": e.get("title", "Unknown"),
                "source": source_id,
                "source_name": source_info.get("name", source_id),
                "uploader": e.get("uploader") or e.get("creator"),
                "duration": e.get("duration"),
                "view_count": e.get("view_count"),
                "thumbnail": e.get("thumbnail"),
                "url": e.get("url") or e.get("webpage_url"),
                "webpage_url": e.get("webpage_url"),
                "is_playlist": e.get("_type") == "playlist",
                "is_album": False,
            }
        )

    return TrackInfoResponse(
        id=info.get("id", url),
        title=info.get("title", "Unknown"),
        source=source_id,
        source_name=source_info.get("name", source_id),
        uploader=info.get("uploader") or info.get("creator"),
        uploader_url=info.get("uploader_url"),
        duration=info.get("duration"),
        view_count=info.get("view_count"),
        like_count=info.get("like_count"),
        thumbnail=info.get("thumbnail"),
        description=info.get("description"),
        webpage_url=info.get("webpage_url"),
        url=info.get("url"),
        ext=info.get("ext"),
        format_id=info.get("format_id"),
        abr=info.get("abr"),
        filesize=info.get("filesize"),
        is_playlist=is_playlist,
        is_album=info.get("_type") == "album",
        track_number=info.get("track_number"),
        album=info.get("album"),
        artist=info.get("artist") or info.get("creator"),
        genres=info.get("genres") or [],
        release_year=info.get("release_year"),
        entries=mini_entries,
    )


@app.get("/v1/info", response_model=TrackInfoResponse, tags=["info"])
async def info_get(url: str, source: Optional[str] = None, _: dict = Depends(get_auth)):
    return await _do_info(url, source)


@app.post("/v1/info", response_model=TrackInfoResponse, tags=["info"])
async def info_post(payload, _: dict = Depends(get_auth)):
    url = _payload_field(payload, "url")
    source = _payload_field(payload, "source")
    return await _do_info(url, source)


# ---------------------------------------------------------------------------
# Lyrics
# ---------------------------------------------------------------------------


async def _do_lyrics(url: str) -> LyricsResponse:
    try:
        info = await extract_info(url, skip_download=True)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Lyrics extraction failed: {exc}",
        )

    source_id = _guess_source(url)
    source_info = MUSIC_SOURCES.get(source_id, {})

    lyrics = info.get("lyrics") or info.get("subtitles") or None
    provider = info.get("lyrics_provider")

    return LyricsResponse(
        id=info.get("id", url),
        title=info.get("title", "Unknown"),
        source=source_id or "unknown",
        source_name=source_info.get("name", source_id or "unknown"),
        lyrics=lyrics,
        lyrics_provider=provider,
    )


@app.get("/v1/lyrics", response_model=LyricsResponse, tags=["lyrics"])
async def lyrics_get(url: str, _: dict = Depends(get_auth)):
    return await _do_lyrics(url)


@app.post("/v1/lyrics", response_model=LyricsResponse, tags=["lyrics"])
async def lyrics_post(payload, _: dict = Depends(get_auth)):
    url = _payload_field(payload, "url")
    return await _do_lyrics(url)


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------


async def _do_download(url: str, source: Optional[str], format: str, quality: Optional[str]):
    source_id = source or _guess_source(url)
    folder = f"{int(time.time()*1000)}"
    output_dir = settings.download_dir / folder
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        file_path = await download_audio(
            url,
            source=source_id,
            output_dir=output_dir,
            format_selector=format,
        )
    except Exception as exc:  # noqa: BLE001
        shutil.rmtree(output_dir, ignore_errors=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Download failed: {exc}",
        )

    info = {}
    try:
        info = await extract_info(url, source=source_id, skip_download=True)
    except Exception:
        pass

    media_type = "audio/mpeg" if file_path.suffix.lower() == ".mp3" else "application/octet-stream"
    download_url = f"{settings.api_base_url.rstrip('/')}/v1/file/{folder}/{file_path.name}"

    return DownloadResponse(
        id=info.get("id", source_id or "unknown"),
        title=info.get("title", "Unknown"),
        source=source_id or "unknown",
        file_path=str(file_path),
        download_url=download_url,
        media_type=media_type,
        filesize=file_path.stat().st_size if file_path.exists() else None,
        duration=info.get("duration"),
        ext=file_path.suffix.lstrip(".") if file_path.suffix else None,
    )


@app.get("/v1/download", response_model=DownloadResponse, tags=["download"])
async def download_get(
    url: str,
    source: Optional[str] = None,
    format: str = "bestaudio/best",
    quality: Optional[str] = None,
    _: dict = Depends(get_auth),
):
    return await _do_download(url, source, format, quality)


@app.post("/v1/download", response_model=DownloadResponse, tags=["download"])
async def download_post(payload, _: dict = Depends(get_auth)):
    url = _payload_field(payload, "url")
    source = _payload_field(payload, "source")
    format = _payload_field(payload, "format", "bestaudio/best")
    quality = _payload_field(payload, "quality")
    return await _do_download(url, source, format, quality)


@app.get("/v1/file/{folder}/{filename}", tags=["download"])
async def serve_file(folder: str, filename: str, _: dict = Depends(get_auth)):
    file_path = settings.download_dir / folder / filename
    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/octet-stream",
        background=BackgroundTask(_cleanup_file, file_path),
    )


@app.get("/v1/stream", tags=["download"])
async def stream_redirect(url: str, source: Optional[str] = None, _: dict = Depends(get_auth)):
    """Resolve the direct stream URL without downloading server-side."""
    try:
        info = await extract_info(url, source=source, skip_download=True)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Stream resolution failed: {exc}",
        )
    direct_url = info.get("url") or info.get("webpage_url") or url
    return RedirectResponse(url=direct_url)


# ---------------------------------------------------------------------------
# API Keys
# ---------------------------------------------------------------------------


@app.post("/v1/keys", tags=["keys"])
async def create_key(owner_id: int = 0):
    """Create a new API key. Open by default (no auth required) so you can
    bootstrap your first key; protect this behind a reverse proxy or admin key
    in production if desired. Usage: POST /v1/keys?owner_id=123"""
    record = await create_api_key(owner_id)
    return {"key": record.key, "owner_id": record.owner_id, "active": record.active}


@app.get("/v1/keys", tags=["keys"])
async def list_keys(owner_id: int = 0, _: dict = Depends(get_auth)):
    return await list_api_keys(owner_id)


@app.delete("/v1/keys/{key}", tags=["keys"])
async def delete_key(key: str, owner_id: int = 0, _: dict = Depends(get_auth)):
    ok = await revoke_api_key(owner_id, key)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    return {"revoked": True, "key": key}




