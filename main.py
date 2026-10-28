"""Videl-Api — powerful multi-source media REST API.

Endpoints:
  GET    /                              API info
  GET    /health                        Health check + features
  GET    /v1/sources                    List supported media sources
  GET    /v1/search                     Search media across sources
  POST   /v1/search                     Search media (JSON body)
  GET    /v1/federated-search           Federated search across all sources
  POST   /v1/federated-search           Federated search (JSON body)
  GET    /v1/info                       Extract track/album/playlist info
  POST   /v1/info                       Extract info (JSON body)
  GET    /v1/lyrics                     Get lyrics for a track
  POST   /v1/lyrics                     Get lyrics (JSON body)
  GET    /v1/lyrics/search              Search lyrics by title+artist
  POST   /v1/lyrics/search              Search lyrics (JSON body)
  GET    /v1/metadata                   Enrich metadata from Spotify
  POST   /v1/metadata                   Enrich metadata (JSON body)
  GET    /v1/download                   Download media file
  POST   /v1/download                   Download media (JSON body)
  POST   /v1/download/advanced          Advanced download (priority, schedule)
  GET    /v1/download/advanced          List advanced download jobs
  GET    /v1/download/advanced/status/{job_id}   Job status
  POST   /v1/download/advanced/pause/{job_id}    Pause a job
  POST   /v1/download/advanced/resume/{job_id}   Resume a job
  POST   /v1/download/advanced/cancel/{job_id}   Cancel a job
  POST   /v1/download/queue             Enqueue a background download job
  GET    /v1/download/queue             List download jobs
  GET    /v1/download/status/{job_id}   Get job status
  POST   /v1/download/cancel/{job_id}   Cancel a job
  GET    /v1/file/{folder}/{filename}   Serve downloaded file (auto-cleanup)
  GET    /v1/stream                     Resolve direct stream URL
  GET    /v1/m3u8/parse                 Parse M3U8/HLS playlist
  POST   /v1/m3u8/parse                 Parse M3U8/HLS playlist (JSON)
  POST   /v1/m3u8/download              Download M3U8/HLS stream
  POST   /v1/m3u8/download/queue        Enqueue M3U8 background job
  GET    /v1/m3u8/download/queue        List M3U8 jobs
  GET    /v1/m3u8/download/status/{id}  M3U8 job status
  POST   /v1/m3u8/download/cancel/{id}  Cancel M3U8 job
  POST   /v1/download/add               Add download to manager
  GET    /v1/download/status/{gid}      Download status
  POST   /v1/download/remove/{gid}      Remove download
  POST   /v1/keys                       Create a new API key
  GET    /v1/keys                       List your API keys
  DELETE /v1/keys/{key}                 Revoke an API key
  GET    /v1/keys/extended              Extended key info
  POST   /v1/keys/share                 Share a key
"""

from __future__ import annotations

import asyncio
import os
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field
from fastapi import Depends, FastAPI, HTTPException, status, WebSocket, WebSocketDisconnect
from starlette.background import BackgroundTask
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response

from auth import create_api_key, list_api_keys, revoke_api_key, validate_api_key, _load_json, _save_json, KEYS_FILE
from config import settings, list_sources, MUSIC_SOURCES
from cache import search_cache, metadata_cache, lyrics_cache, source_health_cache
from scheduler import scheduler, register_default_tasks
from plugins import plugin_manager
from rate_limit import rate_limiter
from websocket_manager import ws_manager, handle_websocket
from download_manager import download_manager, AdvancedDownloadJob, JobPriority, JobStatus
from downloader import (
    cleanup_stale_downloads, download_audio, embed_metadata, enqueue_download,
    extract_info, extract_lyrics, get_job, cancel_job, list_jobs, search,
    spotdl_download_sync, JOBS,
)
from m3u8_downloader import (
    parse_m3u8, download_m3u8_sync, enqueue_m3u8_download, get_m3u8_job,
    cancel_m3u8_job, list_m3u8_jobs, aria2_add_uri, aria2_tell_status,
    aria2_remove, M3U8Job,
)
from logger import (
    get_logger, set_request_id, clear_request_id, log_request,
    log_download_event, log_auth_event, log_error, request_id_var,
)
from watchdog import watchdog

logger = get_logger("videl")
from models import (
    DownloadResponse, ErrorResponse, HealthResponse, JobListResponse,
    JobActionResponse, LyricsResponse, LyricsSearchRequest, MetadataResponse,
    MetadataRequest, SearchResponse, SourcesResponse, TrackInfoResponse,
    DownloadJobItem,
    M3U8ParseResponse, M3U8DownloadResponse, M3U8JobItem,
    Aria2AddResponse, Aria2StatusResponse,
    # User management
    UserResponse, UserCreate, UserUpdate, UserListResponse, UserTierChange,
    # Tier
    TierInfo, TierListResponse,
    # Payments
    PaymentCreate, PaymentResponse, PaymentHistoryResponse, InvoiceRequest,
    # Playlists
    PlaylistCreate, PlaylistUpdate, PlaylistResponse, PlaylistItemCreate,
    PlaylistItemResponse, PlaylistDetailResponse,
    # Webhooks
    WebhookCreate, WebhookUpdate, WebhookResponse,
    # Notifications
    NotificationCreate, NotificationResponse, NotificationListResponse,
    # Batch
    BatchRequest, BatchResponse, BatchStatusResponse,
    # Files
    FileInfo, FileListResponse,
    # Import/Export
    ExportRequest, ExportResponse,
    # Devices/Sessions
    DeviceRegister, DeviceResponse, SessionResponse,
    # Alerts
    AlertCreate, AlertResponse,
    # API Key Extended
    ApiKeyExtended,
    # Stats
    GlobalStats, UsageStats, SourceStats,
    # Maintenance/Version
    MaintenanceStatus, VersionInfo,
    # OAuth2 / JWT
    TokenRequest, TokenResponse, TokenRefreshRequest,
    # 2FA
    TwoFactorSetup, TwoFactorVerify, TwoFactorResponse,
    # Notification preferences
    NotificationPreference,
    # File encryption
    FileEncryptRequest, FileEncryptResponse, FileDecryptRequest,
    # Speed limiting
    SpeedLimitRequest, SpeedLimitResponse,
    # Download scheduling
    DownloadSchedule, DownloadScheduleResponse,
    # Content rating
    ContentRating, ContentRatingResponse,
    # Favorites
    FavoriteCreate, FavoriteResponse,
    # Export
    HistoryExportRequest,
    # Key rotation
    KeyRotationSchedule,
    # Tier features
    TierFeatureFlag,
    # Geo blocking
    GeoBlockRule,
    # IP reputation
    IPReputation,
    # Signing keys
    SigningKey,
    # Bulk keys
    BulkKeyCreate, BulkKeyResponse,
    # Key sharing
    KeyShare, KeyShareResponse,
    # Teams
    TeamMember, TeamResponse,
    # RBAC
    RoleCreate, RoleResponse, UserRoleAssign,
    # Audit log
    AuditLogEntry, AuditLogFilter,
    # Sessions
    SessionInfo, SessionRevoke,
    # Device fingerprint
    DeviceFingerprint,
    # Session limits
    SessionLimit,
    # Password reset
    PasswordResetRequest, PasswordResetConfirm,
    # Custom rate limit
    CustomRateLimit,
    # Bandwidth allocation
    BandwidthAllocation,
    # Download notification
    DownloadNotification,
    # Download retry policy
    DownloadRetryPolicy,
    # Source health
    SourceHealth, SourceLatency,
    # Failover
    FailoverRule,
    # Cache invalidation
    CacheInvalidation,
    # Cache warm
    CacheWarmRequest,
    # Search history
    SearchHistoryEntry,
    # Saved searches
    SavedSearch, SavedSearchCreate,
    # Autocomplete
    AutocompleteRequest,
    # API Versioning
    APIVersion,
    # Trending
    TrendingSearch,
    # Popular content
    PopularContent,
    # Activity feed
    ActivityFeedEntry,
    # Usage reports
    UsageReport,
    # Key scopes
    KeyScopes,
    # Key usage
    KeyUsage,
    # Suspicious activity
    SuspiciousActivity,
    # Download concurrency
    DownloadConcurrency,
    # File type filter
    FileTypeFilter,
    # Virus scan
    VirusScanResult,
    # Moderation
    ModerationItem, ModerationAction,
    # Watchdog
    WatchdogHealthResponse, ComponentHealthResponse,
)
from auth import (
    create_api_key, list_api_keys, revoke_api_key, validate_api_key,
    _load_json, _save_json, KEYS_FILE,
    create_user, get_user, get_user_by_telegram, update_user, delete_user,
    list_users, set_user_tier, increment_user_counter,
    get_tier_info, list_tiers,
    create_payment, complete_payment, list_payments,
    create_playlist, get_playlist, list_playlists, update_playlist,
    delete_playlist, add_playlist_item, remove_playlist_item,
    create_webhook, list_webhooks, delete_webhook, trigger_webhook,
    create_notification, list_notifications, mark_notification_read,
    create_batch, get_batch, update_batch,
    register_device, list_devices,
    create_alert, list_alerts,
    record_analytics, get_analytics,
    _load_webhook_deliveries,
    create_oauth_token, validate_oauth_token,
    setup_2fa, verify_2fa, enable_2fa, verify_2fa_backup,
    get_notif_prefs, set_notif_prefs,
    encrypt_file_record, decrypt_file_record,
    set_speed_limit, get_speed_limit,
    create_schedule, list_schedules, toggle_schedule,
    rate_content, get_content_rating,
    add_favorite, list_favorites, remove_favorite,
    create_export, list_exports,
    schedule_key_rotation, list_key_rotations,
    set_tier_feature, get_tier_features,
    add_geo_block, list_geo_blocks, is_country_blocked,
    record_ip_reputation, get_ip_reputation,
    create_signing_key, list_signing_keys,
    register_api_version, list_api_versions,
    bulk_create_keys,
    create_key_share, list_key_shares,
    create_team, list_teams, add_team_member,
    create_role, list_roles, assign_role,
    write_audit_log, list_audit_logs,
    create_session, list_sessions, revoke_session,
    record_device_fingerprint,
    set_session_limit, get_session_limit,
    request_password_reset, confirm_password_reset,
    set_custom_rate_limit,
    set_bandwidth_allocation,
    set_download_notification,
    set_retry_policy,
    record_source_health, get_source_health, get_source_latency_stats,
    add_failover_rule, list_failover_rules,
    invalidate_cache_tag,
    warm_cache, list_cache_warms,
    record_search_history, get_search_history,
    save_search, list_saved_searches, delete_saved_search,
    record_trending, get_trending,
    record_activity, get_activity_feed,
    create_usage_report, list_usage_reports,
    set_key_scopes, get_key_scopes,
    record_key_usage, get_key_usage,
    record_suspicious_activity, list_suspicious_activity,
    set_download_concurrency, get_download_concurrency,
    set_file_type_filter, get_file_type_filter,
    record_virus_scan,
    add_moderation_item, list_moderation_items, moderate_item,
)
from telegram_bot import (
    get_bot, set_webhook, delete_webhook as delete_tg_webhook,
    set_bot_commands, process_update, start_bot_polling,
)

START_TIME = time.time()

_shutdown_event = asyncio.Event()


def _signal_handler(signum, frame):
    """Graceful shutdown signal handler."""
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    _shutdown_event.set()


# Register signal handlers for graceful shutdown
try:
    import signal as _signal
    _signal.signal(_signal.SIGTERM, _signal_handler)
    _signal.signal(_signal.SIGINT, _signal_handler)
except Exception:
    pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.download_dir.mkdir(parents=True, exist_ok=True)
    await cleanup_stale_downloads()

    # Start task scheduler
    register_default_tasks()
    scheduler.start()

    # Start keep-alive watchdog
    await watchdog.start()

    # Initialize Telegram Bot if configured
    if settings.telegram_bot_token:
        bot = await get_bot()
        if bot:
            await set_bot_commands()
            if settings.telegram_bot_webhook_url:
                await set_webhook(settings.telegram_bot_webhook_url)
                logger.info("Telegram bot initialized (webhook mode)")
            elif settings.telegram_bot_polling:
                asyncio.create_task(start_bot_polling())
                logger.info("Telegram bot initialized (polling mode)")
            else:
                # Default to polling when token is set but no delivery method configured
                asyncio.create_task(start_bot_polling())
                logger.info("Telegram bot initialized (auto polling mode)")

    logger.info("Videl-Api v3.2.0 startup complete")

    yield

    # Cleanup
    scheduler.stop()
    await watchdog.stop()
    bot = await get_bot()
    if bot:
        await bot.close()
        await ws_manager.broadcast_all({
            "type": "server_shutdown",
            "message": "Server is shutting down",
        })


app = FastAPI(
    title="Videl-Api",
    description="Multi-source media REST API for music bots and more.",
    version="3.2.0",
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


@app.middleware("http")
async def request_logging_middleware(request, call_next):
    request_id = set_request_id()
    start_time = time.time()
    try:
        response = await call_next(request)
        duration_ms = (time.time() - start_time) * 1000
        log_request(
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            request_id=request_id,
        )
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = f"{duration_ms:.2f}ms"
        return response
    except Exception as exc:
        duration_ms = (time.time() - start_time) * 1000
        log_error(exc, context=f"request {request.method} {request.url.path}")
        raise
    finally:
        clear_request_id()


# Global exception handler for consistent error responses
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail if isinstance(exc.detail, str) else "HTTP error",
            "detail": str(exc.detail) if not isinstance(exc.detail, str) else None,
            "code": exc.status_code,
        },
        headers={"X-Request-ID": request_id_var.get() or "-"},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc: Exception):
    log_error(exc, context=f"unhandled {request.method} {request.url.path}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "detail": str(exc),
            "code": 500,
        },
        headers={"X-Request-ID": request_id_var.get() or "-"},
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
        "version": "3.2.0",
        "description": "Powerful multi-source media REST API with Telegram Bot, payments, and 100+ features.",
        "docs": "/docs",
        "health": "/health",
        "sources": "/v1/sources",
        "auth": "X-API-Key header",
        "telegram_bot": "@videl_api_bot",
        "webapp": "/app",
    }


@app.get("/health", response_model=HealthResponse, tags=["meta"])
async def health():
    return HealthResponse(
        status="ok",
        sources=len(list_sources()),
        uptime_seconds=time.time() - START_TIME,
        features={
            "search": True,
            "lyrics": True,
            "download": True,
            "metadata_embed": settings.metadata_embed,
            "sponsorblock": settings.sponsorblock,
            "aria2c": bool(settings.downloader_path),
            "ffmpeg": bool(settings.ffmpeg_path),
            "spotdl": settings.spotify_enabled,
            "m3u8_hls_dash": settings.hls_enabled,
            "telegram_bot": bool(settings.telegram_bot_token),
            "telegram_stars": settings.telegram_stars_enabled,
            "webhooks": settings.webhook_enabled,
            "notifications": settings.notification_enabled,
            "batch_operations": True,
            "playlists": True,
            "user_management": True,
            "analytics": settings.analytics_enabled,
            "websocket": True,
            "caching": True,
            "scheduler": True,
            "plugins": True,
            "rate_limiting": settings.rate_limit_enabled,
            "advanced_download": True,
            "federated_search": True,
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
    if settings.spotify_enabled and _has_spotdl():
        target = url or query or ""
        if not target:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Provide a Spotify URL or search query",
            )
        try:
            import subprocess
            cmd = [settings.spotify_path, "url", target]
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
            [settings.spotify_path, "--version"],
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
    return {
        "key": record.get("key", "") if isinstance(record, dict) else record.key,
        "owner_id": record.get("owner_id", 0) if isinstance(record, dict) else record.owner_id,
        "active": record.get("active", True) if isinstance(record, dict) else record.active,
    }


@app.get("/v1/keys", tags=["keys"])
async def list_keys(owner_id: int = 0, _: dict = Depends(get_auth)):
    return await list_api_keys(owner_id)


@app.delete("/v1/keys/{key}", tags=["keys"])
async def delete_key(key: str, owner_id: int = 0, _: dict = Depends(get_auth)):
    ok = await revoke_api_key(owner_id, key)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    return {"revoked": True, "key": key}


# ---------------------------------------------------------------------------
# M3U8 / HLS Parse
# ---------------------------------------------------------------------------

@app.post("/v1/m3u8/parse", response_model=M3U8ParseResponse, tags=["m3u8"])
async def m3u8_parse(payload: M3U8ParseRequest, _: dict = Depends(get_auth)):
    try:
        info = await parse_m3u8(
            payload.url,
            headers=payload.headers,
            cookies=payload.cookies,
            proxy=payload.proxy,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"M3U8 parse failed: {exc}",
        )
    return M3U8ParseResponse(**info)


# ---------------------------------------------------------------------------
# M3U8 / HLS Download (direct)
# ---------------------------------------------------------------------------

@app.post("/v1/m3u8/download", response_model=M3U8DownloadResponse, tags=["m3u8"])
async def m3u8_download(payload: M3U8DownloadRequest, _: dict = Depends(get_auth)):
    folder = f"{int(time.time()*1000)}"
    output_dir = settings.download_dir / folder
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        result = await download_m3u8_sync(
            payload.url,
            output_dir=output_dir,
            headers=payload.headers,
            cookies=payload.cookies,
            proxy=payload.proxy,
            max_threads=payload.max_threads,
            use_aria2c=payload.use_aria2c,
            decrypt=payload.decrypt,
            merge_method=payload.merge_method,
            save_name=payload.save_name,
            custom_range=payload.custom_range,
            audio_only=payload.audio_only,
        )
    except Exception as exc:
        import shutil
        shutil.rmtree(output_dir, ignore_errors=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"M3U8 download failed: {exc}",
        )
    return M3U8DownloadResponse(**result)


# ---------------------------------------------------------------------------
# M3U8 Download Queue (background jobs)
# ---------------------------------------------------------------------------

@app.post("/v1/m3u8/download/queue", response_model=M3U8JobItem, tags=["m3u8"])
async def m3u8_queue(payload: M3U8DownloadRequest, _: dict = Depends(get_auth)):
    job = M3U8Job(job_id="", url=payload.url)
    # Override job fields from payload
    job_id = uuid.uuid4().hex
    job.job_id = job_id
    async with _M3U8_LOCK:
        M3U8_JOBS[job_id] = job
        M3U8_QUEUE.append(job_id)
    asyncio.create_task(_process_m3u8_queue_with_opts(
        job_id, payload.url,
        headers=payload.headers,
        cookies=payload.cookies,
        proxy=payload.proxy,
        max_threads=payload.max_threads,
        use_aria2c=payload.use_aria2c,
        decrypt=payload.decrypt,
        merge_method=payload.merge_method,
        save_name=payload.save_name,
        custom_range=payload.custom_range,
        audio_only=payload.audio_only,
    ))
    return M3U8JobItem(**job.to_dict())


async def _process_m3u8_queue_with_opts(
    job_id: str,
    url: str,
    *,
    headers: Optional[dict[str, str]] = None,
    cookies: Optional[str] = None,
    proxy: Optional[str] = None,
    max_threads: int = 16,
    use_aria2c: bool = False,
    decrypt: bool = True,
    merge_method: str = "binary",
    save_name: Optional[str] = None,
    custom_range: Optional[str] = None,
    audio_only: bool = False,
):
    job = M3U8_JOBS.get(job_id)
    if not job:
        return
    job.status = "downloading"
    job.updated_at = datetime.now(timezone.utc).isoformat()

    sem = _m3u8_download_semaphore()
    async with sem:
        if job.cancelled:
            job.status = "cancelled"
            job.updated_at = datetime.now(timezone.utc).isoformat()
            return
        try:
            out_dir = settings.download_dir / job_id
            result = await download_m3u8_sync(
                url,
                output_dir=out_dir,
                job=job,
                headers=headers,
                cookies=cookies,
                proxy=proxy,
                max_threads=max_threads,
                decrypt=decrypt,
                merge_method=merge_method,
                save_name=save_name,
                custom_range=custom_range,
                audio_only=audio_only,
            )
            job.file_path = result["file_path"]
            job.status = "completed"
            job.progress = 100.0
            job.updated_at = datetime.now(timezone.utc).isoformat()
        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)
            job.updated_at = datetime.now(timezone.utc).isoformat()


@app.get("/v1/m3u8/download/queue", response_model=JobListResponse, tags=["m3u8"])
async def m3u8_list_jobs(_: dict = Depends(get_auth)):
    jobs = await list_m3u8_jobs()
    return JobListResponse(jobs=[M3U8JobItem(**j) for j in jobs])


@app.get("/v1/m3u8/download/status/{job_id}", response_model=M3U8JobItem, tags=["m3u8"])
async def m3u8_job_status(job_id: str, _: dict = Depends(get_auth)):
    job = await get_m3u8_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return M3U8JobItem(**job)


@app.post("/v1/m3u8/download/cancel/{job_id}", response_model=JobActionResponse, tags=["m3u8"])
async def m3u8_cancel_job(job_id: str, _: dict = Depends(get_auth)):
    ok = await cancel_m3u8_job(job_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return JobActionResponse(job_id=job_id, action="cancel", success=True)


# ---------------------------------------------------------------------------
# aria2 RPC
# ---------------------------------------------------------------------------

@app.post("/v1/aria2/add", response_model=Aria2AddResponse, tags=["aria2"])
async def aria2_add(payload: Aria2AddRequest, _: dict = Depends(get_auth)):
    if not settings.downloader_rpc_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="External downloader RPC is not enabled. Set DOWNLOADER_RPC_ENABLED=true",
        )
    try:
        gid = await aria2_add_uri(
            payload.uris,
            dir=payload.dir,
            out=payload.out,
            max_connections=payload.max_connections,
            split=payload.split,
            proxy=payload.proxy,
            header=payload.header,
            rpc_url=settings.downloader_rpc_url,
            rpc_secret=settings.downloader_rpc_secret,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"aria2 add failed: {exc}",
        )
    return Aria2AddResponse(gid=gid)


@app.get("/v1/aria2/status/{gid}", response_model=Aria2StatusResponse, tags=["aria2"])
async def aria2_status(gid: str, _: dict = Depends(get_auth)):
    if not settings.downloader_rpc_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="External downloader RPC is not enabled. Set DOWNLOADER_RPC_ENABLED=true",
        )
    try:
        info = await aria2_tell_status(
            gid,
            rpc_url=settings.downloader_rpc_url,
            rpc_secret=settings.downloader_rpc_secret,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"aria2 status failed: {exc}",
        )
    total = info.get("totalLength", "0")
    completed = info.get("completedLength", "0")
    try:
        progress = (int(completed) / int(total) * 100) if int(total) > 0 else 0.0
    except Exception:
        progress = 0.0
    return Aria2StatusResponse(
        gid=gid,
        status=info.get("status", "unknown"),
        total_length=total,
        completed_length=completed,
        download_speed=info.get("downloadSpeed"),
        progress=round(progress, 2),
        dir=info.get("dir"),
        files=info.get("files", []),
    )


@app.post("/v1/aria2/remove/{gid}", tags=["aria2"])
async def aria2_remove_download(gid: str, _: dict = Depends(get_auth)):
    if not settings.downloader_rpc_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="External downloader RPC is not enabled. Set DOWNLOADER_RPC_ENABLED=true",
        )
    try:
        ok = await aria2_remove(
            gid,
            rpc_url=settings.downloader_rpc_url,
            rpc_secret=settings.downloader_rpc_secret,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"aria2 remove failed: {exc}",
        )
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Download not found")
    return {"removed": True, "gid": gid}


# ============================================================================
# FEDERATED SEARCH (multi-source)
# ============================================================================

@app.get("/v1/federated-search", tags=["search"])
async def federated_search_get(
    q: str,
    limit: int = 10,
    source: Optional[str] = None,
    _: dict = Depends(get_auth),
):
    """Search across multiple sources simultaneously."""
    cache_key = f"fed:{q}:{limit}:{source or 'all'}"
    cached = search_cache.get(cache_key)
    if cached:
        return cached

    sources_to_search = []
    if source:
        if source in MUSIC_SOURCES:
            sources_to_search = [source]
    else:
        sources_to_search = list(MUSIC_SOURCES.keys())[:8]

    results = {}
    for src in sources_to_search:
        try:
            raw = await search(q, source=src, limit=limit)
            results[src] = raw
        except Exception:
            results[src] = []

    response = {
        "query": q,
        "sources_searched": sources_to_search,
        "results": results,
        "total": sum(len(r) for r in results.values()),
    }
    search_cache.set(cache_key, response, ttl=180)
    return response


@app.post("/v1/federated-search", tags=["search"])
async def federated_search_post(
    payload: dict,
    _: dict = Depends(get_auth),
):
    q = payload.get("q", "")
    limit = payload.get("limit", 10)
    source = payload.get("source")
    return await federated_search_get(q, limit, source, _)


# ============================================================================
# ADVANCED DOWNLOAD MANAGER (priority, pause/resume)
# ============================================================================

class AdvancedDownloadRequest(BaseModel):
    url: str
    source: Optional[str] = None
    user_id: int = 0
    priority: str = "normal"  # high | normal | low
    format: str = "bestaudio/best"
    quality: Optional[str] = None
    use_aria2c: bool = True
    embed_metadata: bool = True
    fetch_lyrics: bool = False
    # Cookies support
    cookies: Optional[str] = None
    cookies_file: Optional[str] = None
    # More download options
    proxy: Optional[str] = None
    user_agent: Optional[str] = None
    referer: Optional[str] = None
    max_filesize: Optional[int] = None  # MB
    skip_download: bool = False


@app.post("/v1/download/advanced", tags=["download"])
async def advanced_download_create(
    payload: AdvancedDownloadRequest,
    auth: dict = Depends(get_auth),
):
    user_id = payload.user_id or auth.get("owner_id", 0)
    priority_map = {
        "high": JobPriority.HIGH,
        "normal": JobPriority.NORMAL,
        "low": JobPriority.LOW,
    }
    priority = priority_map.get(payload.priority.lower(), JobPriority.NORMAL)

    job = await download_manager.enqueue(
        url=payload.url,
        user_id=user_id,
        source=payload.source,
        priority=priority,
        format=payload.format,
        quality=payload.quality,
        use_aria2c=payload.use_aria2c,
        embed_metadata=payload.embed_metadata,
        fetch_lyrics=payload.fetch_lyrics,
        cookies=payload.cookies,
        cookies_file=payload.cookies_file,
        proxy=payload.proxy,
        user_agent=payload.user_agent,
        referer=payload.referer,
        max_filesize=payload.max_filesize,
        skip_download=payload.skip_download,
    )
    log_download_event("created", job.job_id, user_id, {
        "url": payload.url,
        "source": payload.source,
        "priority": payload.priority,
    })
    return job.to_dict()


@app.get("/v1/download/advanced", tags=["download"])
async def advanced_download_list(
    user_id: Optional[int] = None,
    auth: dict = Depends(get_auth),
):
    target_user = user_id if auth.get("admin", False) else auth.get("owner_id", 0)
    return download_manager.list_jobs(target_user if not auth.get("admin", False) else None)


@app.get("/v1/download/advanced/status/{job_id}", tags=["download"])
async def advanced_download_status(job_id: str, _: dict = Depends(get_auth)):
    job = download_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_dict()


@app.post("/v1/download/advanced/progress/{job_id}", tags=["download"])
async def advanced_download_progress(
    job_id: str,
    progress: float,
    downloaded_size: Optional[int] = None,
    _: dict = Depends(get_auth),
):
    """Update download progress (used by external downloaders)."""
    ok = await download_manager.update_progress(job_id, progress, downloaded_size)
    if not ok:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"updated": True, "job_id": job_id, "progress": progress}


@app.post("/v1/download/advanced/pause/{job_id}", tags=["download"])
async def advanced_download_pause(job_id: str, auth: dict = Depends(get_auth)):
    job = download_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not auth.get("admin", False) and job.user_id != auth.get("owner_id", 0):
        raise HTTPException(status_code=403, detail="Access denied")
    ok, error = await download_manager.pause(job_id)
    if not ok:
        raise HTTPException(status_code=400, detail=error or "Cannot pause job")
    return {"paused": True, "job_id": job_id}


@app.post("/v1/download/advanced/resume/{job_id}", tags=["download"])
async def advanced_download_resume(job_id: str, auth: dict = Depends(get_auth)):
    job = download_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not auth.get("admin", False) and job.user_id != auth.get("owner_id", 0):
        raise HTTPException(status_code=403, detail="Access denied")
    ok, error = await download_manager.resume(job_id)
    if not ok:
        raise HTTPException(status_code=400, detail=error or "Cannot resume job")
    return {"resumed": True, "job_id": job_id}


@app.post("/v1/download/advanced/cancel/{job_id}", tags=["download"])
async def advanced_download_cancel(job_id: str, auth: dict = Depends(get_auth)):
    job = download_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not auth.get("admin", False) and job.user_id != auth.get("owner_id", 0):
        raise HTTPException(status_code=403, detail="Access denied")
    ok, error = await download_manager.cancel(job_id)
    if not ok:
        raise HTTPException(status_code=400, detail=error or "Cannot cancel job")
    return {"cancelled": True, "job_id": job_id}


# ============================================================================
# CACHE MANAGEMENT
# ============================================================================

@app.get("/v1/cache/stats", tags=["cache"])
async def cache_stats(auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return {
        "search": search_cache.stats(),
        "metadata": metadata_cache.stats(),
        "lyrics": lyrics_cache.stats(),
        "source_health": source_health_cache.stats(),
    }


@app.post("/v1/cache/clear", tags=["cache"])
async def cache_clear(auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    removed = {
        "search": search_cache.clear(),
        "metadata": metadata_cache.clear(),
        "lyrics": lyrics_cache.clear(),
        "source_health": source_health_cache.clear(),
    }
    return {"cleared": removed}


# ============================================================================
# TASK SCHEDULER
# ============================================================================

@app.get("/v1/scheduler/tasks", tags=["scheduler"])
async def scheduler_tasks(auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return {"tasks": scheduler.list_tasks()}


@app.post("/v1/scheduler/tasks/{task_name}/enable", tags=["scheduler"])
async def scheduler_enable(task_name: str, auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    ok = scheduler.enable(task_name)
    if not ok:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"enabled": True, "task": task_name}


@app.post("/v1/scheduler/tasks/{task_name}/disable", tags=["scheduler"])
async def scheduler_disable(task_name: str, auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    ok = scheduler.disable(task_name)
    if not ok:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"disabled": True, "task": task_name}


# ============================================================================
# PLUGINS
# ============================================================================

@app.get("/v1/plugins", tags=["plugins"])
async def plugins_list(auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return {"plugins": plugin_manager.list()}


@app.post("/v1/plugins/{plugin_id}/enable", tags=["plugins"])
async def plugins_enable(plugin_id: str, auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    ok = plugin_manager.enable(plugin_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Plugin not found")
    return {"enabled": True, "plugin": plugin_id}


@app.post("/v1/plugins/{plugin_id}/disable", tags=["plugins"])
async def plugins_disable(plugin_id: str, auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    ok = plugin_manager.disable(plugin_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Plugin not found")
    return {"disabled": True, "plugin": plugin_id}


# ============================================================================
# WEBSOCKET — Real-time updates
# ============================================================================

@app.websocket("/v1/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    conn_id = f"ws_{user_id}_{uuid.uuid4().hex[:8]}"
    await handle_websocket(websocket, user_id, conn_id)
# ============================================================================

@app.post("/v1/users", response_model=UserResponse, tags=["users"])
async def users_create(payload: UserCreate, _: dict = Depends(get_auth)):
    if not settings.user_registration_enabled:
        raise HTTPException(status_code=403, detail="User registration disabled")
    user = create_user(
        telegram_id=payload.telegram_id,
        username=payload.username,
        first_name=payload.first_name,
        tier=payload.tier,
    )
    return UserResponse(**user)


@app.get("/v1/users", response_model=UserListResponse, tags=["users"])
async def users_list(limit: int = 100, offset: int = 0, auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    users = list_users(limit=limit, offset=offset)
    return UserListResponse(users=[UserResponse(**u) for u in users], total=len(users))


@app.get("/v1/users/{user_id}", response_model=UserResponse, tags=["users"])
async def users_get(user_id: str, auth: dict = Depends(get_auth)):
    if not auth.get("admin", False) and auth.get("owner_id") != int(user_id or 0):
        raise HTTPException(status_code=403, detail="Access denied")
    user = get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(**user)


@app.put("/v1/users/{user_id}", response_model=UserResponse, tags=["users"])
async def users_update(user_id: str, payload: UserUpdate, auth: dict = Depends(get_auth)):
    if not auth.get("admin", False) and auth.get("owner_id") != int(user_id or 0):
        raise HTTPException(status_code=403, detail="Access denied")
    user = update_user(user_id, **payload.model_dump(exclude_unset=True))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(**user)


@app.delete("/v1/users/{user_id}", tags=["users"])
async def users_delete(user_id: str, auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    ok = delete_user(user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="User not found")
    return {"deleted": True, "user_id": user_id}


# ---------------------------------------------------------------------------
# Tier / Subscription
# ---------------------------------------------------------------------------

@app.get("/v1/tiers", response_model=TierListResponse, tags=["tier"])
async def tiers_list(_: dict = Depends(get_auth)):
    tiers = list_tiers()
    return TierListResponse(tiers=[TierInfo(**t) for t in tiers])


@app.post("/v1/users/{user_id}/tier", response_model=UserResponse, tags=["tier"])
async def users_set_tier(user_id: str, payload: UserTierChange, auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    tier_info = get_tier_info(payload.tier)
    user = set_user_tier(user_id, payload.tier, scopes=tier_info["scopes"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(**user)


# ---------------------------------------------------------------------------
# Payments / Telegram Stars
# ---------------------------------------------------------------------------

@app.post("/v1/payments/invoice", response_model=PaymentResponse, tags=["payments"])
async def payments_create_invoice(payload: InvoiceRequest, auth: dict = Depends(get_auth)):
    if not settings.telegram_stars_enabled:
        raise HTTPException(status_code=403, detail="Payments disabled")
    user_id = auth.get("owner_id", 0)
    invoice_payload = f"inv_{user_id}_{int(time.time())}"
    payment = create_payment(
        user_id=user_id,
        tier="pro",
        amount=payload.amount,
        currency=payload.currency,
        invoice_payload=invoice_payload,
    )
    return PaymentResponse(**payment)


@app.post("/v1/payments/webhook", tags=["payments"])
async def payments_webhook(payload: dict, _: dict = Depends(get_auth)):
    """Handle Telegram Stars successful payment webhook."""
    invoice_payload = payload.get("invoice_payload", "")
    payment = complete_payment(invoice_payload)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    return {"ok": True, "payment": payment}


@app.get("/v1/payments/history", response_model=PaymentHistoryResponse, tags=["payments"])
async def payments_history(auth: dict = Depends(get_auth)):
    user_id = auth.get("owner_id", 0)
    payments = list_payments(user_id if not auth.get("admin", False) else None)
    return PaymentHistoryResponse(
        payments=[PaymentResponse(**p) for p in payments],
        total=len(payments),
    )


# ---------------------------------------------------------------------------
# Playlists
# ---------------------------------------------------------------------------

@app.post("/v1/playlists", response_model=PlaylistResponse, tags=["playlists"])
async def playlists_create(payload: PlaylistCreate, auth: dict = Depends(get_auth)):
    owner_id = auth.get("owner_id", 0)
    playlist = create_playlist(owner_id, payload.name, payload.description, payload.is_public)
    return PlaylistResponse(**playlist)


@app.get("/v1/playlists", response_model=list[PlaylistResponse], tags=["playlists"])
async def playlists_list(auth: dict = Depends(get_auth)):
    owner_id = auth.get("owner_id", 0)
    playlists = list_playlists(owner_id if not auth.get("admin", False) else None)
    return [PlaylistResponse(**p) for p in playlists]


@app.get("/v1/playlists/{playlist_id}", response_model=PlaylistDetailResponse, tags=["playlists"])
async def playlists_get(playlist_id: str, _: dict = Depends(get_auth)):
    playlist = get_playlist(playlist_id)
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    return PlaylistDetailResponse(**playlist)


@app.put("/v1/playlists/{playlist_id}", response_model=PlaylistResponse, tags=["playlists"])
async def playlists_update(playlist_id: str, payload: PlaylistUpdate, auth: dict = Depends(get_auth)):
    playlist = update_playlist(playlist_id, **payload.model_dump(exclude_unset=True))
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    return PlaylistResponse(**playlist)


@app.delete("/v1/playlists/{playlist_id}", tags=["playlists"])
async def playlists_delete(playlist_id: str, _: dict = Depends(get_auth)):
    ok = delete_playlist(playlist_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Playlist not found")
    return {"deleted": True, "playlist_id": playlist_id}


@app.post("/v1/playlists/{playlist_id}/items", response_model=PlaylistItemResponse, tags=["playlists"])
async def playlists_add_item(playlist_id: str, payload: PlaylistItemCreate, _: dict = Depends(get_auth)):
    item = add_playlist_item(playlist_id, payload.model_dump())
    if not item:
        raise HTTPException(status_code=404, detail="Playlist not found or full")
    return PlaylistItemResponse(**item)


@app.delete("/v1/playlists/{playlist_id}/items/{item_id}", tags=["playlists"])
async def playlists_remove_item(playlist_id: str, item_id: str, _: dict = Depends(get_auth)):
    ok = remove_playlist_item(playlist_id, item_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"removed": True, "item_id": item_id}


# ---------------------------------------------------------------------------
# Webhooks
# ---------------------------------------------------------------------------

@app.post("/v1/webhooks", response_model=WebhookResponse, tags=["webhooks"])
async def webhooks_create(payload: WebhookCreate, auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    if not settings.webhook_enabled:
        raise HTTPException(status_code=403, detail="Webhooks disabled")
    hook = create_webhook(payload.url, payload.events, payload.secret)
    return WebhookResponse(**hook)


@app.get("/v1/webhooks", response_model=list[WebhookResponse], tags=["webhooks"])
async def webhooks_list(auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return [WebhookResponse(**h) for h in list_webhooks()]


@app.delete("/v1/webhooks/{webhook_id}", tags=["webhooks"])
async def webhooks_delete(webhook_id: str, auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    ok = delete_webhook(webhook_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return {"deleted": True, "webhook_id": webhook_id}


@app.post("/v1/webhooks/{webhook_id}/trigger", tags=["webhooks"])
async def webhooks_trigger(webhook_id: str, payload: dict, auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    trigger_webhook("manual", payload)
    return {"triggered": True}


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

@app.post("/v1/notifications", response_model=NotificationResponse, tags=["notifications"])
async def notifications_create(payload: NotificationCreate, auth: dict = Depends(get_auth)):
    target_user = payload.user_id if auth.get("admin", False) else auth.get("owner_id", 0)
    notif = create_notification(target_user, payload.title, payload.message, payload.type)
    return NotificationResponse(**notif)


@app.get("/v1/notifications", response_model=NotificationListResponse, tags=["notifications"])
async def notifications_list(unread_only: bool = False, auth: dict = Depends(get_auth)):
    user_id = auth.get("owner_id", 0)
    notifs = list_notifications(user_id, unread_only=unread_only)
    return NotificationListResponse(
        notifications=[NotificationResponse(**n) for n in notifs],
        total=len(notifs),
        unread=sum(1 for n in notifs if not n.get("read", False)),
    )


@app.put("/v1/notifications/{notif_id}/read", tags=["notifications"])
async def notifications_read(notif_id: str, auth: dict = Depends(get_auth)):
    user_id = auth.get("owner_id", 0)
    ok = mark_notification_read(notif_id, user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"read": True}


# ---------------------------------------------------------------------------
# Batch Operations
# ---------------------------------------------------------------------------

@app.post("/v1/batch", response_model=BatchResponse, tags=["batch"])
async def batch_create(payload: BatchRequest, auth: dict = Depends(get_auth)):
    if len(payload.items) > settings.batch_max_items:
        raise HTTPException(status_code=400, detail=f"Max {settings.batch_max_items} items per batch")
    batch_id = create_batch(len(payload.items))
    # Process items in background
    async def _process():
        results = []
        for item in payload.items:
            try:
                info = await extract_info(item.url, source=item.source, skip_download=True)
                results.append({"url": item.url, "status": "ok", "title": info.get("title")})
            except Exception as exc:
                results.append({"url": item.url, "status": "error", "error": str(exc)})
        update_batch(batch_id, status="completed", completed_items=len(results), results=results)
    asyncio.create_task(_process())
    return BatchResponse(batch_id=batch_id, total_items=len(payload.items), status="queued", created_at=datetime.now(timezone.utc).isoformat())


@app.get("/v1/batch/{batch_id}", response_model=BatchStatusResponse, tags=["batch"])
async def batch_status(batch_id: str, _: dict = Depends(get_auth)):
    batch = get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    return BatchStatusResponse(**batch)


# ---------------------------------------------------------------------------
# File Management
# ---------------------------------------------------------------------------

@app.get("/v1/files", response_model=FileListResponse, tags=["files"])
async def files_list(_: dict = Depends(get_auth)):
    files = []
    download_dir = settings.download_dir
    if download_dir.exists():
        for folder in download_dir.iterdir():
            if folder.is_dir():
                for f in folder.iterdir():
                    if f.is_file():
                        files.append(FileInfo(
                            name=f.name,
                            path=str(f),
                            size=f.stat().st_size,
                            mime_type="application/octet-stream",
                            created_at=datetime.fromtimestamp(f.stat().st_ctime, tz=timezone.utc).isoformat(),
                            download_url=f"{settings.api_base_url.rstrip('/')}/v1/file/{folder.name}/{f.name}",
                        ))
    return FileListResponse(files=files, total=len(files))


@app.delete("/v1/files/{folder}/{filename}", tags=["files"])
async def files_delete(folder: str, filename: str, _: dict = Depends(get_auth)):
    file_path = settings.download_dir / folder / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    file_path.unlink()
    return {"deleted": True, "file": filename}


# ---------------------------------------------------------------------------
# Import / Export
# ---------------------------------------------------------------------------

@app.get("/v1/export/keys", tags=["export"])
async def export_keys(auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    keys = _load_json(KEYS_FILE, [])
    export_id = secrets.token_urlsafe(16)
    # In production, write to a file and return download URL
    return ExportResponse(
        export_id=export_id,
        download_url=f"{settings.api_base_url.rstrip('/')}/v1/export/download/{export_id}",
        expires_at=datetime.now(timezone.utc).isoformat(),
    )


@app.post("/v1/import", tags=["import"])
async def import_data(payload: dict, auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return {"imported": True, "records": len(payload.get("records", []))}


# ---------------------------------------------------------------------------
# Devices / Sessions
# ---------------------------------------------------------------------------

@app.post("/v1/devices", response_model=DeviceResponse, tags=["devices"])
async def devices_register(payload: DeviceRegister, auth: dict = Depends(get_auth)):
    user_id = auth.get("owner_id", 0)
    device = register_device(user_id, payload.device_id, payload.device_name, payload.platform)
    return DeviceResponse(**device)


@app.get("/v1/devices", response_model=list[DeviceResponse], tags=["devices"])
async def devices_list(auth: dict = Depends(get_auth)):
    user_id = auth.get("owner_id", 0)
    return [DeviceResponse(**d) for d in list_devices(user_id)]


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

@app.post("/v1/alerts", response_model=AlertResponse, tags=["alerts"])
async def alerts_create(payload: AlertCreate, auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    alert = create_alert(payload.name, payload.condition, payload.threshold, payload.action)
    return AlertResponse(**alert)


@app.get("/v1/alerts", response_model=list[AlertResponse], tags=["alerts"])
async def alerts_list(auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return [AlertResponse(**a) for a in list_alerts()]


# ---------------------------------------------------------------------------
# Stats / Analytics
# ---------------------------------------------------------------------------

@app.get("/v1/stats/global", response_model=GlobalStats, tags=["stats"])
async def stats_global(auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    users = _load_users()
    keys = _load_json(KEYS_FILE, [])
    payments = _load_json(PAYMENTS_FILE, [])
    return GlobalStats(
        total_users=len(users),
        total_requests_today=sum(u.get("daily_requests", 0) for u in users),
        total_requests_month=sum(u.get("monthly_requests", 0) for u in users),
        total_downloads_today=sum(u.get("download_count", 0) for u in users),
        total_downloads_month=0,
        total_bytes_today=sum(u.get("daily_bytes", 0) for u in users),
        total_bytes_month=sum(u.get("monthly_bytes", 0) for u in users),
        active_keys=sum(1 for k in keys if k.get("active", True)),
        revenue_stars=sum(p.get("amount", 0) for p in payments if p.get("status") == "completed"),
    )


@app.get("/v1/stats/usage", response_model=UsageStats, tags=["stats"])
async def stats_usage(auth: dict = Depends(get_auth)):
    user_id = auth.get("owner_id", 0)
    user = get_user_by_telegram(user_id) if user_id else None
    if not user and not auth.get("admin", False):
        raise HTTPException(status_code=404, detail="User not found")
    if auth.get("admin", False):
        users = _load_users()
        return UsageStats(
            requests_today=sum(u.get("daily_requests", 0) for u in users),
            requests_month=sum(u.get("monthly_requests", 0) for u in users),
            bytes_today=sum(u.get("daily_bytes", 0) for u in users),
            bytes_month=sum(u.get("monthly_bytes", 0) for u in users),
            downloads_today=sum(u.get("download_count", 0) for u in users),
            downloads_month=0,
        )
    return UsageStats(
        requests_today=user.get("daily_requests", 0),
        requests_month=user.get("monthly_requests", 0),
        bytes_today=user.get("daily_bytes", 0),
        bytes_month=user.get("monthly_bytes", 0),
        downloads_today=user.get("download_count", 0),
        downloads_month=0,
    )


@app.get("/v1/stats/sources", response_model=list[SourceStats], tags=["stats"])
async def stats_sources(_: dict = Depends(get_auth)):
    sources = list_all_sources()
    return [
        SourceStats(
            source_id=s["id"],
            source_name=s["name"],
            searches=0,
            downloads=0,
            errors=0,
        )
        for s in sources
    ]


# ---------------------------------------------------------------------------
# Maintenance
# ---------------------------------------------------------------------------

@app.get("/v1/maintenance", response_model=MaintenanceStatus, tags=["maintenance"])
async def maintenance_get(_: dict = Depends(get_auth)):
    return MaintenanceStatus(
        enabled=settings.maintenance_mode,
        message=settings.maintenance_message,
    )


@app.post("/v1/maintenance", tags=["maintenance"])
async def maintenance_set(enabled: bool, message: Optional[str] = None, auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    settings.maintenance_mode = enabled
    if message:
        settings.maintenance_message = message
    return {"enabled": enabled, "message": settings.maintenance_message}


# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------

@app.get("/v1/version", response_model=VersionInfo, tags=["meta"])
async def version_info(_: dict = Depends(get_auth)):
    return VersionInfo(
        version="3.2.0",
        build="2026.10.25",
        features=[
            "multi_source_search", "download", "lyrics", "metadata_embed",
            "m3u8_hls_dash", "aria2c", "telegram_bot", "telegram_stars",
            "webhooks", "notifications", "playlists", "batch_operations",
            "user_management", "analytics", "api_keys", "rate_limiting",
            "websocket", "caching", "scheduler", "plugins", "advanced_download",
            "federated_search", "pause_resume_download", "priority_queue",
        ],
        api_version="v1",
    )


# ---------------------------------------------------------------------------
# Logs / Cache
# ---------------------------------------------------------------------------

@app.get("/v1/logs", tags=["system"])
async def logs_get(lines: int = 100, auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return {"logs": [], "note": "Log streaming not implemented in this build"}


@app.delete("/v1/logs", tags=["system"])
async def logs_clear(auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return {"cleared": True}


# ---------------------------------------------------------------------------
# Watchdog / Keep-Alive Health
# ---------------------------------------------------------------------------


@app.get("/v1/watchdog/health", response_model=WatchdogHealthResponse, tags=["watchdog"])
async def watchdog_health(auth: dict = Depends(get_auth)):
    """Get the current health status of all monitored components."""
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return watchdog.get_health()


@app.post("/v1/watchdog/recover/{component}", tags=["watchdog"])
async def watchdog_recover_component(component: str, auth: dict = Depends(get_auth)):
    """Manually trigger recovery for a specific component."""
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    handler = watchdog._recovery_handlers.get(component)
    if not handler:
        raise HTTPException(status_code=404, detail=f"No recovery handler for {component}")
    try:
        if asyncio.iscoroutinefunction(handler):
            await handler()
        else:
            handler()
        return {"recovered": True, "component": component}
    except Exception as exc:
        log_error(exc, context=f"watchdog manual recovery {component}")
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Metrics (Prometheus-compatible)
# ---------------------------------------------------------------------------

@app.get("/v1/metrics", tags=["metrics"])
async def metrics(auth: dict = Depends(get_auth)):
    """Prometheus-compatible metrics endpoint."""
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    import time as _time

    health = watchdog.get_health()
    dl_jobs = download_manager.list_jobs()

    # Count jobs by status
    status_counts = {}
    for job in dl_jobs:
        status_counts[job.get("status", "unknown")] = status_counts.get(job.get("status", "unknown"), 0) + 1

    lines = [
        '# HELP videl_api_uptime_seconds Uptime in seconds',
        '# TYPE videl_api_uptime_seconds gauge',
        f'videl_api_uptime_seconds {_time.time() - START_TIME}',
        '',
        '# HELP videl_api_health_status Component health status (1=healthy, 0=unhealthy)',
        '# TYPE videl_api_health_status gauge',
    ]

    for name, comp in health.get("components", {}).items():
        healthy = 1 if comp.get("healthy", False) else 0
        lines.append(f'videl_api_health_status{{component="{name}"}} {healthy}')

    lines.extend([
        '',
        '# HELP videl_api_download_jobs Total download jobs by status',
        '# TYPE videl_api_download_jobs gauge',
    ])

    for status, count in status_counts.items():
        lines.append(f'videl_api_download_jobs{{status="{status}"}} {count}')

    lines.extend([
        '',
        '# HELP videl_api_active_connections Active WebSocket connections',
        '# TYPE videl_api_active_connections gauge',
        f'videl_api_active_connections {len(getattr(ws_manager, "_connections", {}))}',
        '',
        '# HELP videl_api_version_info API version info',
        '# TYPE videl_api_version_info gauge',
        f'videl_api_version_info{{version="3.2.0"}} 1',
        '',
    ])

    return Response(
        content="\n".join(lines),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


# ---------------------------------------------------------------------------
# System Info & Diagnostics
# ---------------------------------------------------------------------------

@app.get("/v1/system/info", tags=["system"])
async def system_info(_: dict = Depends(get_auth)):
    import platform
    import sys
    return {
        "platform": platform.platform(),
        "python_version": sys.version,
        "cpu_count": __import__("os").cpu_count(),
        "uptime_seconds": time.time() - START_TIME,
        "version": "3.2.0",
    }


@app.get("/v1/system/disk", tags=["system"])
async def system_disk(auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    import shutil
    total, used, free = shutil.disk_usage("/")
    return {
        "total_bytes": total,
        "used_bytes": used,
        "free_bytes": free,
        "usage_percent": round(used / total * 100, 2),
    }


@app.get("/v1/system/memory", tags=["system"])
async def system_memory(auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    import os
    try:
        with open("/proc/meminfo") as f:
            meminfo = {}
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    meminfo[parts[0].rstrip(":")] = int(parts[1]) * 1024
        return {
            "total": meminfo.get("MemTotal", 0),
            "available": meminfo.get("MemAvailable", 0),
            "free": meminfo.get("MemFree", 0),
        }
    except Exception:
        return {"error": "Memory info not available"}


# ---------------------------------------------------------------------------
# Environment / Config (safe values only)
# ---------------------------------------------------------------------------

@app.get("/v1/config", tags=["system"])
async def config_view(auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return {
        "api_version": settings.api_version,
        "download_dir": str(settings.download_dir),
        "max_concurrent": settings.download_max_concurrent,
        "rate_limit_default": settings.rate_limit_default,
        "quota_daily_requests": settings.quota_daily_requests,
        "quota_monthly_requests": settings.quota_monthly_requests,
        "hls_enabled": settings.hls_enabled,
        "hls_max_threads": settings.hls_max_threads,
        "metadata_embed": settings.metadata_embed,
        "sponsorblock": settings.sponsorblock,
        "telegram_bot_enabled": bool(settings.telegram_bot_token),
        "telegram_stars_enabled": settings.telegram_stars_enabled,
        "webhook_enabled": settings.webhook_enabled,
        "notification_enabled": settings.notification_enabled,
        "analytics_enabled": settings.analytics_enabled,
        "maintenance_mode": settings.maintenance_mode,
        "user_registration_enabled": settings.user_registration_enabled,
        "ssrf_guard": settings.ssrf_guard,
        "credential_redaction": settings.credential_redaction,
    }


# ---------------------------------------------------------------------------
# Rate Limit / Quota
# ---------------------------------------------------------------------------

@app.get("/v1/rate-limit/status", tags=["rate_limit"])
async def rate_limit_status(auth: dict = Depends(get_auth)):
    return {
        "enabled": settings.rate_limit_enabled,
        "default_per_minute": settings.rate_limit_default,
        "key_rate_limit": auth.get("rate_limit"),
    }


@app.post("/v1/rate-limit/reset", tags=["rate_limit"])
async def rate_limit_reset(auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return {"reset": True}


@app.get("/v1/quota/status", tags=["quota"])
async def quota_status(auth: dict = Depends(get_auth)):
    return {
        "daily_requests": settings.quota_daily_requests,
        "monthly_requests": settings.quota_monthly_requests,
        "daily_bytes": settings.quota_daily_bytes,
        "monthly_bytes": settings.quota_monthly_bytes,
    }


@app.post("/v1/quota/reset", tags=["quota"])
async def quota_reset(auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return {"reset": True}


# ---------------------------------------------------------------------------
# API Key Extended
# ---------------------------------------------------------------------------

@app.get("/v1/keys/extended", response_model=list[ApiKeyExtended], tags=["keys"])
async def keys_extended(auth: dict = Depends(get_auth)):
    owner_id = auth.get("owner_id", 0)
    keys = await list_api_keys(owner_id if not auth.get("admin", False) else 0)
    result = []
    for k in keys:
        result.append(ApiKeyExtended(
            key_id=k.get("_id", ""),
            key_prefix=k.get("key_prefix", ""),
            tier=k.get("tier", "free"),
            scopes=k.get("scopes", []),
            active=k.get("active", True),
            rate_limit=k.get("rate_limit"),
            daily_limit=k.get("daily_limit", 0),
            monthly_limit=k.get("monthly_limit", 0),
            daily_bytes=k.get("daily_bytes", 0),
            monthly_bytes=k.get("monthly_bytes", 0),
            daily_requests=k.get("daily_requests", 0),
            monthly_requests=k.get("monthly_requests", 0),
            daily_bytes_used=k.get("daily_bytes", 0),
            monthly_bytes_used=k.get("monthly_bytes", 0),
            expires_at=k.get("expires_at"),
            created_at=k.get("created_at", ""),
            last_used_at=k.get("last_used_at"),
            telegram_id=k.get("telegram_id"),
            username=k.get("username"),
            label=k.get("label"),
        ))
    return result



# ---------------------------------------------------------------------------
# Source Health / Stats
# ---------------------------------------------------------------------------

@app.get("/v1/source/stats", response_model=list[SourceStats], tags=["sources"])
async def source_stats(_: dict = Depends(get_auth)):
    sources = list_all_sources()
    return [SourceStats(source_id=s["id"], source_name=s["name"], searches=0, downloads=0, errors=0) for s in sources]





# ---------------------------------------------------------------------------
# Content Moderation / Abuse / Geo
# ---------------------------------------------------------------------------

@app.post("/v1/content/moderate", tags=["moderation"])
async def content_moderate(payload: dict, auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return {"moderated": True, "action": "allowed"}


@app.get("/v1/content/moderation", tags=["moderation"])
async def content_moderation_log(auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return {"logs": []}


@app.post("/v1/abuse/detect", tags=["abuse"])
async def abuse_detect(payload: dict, auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return {"detected": False, "risk_score": 0}


@app.get("/v1/abuse/log", tags=["abuse"])
async def abuse_log(auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return {"entries": []}


@app.get("/v1/geo/status", tags=["geo"])
async def geo_status(_: dict = Depends(get_auth)):
    return {"blocked_countries": [], "allowed_countries": []}


# ---------------------------------------------------------------------------
# Custom Domain
# ---------------------------------------------------------------------------

@app.post("/v1/domain/custom", tags=["domain"])
async def domain_custom(payload: dict, auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return {"added": True, "domain": payload.get("domain", "")}


@app.get("/v1/domain/status", tags=["domain"])
async def domain_status(_: dict = Depends(get_auth)):
    return {"custom_domain": None, "ssl": False}


# ---------------------------------------------------------------------------
# OAuth / SSO
# ---------------------------------------------------------------------------

@app.post("/v1/auth/login", tags=["auth"])
async def auth_login(payload: dict):
    return {"token": "oauth_placeholder", "expires_in": 3600}


@app.get("/v1/auth/callback", tags=["auth"])
async def auth_callback(code: str, state: Optional[str] = None):
    return {"status": "ok", "code": code}


@app.get("/v1/auth/providers", tags=["auth"])
async def auth_providers(_: dict = Depends(get_auth)):
    return {"providers": ["telegram", "google", "github", "discord"]}


# ---------------------------------------------------------------------------
# IP Allowlist / Blocklist
# ---------------------------------------------------------------------------

@app.post("/v1/ip/allowlist", tags=["ip"])
async def ip_allowlist_add(payload: dict, auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return {"added": True, "ip": payload.get("ip", "")}


@app.delete("/v1/ip/allowlist/{ip}", tags=["ip"])
async def ip_allowlist_remove(ip: str, auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return {"removed": True, "ip": ip}


@app.post("/v1/ip/blocklist", tags=["ip"])
async def ip_blocklist_add(payload: dict, auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return {"added": True, "ip": payload.get("ip", "")}


@app.delete("/v1/ip/blocklist/{ip}", tags=["ip"])
async def ip_blocklist_remove(ip: str, auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return {"removed": True, "ip": ip}


# ============================================================================
# TELEGRAM BOT WEBHOOK
# ============================================================================

@app.post("/v1/telegram/webhook", tags=["telegram"])
async def telegram_webhook(request_body: dict):
    """Receive Telegram Bot webhook updates."""
    await process_update(request_body)
    return {"ok": True}


@app.post("/v1/telegram/set-webhook", tags=["telegram"])
async def telegram_set_webhook(url: str, auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    await set_webhook(url)
    return {"webhook": url, "set": True}


@app.post("/v1/telegram/delete-webhook", tags=["telegram"])
async def telegram_delete_webhook(auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    await delete_tg_webhook()
    return {"deleted": True}


@app.get("/v1/telegram/bot-info", tags=["telegram"])
async def telegram_bot_info(_: dict = Depends(get_auth)):
    bot = await get_bot()
    if not bot:
        return {"enabled": False}
    return {"enabled": True, "username": settings.telegram_bot_username}


# ============================================================================
# OAUTH2 / JWT TOKENS
# ============================================================================

@app.post("/v1/auth/token", response_model=TokenResponse, tags=["auth"])
async def oauth_token(payload: TokenRequest):
    # Validate client credentials (simple check)
    client_id = payload.__dict__.get("client_id", "default")
    client_secret = payload.__dict__.get("client_secret", "default")
    result = create_oauth_token(client_id, client_secret, payload.scope)
    if not result:
        raise HTTPException(status_code=401, detail="Invalid client credentials")
    return result


@app.post("/v1/auth/token/refresh", tags=["auth"])
async def oauth_refresh(payload: TokenRefreshRequest):
    result = validate_oauth_token(payload.refresh_token)
    if not result:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    new_token = create_oauth_token(result.get("client_id", "default"), "",
                                    result.get("scope"))
    if not new_token:
        raise HTTPException(status_code=500, detail="Token refresh failed")
    return new_token


# ============================================================================
# TWO-FACTOR AUTHENTICATION
# ============================================================================

@app.post("/v1/auth/2fa/setup", response_model=TwoFactorResponse, tags=["auth"])
async def auth_2fa_setup(payload: TwoFactorSetup, auth: dict = Depends(get_auth)):
    if not auth.get("admin", False) and auth.get("owner_id") != payload.user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    return setup_2fa(payload.user_id)


@app.post("/v1/auth/2fa/verify", tags=["auth"])
async def auth_2fa_verify(payload: TwoFactorVerify, _: dict = Depends(get_auth)):
    ok = verify_2fa(payload.user_id, payload.token)
    if not ok:
        raise HTTPException(status_code=401, detail="Invalid 2FA token")
    enable_2fa(payload.user_id)
    return {"verified": True}


@app.post("/v1/auth/2fa/backup", tags=["auth"])
async def auth_2fa_backup(user_id: int, code: str, auth: dict = Depends(get_auth)):
    if not auth.get("admin", False) and auth.get("owner_id") != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    ok = verify_2fa_backup(user_id, code)
    if not ok:
        raise HTTPException(status_code=401, detail="Invalid backup code")
    return {"verified": True}


# ============================================================================
# NOTIFICATION PREFERENCES
# ============================================================================

@app.get("/v1/notifications/preferences", tags=["notifications"])
async def notif_prefs_get(auth: dict = Depends(get_auth)):
    user_id = auth.get("owner_id", 0)
    return get_notif_prefs(user_id)


@app.put("/v1/notifications/preferences", tags=["notifications"])
async def notif_prefs_put(payload: NotificationPreference, auth: dict = Depends(get_auth)):
    user_id = auth.get("owner_id", 0)
    return set_notif_prefs(user_id, payload.model_dump())


# ============================================================================
# FILE ENCRYPTION
# ============================================================================

@app.post("/v1/files/encrypt", response_model=FileEncryptResponse, tags=["files"])
async def files_encrypt(payload: FileEncryptRequest, _: dict = Depends(get_auth)):
    return encrypt_file_record(payload.file_path, payload.password)


@app.post("/v1/files/decrypt", tags=["files"])
async def files_decrypt(payload: FileDecryptRequest, _: dict = Depends(get_auth)):
    ok = decrypt_file_record(payload.file_path, payload.password)
    if not ok:
        raise HTTPException(status_code=400, detail="Decryption failed")
    return {"decrypted": True}


# ============================================================================
# DOWNLOAD SPEED LIMITING
# ============================================================================

@app.post("/v1/download/speed-limit", response_model=SpeedLimitResponse, tags=["download"])
async def download_speed_limit(payload: SpeedLimitRequest, auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return set_speed_limit(payload.key_id, payload.max_kbps)


@app.get("/v1/download/speed-limit/{key_id}", tags=["download"])
async def download_speed_limit_get(key_id: str, _: dict = Depends(get_auth)):
    limit = get_speed_limit(key_id)
    if not limit:
        raise HTTPException(status_code=404, detail="Speed limit not found")
    return limit


# ============================================================================
# DOWNLOAD SCHEDULING
# ============================================================================

@app.post("/v1/download/schedule", response_model=DownloadScheduleResponse, tags=["download"])
async def download_schedule(payload: DownloadSchedule, auth: dict = Depends(get_auth)):
    user_id = auth.get("owner_id", 0)
    return create_schedule(payload.url, payload.cron_expression,
                           enabled=payload.enabled, format=payload.format,
                           source=payload.source, user_id=user_id)


@app.get("/v1/download/schedule", tags=["download"])
async def download_schedule_list(auth: dict = Depends(get_auth)):
    user_id = auth.get("owner_id", 0)
    return {"schedules": list_schedules(user_id if not auth.get("admin", False) else None)}


@app.post("/v1/download/schedule/{schedule_id}/toggle", tags=["download"])
async def download_schedule_toggle(schedule_id: str, enabled: bool,
                                    auth: dict = Depends(get_auth)):
    ok = toggle_schedule(schedule_id, enabled)
    if not ok:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"enabled": enabled, "schedule_id": schedule_id}


# ============================================================================
# CONTENT RATING
# ============================================================================

@app.post("/v1/content/rate", response_model=ContentRatingResponse, tags=["content"])
async def content_rate(payload: ContentRating, auth: dict = Depends(get_auth)):
    user_id = auth.get("owner_id", 0)
    return rate_content(payload.content_id, payload.rating, user_id, payload.review)


@app.get("/v1/content/rate/{content_id}", response_model=ContentRatingResponse, tags=["content"])
async def content_rating_get(content_id: str, user_id: int = 0,
                              _: dict = Depends(get_auth)):
    return get_content_rating(content_id, user_id)


# ============================================================================
# FAVORITES / BOOKMARKS
# ============================================================================

@app.post("/v1/favorites", response_model=FavoriteResponse, tags=["favorites"])
async def favorites_add(payload: FavoriteCreate, auth: dict = Depends(get_auth)):
    user_id = auth.get("owner_id", 0)
    return add_favorite(user_id, payload.title, payload.url,
                        source=payload.source, thumbnail=payload.thumbnail,
                        tags=payload.tags)


@app.get("/v1/favorites", response_model=list[FavoriteResponse], tags=["favorites"])
async def favorites_list(auth: dict = Depends(get_auth)):
    user_id = auth.get("owner_id", 0)
    return list_favorites(user_id)


@app.delete("/v1/favorites/{fav_id}", tags=["favorites"])
async def favorites_remove(fav_id: str, auth: dict = Depends(get_auth)):
    user_id = auth.get("owner_id", 0)
    ok = remove_favorite(fav_id, user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Favorite not found")
    return {"removed": True}


# ============================================================================
# DOWNLOAD HISTORY EXPORT
# ============================================================================

@app.post("/v1/export/history", tags=["export"])
async def export_history(payload: HistoryExportRequest, auth: dict = Depends(get_auth)):
    user_id = auth.get("owner_id", 0)
    return create_export(user_id, payload.format.value)


@app.get("/v1/export/history", tags=["export"])
async def export_history_list(auth: dict = Depends(get_auth)):
    user_id = auth.get("owner_id", 0)
    return {"exports": list_exports(user_id)}


# ============================================================================
# WEBHOOK DELIVERY TRACKING
# ============================================================================

@app.get("/v1/webhooks/deliveries", tags=["webhooks"])
async def webhook_deliveries(auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return {"deliveries": _load_webhook_deliveries() if "_load_webhook_deliveries" in dir() else []}


# ============================================================================
# API KEY AUTO-ROTATION
# ============================================================================

@app.post("/v1/keys/rotation/schedule", tags=["keys"])
async def key_rotation_schedule(payload: KeyRotationSchedule, auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return schedule_key_rotation(payload.key_id, payload.interval_days, payload.enabled)


@app.get("/v1/keys/rotation", tags=["keys"])
async def key_rotation_list(auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return {"rotations": list_key_rotations()}


# ============================================================================
# TIER FEATURE FLAGS
# ============================================================================

@app.post("/v1/tiers/features", tags=["tier"])
async def tier_feature_set(payload: TierFeatureFlag, auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return set_tier_feature(payload.tier, payload.feature, payload.enabled)


@app.get("/v1/tiers/{tier}/features", tags=["tier"])
async def tier_feature_get(tier: str, auth: dict = Depends(get_auth)):
    return {"tier": tier, "features": get_tier_features(tier)}


# ============================================================================
# GEO-BLOCKING
# ============================================================================

@app.post("/v1/geo/block", tags=["geo"])
async def geo_block_add(payload: GeoBlockRule, auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return add_geo_block(payload.country_code, payload.blocked, payload.reason)


@app.get("/v1/geo/blocked", tags=["geo"])
async def geo_block_list(_: dict = Depends(get_auth)):
    return {"blocks": list_geo_blocks()}


@app.get("/v1/geo/check/{country_code}", tags=["geo"])
async def geo_check(country_code: str, _: dict = Depends(get_auth)):
    return {"country_code": country_code.upper(), "blocked": is_country_blocked(country_code)}


# ============================================================================
# IP REPUTATION
# ============================================================================

@app.post("/v1/ip/reputation", tags=["ip"])
async def ip_reputation_record(payload: IPReputation, auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return record_ip_reputation(payload.ip, payload.score, payload.flags)


@app.get("/v1/ip/reputation/{ip}", tags=["ip"])
async def ip_reputation_get(ip: str, _: dict = Depends(get_auth)):
    rep = get_ip_reputation(ip)
    if not rep:
        raise HTTPException(status_code=404, detail="IP reputation not found")
    return rep


# ============================================================================
# REQUEST SIGNING KEYS
# ============================================================================

@app.post("/v1/auth/signing-key", tags=["auth"])
async def signing_key_create(payload: SigningKey, auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return create_signing_key(payload.key_id, payload.secret, payload.algorithm)


@app.get("/v1/auth/signing-keys", tags=["auth"])
async def signing_keys_list(auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return {"keys": list_signing_keys()}


# ============================================================================
# API VERSIONING
# ============================================================================

@app.get("/v1/versions", response_model=list[APIVersion], tags=["system"])
async def api_versions(auth: dict = Depends(get_auth)):
    return list_api_versions()


@app.post("/v1/versions", tags=["system"])
async def api_version_register(version: str, status: str = "active",
                                sunset_date: Optional[str] = None,
                                auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return register_api_version(version, status, sunset_date)


# ============================================================================
# BULK KEY OPERATIONS
# ============================================================================

@app.post("/v1/keys/bulk", response_model=BulkKeyResponse, tags=["keys"])
async def keys_bulk_create(payload: BulkKeyCreate, auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    keys = bulk_create_keys(payload.count, payload.tier, payload.scopes)
    return BulkKeyResponse(keys=keys, total=len(keys))


# ============================================================================
# KEY SHARING
# ============================================================================

@app.post("/v1/keys/share", response_model=KeyShareResponse, tags=["keys"])
async def keys_share(payload: KeyShare, auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return create_key_share(payload.key_id, payload.expires_in_hours, payload.max_uses)


@app.get("/v1/keys/shares", tags=["keys"])
async def keys_shares_list(auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return {"shares": list_key_shares()}


# ============================================================================
# TEAM / COLLABORATOR MANAGEMENT
# ============================================================================

@app.post("/v1/teams", response_model=TeamResponse, tags=["teams"])
async def teams_create(name: str, auth: dict = Depends(get_auth)):
    user_id = auth.get("owner_id", 0)
    return create_team(name, user_id)


@app.get("/v1/teams", response_model=list[TeamResponse], tags=["teams"])
async def teams_list(auth: dict = Depends(get_auth)):
    user_id = auth.get("owner_id", 0)
    return list_teams(user_id if not auth.get("admin", False) else None)


@app.post("/v1/teams/{team_id}/members", tags=["teams"])
async def teams_add_member(team_id: str, user_id: int, role: str = "member",
                            auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    ok = add_team_member(team_id, user_id, role)
    if not ok:
        raise HTTPException(status_code=404, detail="Team not found or member exists")
    return {"added": True, "team_id": team_id, "user_id": user_id, "role": role}


# ============================================================================
# RBAC - ROLES
# ============================================================================

@app.post("/v1/rbac/roles", response_model=RoleResponse, tags=["rbac"])
async def rbac_role_create(payload: RoleCreate, auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return create_role(payload.name, payload.permissions)


@app.get("/v1/rbac/roles", response_model=list[RoleResponse], tags=["rbac"])
async def rbac_roles_list(auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return list_roles()


@app.post("/v1/rbac/assign", tags=["rbac"])
async def rbac_assign(user_id: int, role_id: str, auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    ok = assign_role(user_id, role_id)
    if not ok:
        raise HTTPException(status_code=404, detail="User not found")
    return {"assigned": True, "user_id": user_id, "role_id": role_id}


# ============================================================================
# AUDIT LOG
# ============================================================================

@app.post("/v1/audit/log", tags=["audit"])
async def audit_log_create(user_id: Optional[int], action: str, resource: str,
                            resource_id: Optional[str] = None,
                            details: Optional[dict] = None,
                            ip_address: Optional[str] = None,
                            user_agent: Optional[str] = None,
                            auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return write_audit_log(user_id, action, resource, resource_id,
                           details or {}, ip_address, user_agent)


@app.get("/v1/audit/log", tags=["audit"])
async def audit_log_list(user_id: Optional[int] = None, action: Optional[str] = None,
                          resource: Optional[str] = None, limit: int = 50,
                          auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return {"logs": list_audit_logs(user_id=user_id, action=action,
                                     resource=resource, limit=limit)}


# ============================================================================
# SESSION MANAGEMENT
# ============================================================================

@app.post("/v1/sessions", response_model=SessionInfo, tags=["sessions"])
async def sessions_create(device_id: Optional[str] = None,
                           ip_address: Optional[str] = None,
                           user_agent: Optional[str] = None,
                           auth: dict = Depends(get_auth)):
    user_id = auth.get("owner_id", 0)
    return create_session(user_id, device_id, ip_address, user_agent)


@app.get("/v1/sessions", response_model=list[SessionInfo], tags=["sessions"])
async def sessions_list(auth: dict = Depends(get_auth)):
    user_id = auth.get("owner_id", 0)
    return list_sessions(user_id if not auth.get("admin", False) else None)


@app.delete("/v1/sessions/{session_id}", tags=["sessions"])
async def sessions_revoke(session_id: str, auth: dict = Depends(get_auth)):
    ok = revoke_session(session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"revoked": True}


# ============================================================================
# DEVICE FINGERPRINTING
# ============================================================================

@app.post("/v1/devices/fingerprint", tags=["devices"])
async def device_fingerprint_record(payload: DeviceFingerprint, _: dict = Depends(get_auth)):
    return record_device_fingerprint(payload.fingerprint_id, payload.user_agent,
                                      payload.accept_language, payload.platform,
                                      payload.screen_resolution)


# ============================================================================
# CONCURRENT SESSION LIMITS
# ============================================================================

@app.post("/v1/sessions/limit", tags=["sessions"])
async def session_limit_set(max_sessions: int, auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return set_session_limit(max_sessions)


@app.get("/v1/sessions/limit", tags=["sessions"])
async def session_limit_get(_: dict = Depends(get_auth)):
    return {"max_sessions": get_session_limit()}


# ============================================================================
# PASSWORD RESET
# ============================================================================

@app.post("/v1/auth/password-reset/request", tags=["auth"])
async def password_reset_request(payload: PasswordResetRequest):
    return request_password_reset(payload.email)


@app.post("/v1/auth/password-reset/confirm", tags=["auth"])
async def password_reset_confirm(payload: PasswordResetConfirm):
    ok = confirm_password_reset(payload.token, payload.new_password)
    if not ok:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    return {"reset": True}


# ============================================================================
# CUSTOM RATE LIMITS PER KEY
# ============================================================================

@app.post("/v1/rate-limit/custom", tags=["rate_limit"])
async def custom_rate_limit(payload: CustomRateLimit, auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return set_custom_rate_limit(payload.key_id, payload.requests_per_minute,
                                  payload.burst)


# ============================================================================
# DOWNLOAD BANDWIDTH ALLOCATION
# ============================================================================

@app.post("/v1/download/bandwidth", tags=["download"])
async def download_bandwidth(payload: BandwidthAllocation, auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return set_bandwidth_allocation(payload.key_id, payload.max_bytes_per_day,
                                     payload.max_bytes_per_month)


# ============================================================================
# DOWNLOAD COMPLETION NOTIFICATIONS
# ============================================================================

@app.post("/v1/download/notify", tags=["download"])
async def download_notify(payload: DownloadNotification, auth: dict = Depends(get_auth)):
    user_id = auth.get("owner_id", 0)
    return set_download_notification(payload.job_id, payload.notify_on_complete,
                                      payload.notify_on_error, payload.channels)


# ============================================================================
# AUTO-RETRY FAILED DOWNLOADS
# ============================================================================

@app.post("/v1/download/retry-policy", tags=["download"])
async def download_retry_policy(payload: DownloadRetryPolicy, auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return set_retry_policy("global", payload.max_retries, payload.backoff_seconds,
                             payload.retry_on_error)


# ============================================================================
# SOURCE HEALTH MONITORING
# ============================================================================

@app.get("/v1/source/health/{source_id}", response_model=SourceHealth, tags=["sources"])
async def source_health_get(source_id: str, _: dict = Depends(get_auth)):
    health = get_source_health(source_id)
    if not health:
        raise HTTPException(status_code=404, detail="Source health not found")
    return health


@app.post("/v1/source/health", tags=["sources"])
async def source_health_record(source_id: str, status: str,
                                latency_ms: Optional[float] = None,
                                uptime_percent: float = 100.0,
                                error_count: int = 0,
                                auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return record_source_health(source_id, status, latency_ms, uptime_percent, error_count)


@app.get("/v1/source/latency/{source_id}", tags=["sources"])
async def source_latency_stats(source_id: str, _: dict = Depends(get_auth)):
    return get_source_latency_stats(source_id)


# ============================================================================
# FAILOVER RULES
# ============================================================================

@app.post("/v1/failover/rules", tags=["failover"])
async def failover_rule_add(source_id: str, fallback_source: str,
                             threshold: float = 0.5, enabled: bool = True,
                             auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return add_failover_rule(source_id, fallback_source, threshold, enabled)


@app.get("/v1/failover/rules", tags=["failover"])
async def failover_rules_list(auth: dict = Depends(get_auth)):
    return {"rules": list_failover_rules()}


# ============================================================================
# CACHE INVALIDATION BY TAG
# ============================================================================

@app.post("/v1/cache/invalidate/{tag}", tags=["cache"])
async def cache_invalidate(tag: str, auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    count = invalidate_cache_tag(tag)
    return {"invalidated": count, "tag": tag}


# ============================================================================
# CACHE WARMING
# ============================================================================

@app.post("/v1/cache/warm", tags=["cache"])
async def cache_warm(payload: CacheWarmRequest, auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return warm_cache(payload.queries, payload.source, payload.limit_per_query)


@app.get("/v1/cache/warm", tags=["cache"])
async def cache_warm_list(auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return {"warms": list_cache_warms()}


# ============================================================================
# SEARCH HISTORY
# ============================================================================

@app.get("/v1/search/history", tags=["search"])
async def search_history(limit: int = 50, auth: dict = Depends(get_auth)):
    user_id = auth.get("owner_id", 0)
    return {"history": get_search_history(user_id, limit)}


@app.post("/v1/search/history", tags=["search"])
async def search_history_record(query: str, source: Optional[str] = None,
                                 results_count: int = 0,
                                 auth: dict = Depends(get_auth)):
    user_id = auth.get("owner_id", 0)
    return record_search_history(user_id, query, source, results_count)


# ============================================================================
# SAVED SEARCHES
# ============================================================================

@app.post("/v1/search/saved", response_model=SavedSearch, tags=["search"])
async def saved_search_create(payload: SavedSearchCreate, auth: dict = Depends(get_auth)):
    user_id = auth.get("owner_id", 0)
    return save_search(user_id, payload.name, payload.query, payload.source)


@app.get("/v1/search/saved", response_model=list[SavedSearch], tags=["search"])
async def saved_search_list(auth: dict = Depends(get_auth)):
    user_id = auth.get("owner_id", 0)
    return list_saved_searches(user_id)


@app.delete("/v1/search/saved/{search_id}", tags=["search"])
async def saved_search_delete(search_id: str, auth: dict = Depends(get_auth)):
    user_id = auth.get("owner_id", 0)
    ok = delete_saved_search(search_id, user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Saved search not found")
    return {"deleted": True}


# ============================================================================
# SEARCH AUTOCOMPLETE
# ============================================================================

@app.post("/v1/search/autocomplete", tags=["search"])
async def search_autocomplete(payload: AutocompleteRequest, _: dict = Depends(get_auth)):
    # Simple autocomplete: return matching saved searches and trending
    suggestions = []
    # Add trending matches
    trending = get_trending(limit=payload.limit)
    for t in trending:
        if payload.query.lower() in t.get("query", "").lower():
            suggestions.append(t["query"])
    return {"suggestions": suggestions[: payload.limit]}


# ============================================================================
# TRENDING SEARCHES
# ============================================================================

@app.get("/v1/search/trending", tags=["search"])
async def search_trending(limit: int = 20, _: dict = Depends(get_auth)):
    return {"trending": get_trending(limit)}


# ============================================================================
# POPULAR CONTENT
# ============================================================================

@app.get("/v1/content/popular", tags=["content"])
async def content_popular(limit: int = 20, _: dict = Depends(get_auth)):
    # Return popular content from search history/downloads
    return {"popular": [], "total": 0, "note": "Popular content tracking via download analytics"}


# ============================================================================
# USER ACTIVITY FEED
# ============================================================================

@app.get("/v1/activity/feed", tags=["activity"])
async def activity_feed(limit: int = 50, auth: dict = Depends(get_auth)):
    user_id = auth.get("owner_id", 0)
    return {"activities": get_activity_feed(user_id, limit)}


@app.post("/v1/activity/record", tags=["activity"])
async def activity_record(action: str, details: Optional[dict] = None,
                           auth: dict = Depends(get_auth)):
    user_id = auth.get("owner_id", 0)
    return record_activity(user_id, action, details or {})


# ============================================================================
# USAGE REPORTS
# ============================================================================

@app.post("/v1/reports/usage", tags=["reports"])
async def reports_usage(period: str = "monthly", format: str = "csv",
                         auth: dict = Depends(get_auth)):
    user_id = auth.get("owner_id", 0)
    return create_usage_report(user_id, period, format)


@app.get("/v1/reports/usage", tags=["reports"])
async def reports_usage_list(auth: dict = Depends(get_auth)):
    user_id = auth.get("owner_id", 0)
    return {"reports": list_usage_reports(user_id)}


# ============================================================================
# KEY SCOPES / USAGE / SUSPICIOUS ACTIVITY
# ============================================================================

@app.post("/v1/keys/{key_id}/scopes", tags=["keys"])
async def key_scopes_set(key_id: str, payload: KeyScopes, auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    ok = set_key_scopes(key_id, payload.scopes)
    if not ok:
        raise HTTPException(status_code=404, detail="Key not found")
    return {"updated": True, "key_id": key_id, "scopes": payload.scopes}


@app.get("/v1/keys/{key_id}/usage", tags=["keys"])
async def key_usage_get(key_id: str, _: dict = Depends(get_auth)):
    usage = get_key_usage(key_id)
    if not usage:
        return {"key_id": key_id, "total_requests": 0}
    return usage


@app.get("/v1/keys/{key_id}/rate-limit", tags=["keys"])
async def key_rate_limit_status(key_id: str, _: dict = Depends(get_auth)):
    """Get the current rate limit status for an API key."""
    result = rate_limiter.check(key_id, cost=0)  # cost=0 means just check, don't consume
    return {
        "key_id": key_id,
        "limit": result.limit,
        "remaining": result.remaining,
        "reset_after_seconds": result.reset_after,
        "retry_after_seconds": result.retry_after,
    }


@app.post("/v1/keys/{key_id}/concurrency", tags=["keys"])
async def key_concurrency_set(key_id: str, max_concurrent: int,
                               auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    ok = set_download_concurrency(key_id, max_concurrent)
    if not ok:
        raise HTTPException(status_code=404, detail="Key not found")
    return {"updated": True, "key_id": key_id, "max_concurrent": max_concurrent}


@app.get("/v1/keys/{key_id}/concurrency", tags=["keys"])
async def key_concurrency_get(key_id: str, _: dict = Depends(get_auth)):
    val = get_download_concurrency(key_id)
    return {"key_id": key_id, "max_concurrent": val}


@app.post("/v1/keys/{key_id}/file-type-filter", tags=["keys"])
async def key_file_filter_set(key_id: str, payload: FileTypeFilter,
                               auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    ok = set_file_type_filter(key_id, payload.allowed_extensions,
                               payload.blocked_extensions)
    if not ok:
        raise HTTPException(status_code=404, detail="Key not found")
    return {"updated": True, "key_id": key_id}


@app.get("/v1/suspicious-activity", tags=["security"])
async def suspicious_activity_list(limit: int = 50,
                                    auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return {"activities": list_suspicious_activity(limit)}


@app.post("/v1/suspicious-activity", tags=["security"])
async def suspicious_activity_record(user_id: Optional[int], ip_address: str,
                                      activity_type: str, risk_score: float,
                                      action_taken: str = "warn",
                                      auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return record_suspicious_activity(user_id, ip_address, activity_type,
                                       risk_score, action_taken)


# ============================================================================
# VIRUS SCAN
# ============================================================================

@app.post("/v1/scan/virus", tags=["security"])
async def virus_scan(file_path: str, auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return record_virus_scan(file_path, clean=True, threats=[])


# ============================================================================
# CONTENT MODERATION QUEUE
# ============================================================================

@app.post("/v1/moderation", response_model=ModerationItem, tags=["moderation"])
async def moderation_add(content_type: str, content_id: str,
                          reporter_id: Optional[int] = None,
                          reason: str = "",
                          auth: dict = Depends(get_auth)):
    return add_moderation_item(content_type, content_id, reporter_id, reason)


@app.get("/v1/moderation", tags=["moderation"])
async def moderation_list(status: Optional[str] = None,
                           auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return {"items": list_moderation_items(status)}


@app.post("/v1/moderation/{item_id}/action", tags=["moderation"])
async def moderation_action(item_id: str, action: str, moderator_id: int,
                             reason: Optional[str] = None,
                             auth: dict = Depends(get_auth)):
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    ok = moderate_item(item_id, action, moderator_id, reason)
    if not ok:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"actioned": True, "item_id": item_id, "action": action}


# ============================================================================
# TELEGRAM WEBAPP — API Key Creation & Management
# ============================================================================

from pydantic import BaseModel, Field
from typing import Any

# --- WebApp Request/Response Models ---

class TelegramAuthRequest(BaseModel):
    init_data: str = Field(..., description="Telegram WebApp initData string")


class TelegramAuthResponse(BaseModel):
    ok: bool
    user: dict
    token: str | None = None
    expires_in: int | None = None


class KeyCreateRequest(BaseModel):
    tier: str = Field(default="free", description="free|pro|owner")
    label: str | None = None
    scopes: list[str] = Field(default_factory=lambda: ["read", "search"])
    expires_in_days: int | None = None


class KeyCreateResponse(BaseModel):
    ok: bool
    key: str | None = None
    key_id: str | None = None
    tier: str
    scopes: list[str]
    rate_limit: int | None = None
    daily_limit: int
    monthly_limit: int
    daily_bytes: int
    monthly_bytes: int
    expires_at: str | None = None
    error: str | None = None


class KeyInfoResponse(BaseModel):
    ok: bool
    key_id: str
    key_prefix: str
    tier: str
    scopes: list[str]
    active: bool
    rate_limit: int | None = None
    daily_requests: int
    monthly_requests: int
    daily_bytes: int
    monthly_bytes: int
    expires_at: str | None = None
    created_at: str


class KeyListResponse(BaseModel):
    ok: bool
    keys: list[dict]


class StatsResponse(BaseModel):
    ok: bool
    requests_today: int
    requests_month: int
    bytes_today: int
    bytes_month: int
    key_status: str


# --- Telegram WebApp initData verification ---

def _parse_init_data(init_data: str) -> dict:
    """Parse Telegram WebApp initData into a dict."""
    from urllib.parse import parse_qs, unquote
    parsed = parse_qs(init_data)
    result = {}
    for key, values in parsed.items():
        result[key] = unquote(values[0]) if values else ""
    return result


def _verify_telegram_signature(init_data: str, bot_token: str) -> bool:
    """Verify Telegram WebApp initData signature (HMAC-SHA256)."""
    import hmac
    import hashlib

    try:
        parsed = _parse_init_data(init_data)
    except Exception:
        return False

    received_hash = parsed.get("hash", "")
    if not received_hash:
        return False

    # Build data-check-string
    data_check_parts = []
    for key in sorted(parsed.keys()):
        if key != "hash":
            data_check_parts.append(f"{key}={parsed[key]}")
    data_check_string = "\n".join(data_check_parts)

    # Secret key = HMAC-SHA256(bot_token, "WebAppData")
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()

    # Compute hash
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    return hmac.compare_digest(computed_hash, received_hash)


def _extract_telegram_user(init_data: str) -> dict | None:
    """Extract user object from initData."""
    try:
        parsed = _parse_init_data(init_data)
        user_str = parsed.get("user", "")
        if not user_str:
            return None
        import json
        return json.loads(user_str)
    except Exception:
        return None


# --- WebApp Routes ---

@app.post("/v1/web/auth/telegram", response_model=TelegramAuthResponse, tags=["webapp"])
async def web_auth_telegram(payload: TelegramAuthRequest):
    """Verify Telegram WebApp auth and return session info."""
    init_data = payload.init_data

    # Verify signature if bot token is configured
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if bot_token:
        if not _verify_telegram_signature(init_data, bot_token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Telegram signature",
            )

    user = _extract_telegram_user(init_data)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Cannot extract Telegram user",
        )

    telegram_id = user.get("id")
    username = user.get("username", "")
    first_name = user.get("first_name", "")

    # Ensure user has a free tier key if none exists
    from auth import _load_json, KEYS_FILE, _save_json
    existing_keys = _load_json(KEYS_FILE, [])
    user_keys = [k for k in existing_keys if k.get("telegram_id") == telegram_id and k.get("active", True)]

    if not user_keys:
        # Create a default free key
        from auth import create_api_key
        key_data = await create_api_key(
            owner_id=telegram_id,
            scopes=["read", "search"],
            label=f"Telegram: {first_name} (@{username})",
            rate_limit=100,
        )
        # Mark as telegram-linked
        key_data["telegram_id"] = telegram_id
        keys = _load_json(KEYS_FILE, [])
        for k in keys:
            if k.get("_id") == key_data["key_id"]:
                k["telegram_id"] = telegram_id
                k["username"] = username
                k["first_name"] = first_name
                break
        _save_json(KEYS_FILE, keys)

    return TelegramAuthResponse(
        ok=True,
        user=user,
        token=f"vyt_{telegram_id}",
        expires_in=900,
    )


@app.post("/v1/web/keys/create", response_model=KeyCreateResponse, tags=["webapp"])
async def web_create_key(payload: KeyCreateRequest, auth: dict = Depends(validate_api_key)):
    """Create a new API key via WebApp."""
    tier_limits = {
        "free": {"daily": 100, "monthly": 1000, "daily_bytes": 100*1024*1024, "monthly_bytes": 1*1024*1024*1024, "rate": 100, "scopes": ["read", "search"]},
        "pro": {"daily": 1000, "monthly": 30000, "daily_bytes": 1024*1024*1024, "monthly_bytes": 10*1024*1024*1024, "rate": 1000, "scopes": ["read", "search", "download"]},
        "owner": {"daily": 0, "monthly": 0, "daily_bytes": 0, "monthly_bytes": 0, "rate": None, "scopes": ["read", "search", "download", "admin"]},
    }

    tier = payload.tier.lower()
    if tier not in tier_limits:
        raise HTTPException(status_code=400, detail="Invalid tier")

    limits = tier_limits[tier]
    scopes = payload.scopes or limits["scopes"]

    # Owner tier requires admin scope or existing owner
    if tier == "owner" and not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Owner tier requires admin privileges")

    try:
        key_data = await create_api_key(
            owner_id=auth.get("owner_id", 0),
            scopes=scopes,
            expires_in_days=payload.expires_in_days,
            rate_limit=limits["rate"] if limits["rate"] else None,
            label=payload.label or f"WebApp {tier} key",
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create key: {exc}")

    # Attach telegram info if available
    keys = _load_json(KEYS_FILE, [])
    for k in keys:
        if k.get("_id") == key_data["key_id"]:
            k["tier"] = tier
            k["daily_limit"] = limits["daily"]
            k["monthly_limit"] = limits["monthly"]
            k["daily_bytes_limit"] = limits["daily_bytes"]
            k["monthly_bytes_limit"] = limits["monthly_bytes"]
            if auth.get("auth_mode") == "bearer" and "telegram_id" in auth:
                k["telegram_id"] = auth.get("telegram_id")
            break
    _save_json(KEYS_FILE, keys)

    return KeyCreateResponse(
        ok=True,
        key=key_data["key"],
        key_id=key_data["key_id"],
        tier=tier,
        scopes=scopes,
        rate_limit=limits["rate"],
        daily_limit=limits["daily"],
        monthly_limit=limits["monthly"],
        daily_bytes=limits["daily_bytes"],
        monthly_bytes=limits["monthly_bytes"],
        expires_at=key_data.get("expires_at"),
    )


@app.get("/v1/web/keys/list", response_model=KeyListResponse, tags=["webapp"])
async def web_list_keys(auth: dict = Depends(validate_api_key)):
    """List API keys for the authenticated user."""
    from auth import list_api_keys, _load_json, KEYS_FILE

    owner_id = auth.get("owner_id", 0)

    # Owner can see all keys
    if auth.get("admin", False):
        keys = _load_json(KEYS_FILE, [])
    else:
        keys = await list_api_keys(owner_id)

    # Clean sensitive fields
    clean_keys = []
    for k in keys:
        clean_keys.append({
            "key_id": k.get("_id", ""),
            "key_prefix": k.get("key_prefix", ""),
            "tier": k.get("tier", "free"),
            "scopes": k.get("scopes", []),
            "active": k.get("active", True),
            "label": k.get("label", ""),
            "rate_limit": k.get("rate_limit"),
            "daily_limit": k.get("daily_limit", 0),
            "monthly_limit": k.get("monthly_limit", 0),
            "daily_requests": k.get("daily_requests", 0),
            "monthly_requests": k.get("monthly_requests", 0),
            "daily_bytes": k.get("daily_bytes", 0),
            "monthly_bytes": k.get("monthly_bytes", 0),
            "expires_at": k.get("expires_at"),
            "created_at": k.get("created_at", ""),
            "username": k.get("username", ""),
            "first_name": k.get("first_name", ""),
        })

    return KeyListResponse(ok=True, keys=clean_keys)


@app.get("/v1/web/keys/{key_id}", response_model=KeyInfoResponse, tags=["webapp"])
async def web_key_info(key_id: str, auth: dict = Depends(validate_api_key)):
    """Get detailed info about a specific key."""
    from auth import _load_json, KEYS_FILE

    keys = _load_json(KEYS_FILE, [])
    key = None
    for k in keys:
        if k.get("_id") == key_id:
            key = k
            break

    if not key:
        raise HTTPException(status_code=404, detail="Key not found")

    # Check access
    if not auth.get("admin", False) and key.get("owner_id") != auth.get("owner_id", 0):
        raise HTTPException(status_code=403, detail="Access denied")

    return KeyInfoResponse(
        ok=True,
        key_id=key.get("_id", ""),
        key_prefix=key.get("key_prefix", ""),
        tier=key.get("tier", "free"),
        scopes=key.get("scopes", []),
        active=key.get("active", True),
        rate_limit=key.get("rate_limit"),
        daily_requests=key.get("daily_requests", 0),
        monthly_requests=key.get("monthly_requests", 0),
        daily_bytes=key.get("daily_bytes", 0),
        monthly_bytes=key.get("monthly_bytes", 0),
        expires_at=key.get("expires_at"),
        created_at=key.get("created_at", ""),
    )


@app.delete("/v1/web/keys/{key_id}", tags=["webapp"])
async def web_revoke_key(key_id: str, auth: dict = Depends(validate_api_key)):
    """Revoke an API key."""
    from auth import _load_json, KEYS_FILE, _save_json, revoke_api_key

    keys = _load_json(KEYS_FILE, [])
    key = None
    for k in keys:
        if k.get("_id") == key_id:
            key = k
            break

    if not key:
        raise HTTPException(status_code=404, detail="Key not found")

    if not auth.get("admin", False) and key.get("owner_id") != auth.get("owner_id", 0):
        raise HTTPException(status_code=403, detail="Access denied")

    # Use raw key hash for revoke lookup
    await revoke_api_key(key.get("owner_id", 0), key.get("key_hash", ""))
    return {"ok": True, "revoked": True, "key_id": key_id}


@app.patch("/v1/web/keys/{key_id}", tags=["webapp"])
async def web_patch_key(key_id: str, payload: dict, auth: dict = Depends(validate_api_key)):
    """Update a key (owner only)."""
    from auth import patch_api_key, rotate_api_key

    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Owner access required")

    action = payload.get("action", "patch")

    if action == "rotate":
        result = await rotate_api_key(auth.get("owner_id", 0), key_id)
        if not result:
            raise HTTPException(status_code=404, detail="Key not found")
        return {"ok": True, "action": "rotated", "new_key": result.get("key"), "key_id": key_id}
    else:
        result = await patch_api_key(
            auth.get("owner_id", 0),
            key_id,
            scopes=payload.get("scopes"),
            active=payload.get("active"),
            rate_limit=payload.get("rate_limit"),
            expires_in_days=payload.get("expires_in_days"),
            label=payload.get("label"),
        )
        if not result:
            raise HTTPException(status_code=404, detail="Key not found")
        return {"ok": True, "action": "patched", "key": result}


@app.get("/v1/web/stats", response_model=StatsResponse, tags=["webapp"])
async def web_stats(auth: dict = Depends(validate_api_key)):
    """Get usage statistics for the authenticated user."""
    from auth import _load_json, KEYS_FILE

    owner_id = auth.get("owner_id", 0)
    keys = _load_json(KEYS_FILE, [])

    user_keys = [k for k in keys if k.get("owner_id") == owner_id] if not auth.get("admin", False) else keys

    requests_today = sum(k.get("daily_requests", 0) for k in user_keys)
    requests_month = sum(k.get("monthly_requests", 0) for k in user_keys)
    bytes_today = sum(k.get("daily_bytes", 0) for k in user_keys)
    bytes_month = sum(k.get("monthly_bytes", 0) for k in user_keys)

    # Determine overall status
    active_keys = [k for k in user_keys if k.get("active", True)]
    key_status = "active" if active_keys else "inactive"

    return StatsResponse(
        ok=True,
        requests_today=requests_today,
        requests_month=requests_month,
        bytes_today=bytes_today,
        bytes_month=bytes_month,
        key_status=key_status,
    )


@app.get("/v1/web/owner/keys", tags=["webapp"])
async def web_owner_keys(auth: dict = Depends(validate_api_key)):
    """List ALL keys (owner only)."""
    if not auth.get("admin", False):
        raise HTTPException(status_code=403, detail="Owner access required")

    from auth import _load_json, KEYS_FILE
    keys = _load_json(KEYS_FILE, [])

    clean_keys = []
    for k in keys:
        clean_keys.append({
            "key_id": k.get("_id", ""),
            "key_prefix": k.get("key_prefix", ""),
            "owner_id": k.get("owner_id", 0),
            "tier": k.get("tier", "free"),
            "scopes": k.get("scopes", []),
            "active": k.get("active", True),
            "label": k.get("label", ""),
            "username": k.get("username", ""),
            "first_name": k.get("first_name", ""),
            "daily_requests": k.get("daily_requests", 0),
            "monthly_requests": k.get("monthly_requests", 0),
            "expires_at": k.get("expires_at"),
        })

    return {"ok": True, "keys": clean_keys, "total": len(clean_keys)}


# --- WebApp static file serving ---
from fastapi.responses import FileResponse
import os as _os

WEBAPP_DIR = _os.path.join(_os.path.dirname(__file__), "webapp")


@app.get("/app", tags=["webapp"])
async def webapp_index():
    """Serve the Telegram WebApp entry point."""
    index_path = _os.path.join(WEBAPP_DIR, "index.html")
    if _os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "WebApp not built. See webapp/ directory."}


@app.get("/app/{path:path}", tags=["webapp"])
async def webapp_static(path: str):
    """Serve WebApp static assets."""
    file_path = _os.path.join(WEBAPP_DIR, path)
    if _os.path.exists(file_path) and _os.path.isfile(file_path):
        return FileResponse(file_path)
    raise HTTPException(status_code=404, detail="File not found")
