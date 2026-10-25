"""Pydantic request/response schemas for Videl-Api."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------

class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    code: Optional[int] = None


class HealthResponse(BaseModel):
    status: str
    version: str = "2.0.0"
    sources: int
    uptime_seconds: float
    features: dict[str, bool] = {}


class SourceItem(BaseModel):
    id: str
    type: str = "music"
    name: str
    supports_search: bool
    supports_stream: bool = False
    supports_download: bool = False
    supports_chapters: bool = False
    description: str


class SourcesResponse(BaseModel):
    sources: list[SourceItem]


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

class SearchRequest(BaseModel):
    q: str = Field(..., min_length=1, description="Search query")
    source: str = Field(default="youtube", description="Source id (youtube, soundcloud, ...)")
    limit: int = Field(default=20, ge=1, le=100, description="Max results")


class TrackMini(BaseModel):
    id: str
    title: str
    source: str
    source_name: str
    uploader: Optional[str] = None
    duration: Optional[int] = None
    view_count: Optional[int] = None
    thumbnail: Optional[str] = None
    url: Optional[str] = None
    webpage_url: Optional[str] = None
    is_playlist: bool = False
    is_album: bool = False


class SearchResponse(BaseModel):
    query: str
    source: str
    results: list[TrackMini]
    total: int


# ---------------------------------------------------------------------------
# Track / info
# ---------------------------------------------------------------------------

class TrackInfoRequest(BaseModel):
    url: str = Field(..., min_length=1, description="Media URL or video/track id")
    source: Optional[str] = Field(default=None, description="Force a source id")


class TrackInfoResponse(BaseModel):
    id: str
    title: str
    source: str
    source_name: str
    uploader: Optional[str] = None
    uploader_url: Optional[str] = None
    duration: Optional[int] = None
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    thumbnail: Optional[str] = None
    description: Optional[str] = None
    webpage_url: Optional[str] = None
    url: Optional[str] = None
    ext: Optional[str] = None
    format_id: Optional[str] = None
    abr: Optional[float] = None
    filesize: Optional[int] = None
    is_playlist: bool = False
    is_album: bool = False
    track_number: Optional[int] = None
    album: Optional[str] = None
    artist: Optional[str] = None
    genres: list[str] = []
    release_year: Optional[int] = None
    entries: list[TrackMini] = []
    lyrics_available: bool = False


# ---------------------------------------------------------------------------
# Download / stream
# ---------------------------------------------------------------------------

class DownloadRequest(BaseModel):
    url: str = Field(..., min_length=1, description="Media URL or video/track id")
    source: Optional[str] = Field(default=None, description="Force a source id")
    format: str = Field(default="bestaudio/best", description="yt-dlp format selector")
    quality: Optional[str] = Field(default=None, description="Audio bitrate hint")
    use_aria2c: bool = Field(default=True, description="Use aria2c multipart downloader if available")
    embed_metadata: bool = Field(default=True, description="Embed ID3/album-art metadata")
    fetch_lyrics: bool = Field(default=False, description="Also fetch and embed lyrics")


class DownloadResponse(BaseModel):
    id: str
    title: str
    source: str
    file_path: str
    download_url: str
    media_type: str = "application/octet-stream"
    filesize: Optional[int] = None
    duration: Optional[int] = None
    ext: Optional[str] = None
    lyrics: Optional[str] = None


# Download queue / job
class DownloadJobItem(BaseModel):
    job_id: str
    url: str
    source: Optional[str] = None
    status: str
    progress: float
    file_path: Optional[str] = None
    error: Optional[str] = None
    created_at: str
    updated_at: str


class JobListResponse(BaseModel):
    jobs: list[DownloadJobItem]


class JobActionResponse(BaseModel):
    job_id: str
    action: str
    success: bool


# ---------------------------------------------------------------------------
# Lyrics
# ---------------------------------------------------------------------------

class LyricsRequest(BaseModel):
    url: str = Field(..., min_length=1, description="Media URL or video/track id")
    provider: Optional[str] = Field(default=None, description="Lyrics provider: synced, genius, musixmatch, azlyrics")


class LyricsResponse(BaseModel):
    id: str
    title: str
    source: str
    source_name: Optional[str] = None
    lyrics: Optional[str] = None
    lyrics_provider: Optional[str] = None


class LyricsSearchRequest(BaseModel):
    title: str = Field(..., min_length=1, description="Song title")
    artist: Optional[str] = Field(default=None, description="Artist name")
    provider: Optional[str] = Field(default=None, description="Lyrics provider")


# ---------------------------------------------------------------------------
# Metadata (Spotify enrichment)
# ---------------------------------------------------------------------------

class MetadataRequest(BaseModel):
    url: Optional[str] = Field(default=None, description="Spotify track/album/playlist URL")
    query: Optional[str] = Field(default=None, description="Search query (track name)")


class MetadataTrack(BaseModel):
    id: str
    name: str
    artists: list[str] = []
    album: Optional[str] = None
    album_art: Optional[str] = None
    duration_ms: Optional[int] = None
    release_year: Optional[int] = None
    genres: list[str] = []
    isrc: Optional[str] = None
    popularity: Optional[int] = None
    track_number: Optional[int] = None
    explicit: Optional[bool] = None
    preview_url: Optional[str] = None
    spotify_url: Optional[str] = None


class MetadataResponse(BaseModel):
    type: str  # track | album | playlist
    tracks: list[MetadataTrack]
    total: int


# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------

class ApiKeyCreateResponse(BaseModel):
    key: str
    owner_id: int


class ApiKeyRecord(BaseModel):
    key: str
    owner_id: int
    active: bool = True
    created_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# M3U8 / HLS / DASH
# ---------------------------------------------------------------------------

class M3U8ParseRequest(BaseModel):
    url: str = Field(..., min_length=1, description="M3U8/HLS playlist URL")
    headers: Optional[dict[str, str]] = Field(default=None, description="Custom HTTP headers")
    cookies: Optional[str] = Field(default=None, description="Cookie string")
    proxy: Optional[str] = Field(default=None, description="Proxy URL")


class M3U8ParseResponse(BaseModel):
    url: str
    is_variant: bool
    is_media: bool
    version: Optional[int] = None
    target_duration: Optional[float] = None
    media_sequence: Optional[int] = None
    end_list: Optional[bool] = None
    duration: float
    playlists: list[dict] = []
    segments: list[dict] = []
    keys: list[dict] = []
    media: list[dict] = []
    iframes: list[dict] = []
    start: Optional[dict] = None


class M3U8DownloadRequest(BaseModel):
    url: str = Field(..., min_length=1, description="M3U8/HLS playlist URL")
    headers: Optional[dict[str, str]] = Field(default=None)
    cookies: Optional[str] = Field(default=None)
    proxy: Optional[str] = Field(default=None)
    max_threads: int = Field(default=16, ge=1, le=64)
    use_aria2c: bool = Field(default=False)
    decrypt: bool = Field(default=True)
    merge_method: str = Field(default="binary", description="binary | ffmpeg")
    save_name: Optional[str] = Field(default=None)
    custom_range: Optional[str] = Field(default=None, description="e.g. 0-10, 05:00-20:00")
    audio_only: bool = Field(default=False)


class M3U8DownloadResponse(BaseModel):
    file_path: str
    title: str
    segments: int
    duration: float
    merge_method: str
    decrypted: bool
    is_variant: bool


class M3U8JobItem(BaseModel):
    job_id: str
    url: str
    status: str
    progress: float
    file_path: Optional[str] = None
    error: Optional[str] = None
    created_at: str
    updated_at: str
    total_segments: int = 0
    downloaded_segments: int = 0
    meta: dict = {}


# ---------------------------------------------------------------------------
# aria2 RPC
# ---------------------------------------------------------------------------

class Aria2AddRequest(BaseModel):
    uris: list[str] = Field(..., min_length=1, description="List of URLs to download")
    dir: Optional[str] = Field(default=None, description="Download directory")
    out: Optional[str] = Field(default=None, description="Output filename")
    max_connections: int = Field(default=16, ge=1, le=32)
    split: int = Field(default=16, ge=1, le=32)
    proxy: Optional[str] = Field(default=None)
    header: Optional[list[str]] = Field(default=None)


class Aria2AddResponse(BaseModel):
    gid: str


class Aria2StatusResponse(BaseModel):
    gid: str
    status: str
    total_length: Optional[str] = None
    completed_length: Optional[str] = None
    download_speed: Optional[str] = None
    progress: Optional[float] = None
    dir: Optional[str] = None
    files: list[dict] = []


# ============================================================================
# USER MANAGEMENT
# ============================================================================

class UserBase(BaseModel):
    telegram_id: Optional[int] = None
    username: Optional[str] = None
    first_name: Optional[str] = None
    language: str = "en"
    notifications: bool = True


class UserCreate(UserBase):
    tier: str = "free"


class UserUpdate(BaseModel):
    username: Optional[str] = None
    first_name: Optional[str] = None
    language: Optional[str] = None
    notifications: Optional[bool] = None
    tier: Optional[str] = None


class UserResponse(UserBase):
    id: str
    tier: str
    scopes: list[str] = []
    is_admin: bool = False
    is_owner: bool = False
    daily_requests: int = 0
    monthly_requests: int = 0
    daily_bytes: int = 0
    monthly_bytes: int = 0
    stars_balance: int = 0
    lifetime_stars: int = 0
    download_count: int = 0
    search_count: int = 0
    playlist_count: int = 0
    created_at: str
    updated_at: str


class UserListResponse(BaseModel):
    users: list[UserResponse]
    total: int


class UserTierChange(BaseModel):
    tier: str = Field(..., description="free | pro | owner")


# ============================================================================
# TIER / SUBSCRIPTION
# ============================================================================

class TierInfo(BaseModel):
    tier: str
    daily_limit: int
    monthly_limit: int
    daily_bytes_limit: int
    monthly_bytes_limit: int
    rate_limit: Optional[int]
    scopes: list[str]


class TierListResponse(BaseModel):
    tiers: list[TierInfo]


# ============================================================================
# PAYMENTS / TELEGRAM STARS
# ============================================================================

class PaymentCreate(BaseModel):
    tier: str = Field(..., description="Target tier to upgrade to")
    amount: int = Field(..., ge=1, description="Amount in Stars")


class PaymentResponse(BaseModel):
    payment_id: str
    status: str  # pending | completed | failed
    amount: int
    currency: str
    invoice_payload: str
    created_at: str


class PaymentHistoryResponse(BaseModel):
    payments: list[PaymentResponse]
    total: int


class InvoiceRequest(BaseModel):
    title: str
    description: str
    amount: int
    currency: str = "XTR"


# ============================================================================
# PLAYLISTS
# ============================================================================

class PlaylistBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    is_public: bool = False


class PlaylistCreate(PlaylistBase):
    pass


class PlaylistUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    is_public: Optional[bool] = None


class PlaylistResponse(PlaylistBase):
    id: str
    owner_id: int
    item_count: int = 0
    created_at: str
    updated_at: str


class PlaylistItemBase(BaseModel):
    title: str
    url: str
    source: Optional[str] = None
    duration: Optional[int] = None
    thumbnail: Optional[str] = None


class PlaylistItemCreate(PlaylistItemBase):
    pass


class PlaylistItemResponse(PlaylistItemBase):
    id: str
    playlist_id: str
    position: int
    added_at: str


class PlaylistDetailResponse(PlaylistResponse):
    items: list[PlaylistItemResponse] = []


# ============================================================================
# WEBHOOKS
# ============================================================================

class WebhookCreate(BaseModel):
    url: str = Field(..., description="Webhook endpoint URL")
    events: list[str] = Field(default=["download.completed", "payment.completed"])
    secret: Optional[str] = None


class WebhookUpdate(BaseModel):
    url: Optional[str] = None
    events: Optional[list[str]] = None
    secret: Optional[str] = None
    active: Optional[bool] = None


class WebhookResponse(BaseModel):
    id: str
    url: str
    events: list[str]
    active: bool
    created_at: str
    last_triggered: Optional[str] = None
    trigger_count: int = 0


# ============================================================================
# NOTIFICATIONS
# ============================================================================

class NotificationCreate(BaseModel):
    user_id: Optional[int] = Field(default=None, description="Target user (admin only)")
    title: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
    type: str = Field(default="info", description="info | warning | error | success")


class NotificationResponse(BaseModel):
    id: str
    user_id: int
    title: str
    message: str
    type: str
    read: bool = False
    created_at: str


class NotificationListResponse(BaseModel):
    notifications: list[NotificationResponse]
    total: int
    unread: int


# ============================================================================
# BATCH OPERATIONS
# ============================================================================

class BatchItem(BaseModel):
    url: str
    source: Optional[str] = None
    format: str = "bestaudio/best"
    quality: Optional[str] = None


class BatchRequest(BaseModel):
    items: list[BatchItem] = Field(..., min_length=1, max_length=50)


class BatchResponse(BaseModel):
    batch_id: str
    total_items: int
    status: str  # queued | processing | completed | failed
    created_at: str


class BatchStatusResponse(BaseModel):
    batch_id: str
    status: str
    completed_items: int
    total_items: int
    results: list[dict] = []
    error: Optional[str] = None


# ============================================================================
# FILE MANAGEMENT
# ============================================================================

class FileInfo(BaseModel):
    name: str
    path: str
    size: int
    mime_type: str
    created_at: str
    download_url: str


class FileListResponse(BaseModel):
    files: list[FileInfo]
    total: int


# ============================================================================
# IMPORT / EXPORT
# ============================================================================

class ExportRequest(BaseModel):
    type: str = Field(..., description="keys | history | config")
    user_id: Optional[int] = None


class ExportResponse(BaseModel):
    export_id: str
    download_url: str
    expires_at: str


# ============================================================================
# DEVICES / SESSIONS
# ============================================================================

class DeviceRegister(BaseModel):
    device_id: str
    device_name: str
    platform: str  # ios | android | web | desktop


class DeviceResponse(BaseModel):
    id: str
    device_id: str
    device_name: str
    platform: str
    last_active: str
    active: bool


class SessionResponse(BaseModel):
    id: str
    device_id: str
    created_at: str
    expires_at: str
    active: bool


# ============================================================================
# ALERTS
# ============================================================================

class AlertCreate(BaseModel):
    name: str
    condition: str  # e.g. "daily_requests > 80%"
    threshold: float
    action: str  # notify | block | throttle


class AlertResponse(BaseModel):
    id: str
    name: str
    condition: str
    threshold: float
    action: str
    active: bool
    created_at: str


# ============================================================================
# API KEY EXTENDED
# ============================================================================

class ApiKeyExtended(BaseModel):
    key_id: str
    key_prefix: str
    tier: str
    scopes: list[str]
    active: bool
    rate_limit: Optional[int]
    daily_limit: int
    monthly_limit: int
    daily_bytes: int
    monthly_bytes: int
    daily_requests: int
    monthly_requests: int
    daily_bytes_used: int
    monthly_bytes_used: int
    expires_at: Optional[str]
    created_at: str
    last_used_at: Optional[str]
    telegram_id: Optional[int]
    username: Optional[str]
    label: Optional[str]


# ============================================================================
# STATS / ANALYTICS
# ============================================================================

class GlobalStats(BaseModel):
    total_users: int
    total_requests_today: int
    total_requests_month: int
    total_downloads_today: int
    total_downloads_month: int
    total_bytes_today: int
    total_bytes_month: int
    active_keys: int
    revenue_stars: int


class UsageStats(BaseModel):
    requests_today: int
    requests_month: int
    bytes_today: int
    bytes_month: int
    downloads_today: int
    downloads_month: int


class SourceStats(BaseModel):
    source_id: str
    source_name: str
    searches: int
    downloads: int
    errors: int


# ============================================================================
# MAINTENANCE
# ============================================================================

class MaintenanceStatus(BaseModel):
    enabled: bool
    message: str
    started_at: Optional[str] = None


# ============================================================================
# VERSION
# ============================================================================

class VersionInfo(BaseModel):
    version: str
    build: str
    features: list[str]
    api_version: str
