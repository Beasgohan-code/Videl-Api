"""Videl-Api — powerful multi-source music REST API.

Endpoints:
  GET    /                              API info
  GET    /health                        Health check + features
  GET    /v1/sources                    List supported music sources
  GET    /v1/search                     Search music across sources
  POST   /v1/search                     Search music (JSON body)
  GET    /v1/info                       Extract track/album/playlist info
  POST   /v1/info                       Extract info (JSON body)
  GET    /v1/lyrics                     Get lyrics for a track
  POST   /v1/lyrics                     Get lyrics (JSON body)
  GET    /v1/lyrics/search              Search lyrics by title+artist
  POST   /v1/lyrics/search              Search lyrics (JSON body)
  GET    /v1/metadata                   Enrich metadata from Spotify
  POST   /v1/metadata                   Enrich metadata (JSON body)
  GET    /v1/download                   Download audio file
  POST   /v1/download                   Download audio (JSON body)
  POST   /v1/download/queue             Enqueue a background download job
  GET    /v1/download/queue             List download jobs
  GET    /v1/download/status/{job_id}   Get job status
  POST   /v1/download/cancel/{job_id}   Cancel a job
  GET    /v1/file/{folder}/{filename}   Serve downloaded file (auto-cleanup)
  GET    /v1/stream                     Resolve direct stream URL
  POST   /v1/keys                       Create a new API key
  GET    /v1/keys                       List your API keys
  DELETE /v1/keys/{key}                 Revoke an API key
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, status
from starlette.background import BackgroundTask
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse

from auth import create_api_key, list_api_keys, revoke_api_key, validate_api_key
from config import settings, list_sources, MUSIC_SOURCES
from downloader import (
    cleanup_stale_downloads, download_audio, embed_metadata, enqueue_download,
    extract_info, extract_lyrics, get_job, cancel_job, list_jobs, search,
    spotdl_download_sync, JOBS,
)
from models import (
    DownloadResponse, ErrorResponse, HealthResponse, JobListResponse,
    JobActionResponse, LyricsResponse, LyricsSearchRequest, MetadataResponse,
    MetadataRequest, SearchResponse, SourcesResponse, TrackInfoResponse,
    DownloadJobItem,
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
    version="2.1.0",
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


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

async def get_auth(_: dict = Depends(validate_api_key)) -> dict:
    return _


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
# Root / health
# ---------------------------------------------------------------------------

@app.get("/", tags=["meta"])
async def root():
    return {
        "name": "Videl-Api",
        "version": "2.1.0",
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
        features={
            "aria2c": bool(settings.aria2c_path),
            "ffmpeg": bool(settings.ffmpeg_path),
            "spotdl": settings.spotdl_enabled,
            "metadata_embed": settings.metadata_embed,
            "sponsorblock": settings.sponsorblock,
            "search": True,
            "lyrics": True,
        },
    )


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

@app.get("/v1/sources", response_model=SourcesResponse, tags=["meta"])
async def sources_list(_: dict = Depends(get_auth)):
    return SourcesResponse(sources=list_sources())


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

async def _do_search(q: str, source: str, limit: int) -> SearchResponse:
    limit = max(1, min(limit, settings.search_max_limit))
    try:
        raw = await search(q, source=source, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
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
    except Exception as exc:
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
        lyrics_available=bool(info.get("lyrics")),
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

async def _do_lyrics(url: str, provider: Optional[str]) -> LyricsResponse:
    try:
        info = await extract_info(url, skip_download=True)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Lyrics extraction failed: {exc}",
        )

    source_id = _guess_source(url)
    source_info = MUSIC_SOURCES.get(source_id, {})

    title = info.get("title", "Unknown")
    artist = info.get("artist") or info.get("uploader") or info.get("creator")

    lyrics = info.get("lyrics")
    provider_used = info.get("lyrics_provider")

    if not lyrics and provider:
        lyrics = await extract_lyrics(title, artist=artist, provider=provider)
        provider_used = provider

    if not lyrics and artist:
        lyrics = await extract_lyrics(title, artist=artist, provider=None)
        provider_used = provider_used or settings.lyrics_default_provider

    return LyricsResponse(
        id=info.get("id", url),
        title=title,
        source=source_id or "unknown",
        source_name=source_info.get("name", source_id or "unknown"),
        lyrics=lyrics,
        lyrics_provider=provider_used,
    )


@app.get("/v1/lyrics", response_model=LyricsResponse, tags=["lyrics"])
async def lyrics_get(url: str, provider: Optional[str] = None, _: dict = Depends(get_auth)):
    return await _do_lyrics(url, provider)


@app.post("/v1/lyrics", response_model=LyricsResponse, tags=["lyrics"])
async def lyrics_post(payload, _: dict = Depends(get_auth)):
    url = _payload_field(payload, "url")
    provider = _payload_field(payload, "provider")
    return await _do_lyrics(url, provider)


@app.post("/v1/lyrics/search", response_model=LyricsResponse, tags=["lyrics"])
async def lyrics_search(payload: LyricsSearchRequest, _: dict = Depends(get_auth)):
    lyrics = await extract_lyrics(
        payload.title, artist=payload.artist, provider=payload.provider
    )
    return LyricsResponse(
        id=payload.title,
        title=payload.title,
        source="lyrics_search",
        lyrics=lyrics,
        lyrics_provider=payload.provider or settings.lyrics_default_provider,
    )


# ---------------------------------------------------------------------------
# Metadata (Spotify enrichment)
# ---------------------------------------------------------------------------

@app.get("/v1/metadata", response_model=MetadataResponse, tags=["metadata"])
async def metadata_get(
    url: Optional[str] = None,
    query: Optional[str] = None,
    _: dict = Depends(get_auth),
):
    return await _do_metadata(url, query)


@app.post("/v1/metadata", response_model=MetadataResponse, tags=["metadata"])
async def metadata_post(payload: MetadataRequest, _: dict = Depends(get_auth)):
    return await _do_metadata(payload.url, payload.query)


async def _do_metadata(url: Optional[str], query: Optional[str]) -> MetadataResponse:
    # Try spotdl for Spotify metadata
    if settings.spotdl_enabled and _has_spotdl():
        target = url or query or ""
        if not target:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Provide a Spotify URL or search query",
            )
        try:
            import subprocess
            cmd = [settings.spotdl_path, "url", target]
            if settings.spotify_client_id and settings.spotify_client_secret:
                cmd += ["--client-id", settings.spotify_client_id, "--client-secret", settings.spotify_client_secret]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                # spotdl 'url' returns download URLs; parse tracks from output
                lines = [l for l in result.stdout.splitlines() if l.strip()]
                tracks = []
                for i, line in enumerate(lines):
                    tracks.append(MetadataTrack(
                        id=str(i),
                        name=line.strip(),
                        artists=[],
                        spotify_url=target if "open.spotify.com" in target else None,
                    ))
                return MetadataResponse(type="track", tracks=tracks, total=len(tracks))
        except Exception:
            pass

    # Fallback: return empty
    return MetadataResponse(type="unknown", tracks=[], total=0)


def _has_spotdl() -> bool:
    try:
        subprocess_result = __import__("subprocess").run(
            [settings.spotdl_path, "--version"],
            capture_output=True, check=False, timeout=5,
        )
        return subprocess_result.returncode == 0
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Download (direct)
# ---------------------------------------------------------------------------

async def _do_download(url: str, source: Optional[str], fmt: str, quality: Optional[str],
                       use_aria2c: bool, embed_metadata_flag: bool, fetch_lyrics: bool):
    source_id = source or _guess_source(url)
    folder = f"{int(time.time()*1000)}"
    output_dir = settings.download_dir / folder
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        file_path = await download_audio(
            url, source=source_id, output_dir=output_dir,
            format_selector=fmt, use_aria2c=use_aria2c,
        )
    except Exception as exc:
        shutil_rmtree(output_dir)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Download failed: {exc}",
        )

    info = {}
    try:
        info = await extract_info(url, source=source_id, skip_download=True)
    except Exception:
        pass

    # Fetch lyrics if requested
    lyrics = None
    if fetch_lyrics:
        title = info.get("title", "Unknown")
        artist = info.get("artist") or info.get("uploader") or info.get("creator")
        try:
            lyrics = await extract_lyrics(title, artist=artist)
        except Exception:
            pass

    # Embed metadata
    if embed_metadata_flag and settings.metadata_embed:
        try:
            await embed_metadata(
                file_path,
                title=info.get("title"),
                artist=info.get("artist") or info.get("creator"),
                album=info.get("album"),
                genres=info.get("genres"),
                year=info.get("release_year"),
                track_number=info.get("track_number"),
                lyrics=lyrics,
            )
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
        lyrics=lyrics,
    )


def shutil_rmtree(path: Path) -> None:
    import shutil
    shutil.rmtree(path, ignore_errors=True)


@app.get("/v1/download", response_model=DownloadResponse, tags=["download"])
async def download_get(
    url: str,
    source: Optional[str] = None,
    format: str = "bestaudio/best",
    quality: Optional[str] = None,
    use_aria2c: bool = True,
    embed_metadata: bool = True,
    fetch_lyrics: bool = False,
    _: dict = Depends(get_auth),
):
    return await _do_download(url, source, format, quality, use_aria2c, embed_metadata, fetch_lyrics)


@app.post("/v1/download", response_model=DownloadResponse, tags=["download"])
async def download_post(payload, _: dict = Depends(get_auth)):
    url = _payload_field(payload, "url")
    source = _payload_field(payload, "source")
    fmt = _payload_field(payload, "format", "bestaudio/best")
    quality = _payload_field(payload, "quality")
    use_aria2c = _payload_field(payload, "use_aria2c", True)
    embed_metadata_flag = _payload_field(payload, "embed_metadata", True)
    fetch_lyrics = _payload_field(payload, "fetch_lyrics", False)
    return await _do_download(url, source, fmt, quality, use_aria2c, embed_metadata_flag, fetch_lyrics)


# ---------------------------------------------------------------------------
# Download queue (background jobs)
# ---------------------------------------------------------------------------

@app.post("/v1/download/queue", response_model=DownloadJobItem, tags=["download"])
async def queue_download(
    url: str,
    source: Optional[str] = None,
    _: dict = Depends(get_auth),
):
    import uuid as _uuid
    job_id = _uuid.uuid4().hex
    from downloader import DownloadJob
    job = DownloadJob(job_id=job_id, url=url, source=source or _guess_source(url))
    await enqueue_download(job)
    return DownloadJobItem(**job.to_dict())


@app.get("/v1/download/queue", response_model=JobListResponse, tags=["download"])
async def list_downloads(_: dict = Depends(get_auth)):
    jobs = await list_jobs()
    return JobListResponse(jobs=[DownloadJobItem(**j) for j in jobs])


@app.get("/v1/download/status/{job_id}", response_model=DownloadJobItem, tags=["download"])
async def download_status(job_id: str, _: dict = Depends(get_auth)):
    job = await get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return DownloadJobItem(**job)


@app.post("/v1/download/cancel/{job_id}", response_model=JobActionResponse, tags=["download"])
async def cancel_download(job_id: str, _: dict = Depends(get_auth)):
    ok = await cancel_job(job_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return JobActionResponse(job_id=job_id, action="cancel", success=True)


# ---------------------------------------------------------------------------
# Serve downloaded files
# ---------------------------------------------------------------------------

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


def _cleanup_file(path: Path) -> None:
    if path.exists():
        path.unlink(missing_ok=True)
    parent = path.parent
    if parent.exists() and not any(parent.iterdir()):
        shutil.rmtree(parent, ignore_errors=True)


# ---------------------------------------------------------------------------
# Stream redirect
# ---------------------------------------------------------------------------

@app.get("/v1/stream", tags=["download"])
async def stream_redirect(url: str, source: Optional[str] = None, _: dict = Depends(get_auth)):
    try:
        info = await extract_info(url, source=source, skip_download=True)
    except Exception as exc:
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
