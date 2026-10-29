"""Pydantic request/response schemas for Videl-Api."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
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
    version: str = "3.2.0"
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


# ============================================================================
# OAUTH2 / JWT
# ============================================================================

class TokenRequest(BaseModel):
    grant_type: str = "client_credentials"
    scope: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    scope: Optional[str] = None


class TokenRefreshRequest(BaseModel):
    refresh_token: str


# ============================================================================
# TWO-FACTOR AUTHENTICATION
# ============================================================================

class TwoFactorSetup(BaseModel):
    user_id: int


class TwoFactorVerify(BaseModel):
    user_id: int
    token: str


class TwoFactorResponse(BaseModel):
    enabled: bool
    secret: Optional[str] = None
    qr_code: Optional[str] = None
    backup_codes: list[str] = []


# ============================================================================
# NOTIFICATIONS - EMAIL / SMS / PUSH
# ============================================================================

class EmailNotification(BaseModel):
    to: str
    subject: str
    body: str
    html: Optional[str] = None


class SMSNotification(BaseModel):
    to: str
    message: str


class PushSubscription(BaseModel):
    endpoint: str
    keys: dict  # {p256dh, auth}


class PushNotification(BaseModel):
    subscription: PushSubscription
    title: str
    body: str
    icon: Optional[str] = None
    url: Optional[str] = None


class NotificationPreference(BaseModel):
    email: bool = True
    sms: bool = False
    push: bool = True
    download_complete: bool = True
    payment_received: bool = True
    system_alerts: bool = False
    marketing: bool = False


# ============================================================================
# FILE ENCRYPTION
# ============================================================================

class FileEncryptRequest(BaseModel):
    file_path: str
    password: str


class FileDecryptRequest(BaseModel):
    file_path: str
    password: str


class FileEncryptResponse(BaseModel):
    encrypted_path: str
    algorithm: str = "AES-256-GCM"


# ============================================================================
# DOWNLOAD SPEED LIMITING
# ============================================================================

class SpeedLimitRequest(BaseModel):
    key_id: str
    max_kbps: int  # kilobits per second


class SpeedLimitResponse(BaseModel):
    key_id: str
    max_kbps: int
    active: bool


# ============================================================================
# DOWNLOAD SCHEDULING
# ============================================================================

class DownloadSchedule(BaseModel):
    url: str
    source: Optional[str] = None
    cron_expression: str  # e.g. "0 2 * * *"
    format: str = "bestaudio/best"
    enabled: bool = True


class DownloadScheduleResponse(BaseModel):
    schedule_id: str
    url: str
    cron_expression: str
    next_run: Optional[str] = None
    enabled: bool


# ============================================================================
# CONTENT RATING
# ============================================================================

class ContentRating(BaseModel):
    content_id: str
    rating: int = Field(..., ge=1, le=5)
    review: Optional[str] = Field(default=None, max_length=500)


class ContentRatingResponse(BaseModel):
    content_id: str
    average_rating: float
    total_ratings: int
    user_rating: Optional[int] = None


# ============================================================================
# FAVORITES / BOOKMARKS
# ============================================================================

class FavoriteCreate(BaseModel):
    title: str
    url: str
    source: Optional[str] = None
    thumbnail: Optional[str] = None
    tags: list[str] = []


class FavoriteResponse(BaseModel):
    id: str
    title: str
    url: str
    source: Optional[str]
    thumbnail: Optional[str]
    tags: list[str]
    created_at: str


# ============================================================================
# DOWNLOAD HISTORY EXPORT
# ============================================================================

class ExportFormat(str, Enum):
    JSON = "json"
    CSV = "csv"


class HistoryExportRequest(BaseModel):
    format: ExportFormat = ExportFormat.JSON
    date_from: Optional[str] = None
    date_to: Optional[str] = None


# ============================================================================
# API ANALYTICS PER ENDPOINT
# ============================================================================

class EndpointStats(BaseModel):
    endpoint: str
    method: str
    total_requests: int
    avg_response_time_ms: float
    error_count: int
    last_accessed: Optional[str] = None


# ============================================================================
# WEBHOOK RETRY / EVENT FILTERING
# ============================================================================

class WebhookDelivery(BaseModel):
    webhook_id: str
    event: str
    status: str  # pending, delivered, failed
    attempt: int
    next_retry: Optional[str] = None


class WebhookEventFilter(BaseModel):
    events: list[str]
    secret: Optional[str] = None


# ============================================================================
# API KEY AUTO-ROTATION
# ============================================================================

class KeyRotationSchedule(BaseModel):
    key_id: str
    interval_days: int
    enabled: bool = True


# ============================================================================
# TIER FEATURE FLAGS
# ============================================================================

class TierFeatureFlag(BaseModel):
    tier: str
    feature: str
    enabled: bool


# ============================================================================
# GEO-BLOCKING
# ============================================================================

class GeoBlockRule(BaseModel):
    country_code: str  # ISO 3166-1 alpha-2
    blocked: bool = True
    reason: Optional[str] = None


# ============================================================================
# IP REPUTATION
# ============================================================================

class IPReputation(BaseModel):
    ip: str
    score: float = Field(..., ge=0, le=100)
    flags: list[str] = []
    last_checked: str


# ============================================================================
# REQUEST SIGNING (HMAC)
# ============================================================================

class SigningKey(BaseModel):
    key_id: str
    secret: str
    algorithm: str = "HMAC-SHA256"


# ============================================================================
# API VERSIONING / DEPRECATION
# ============================================================================

class APIVersion(BaseModel):
    version: str
    status: str  # active, deprecated, sunset
    sunset_date: Optional[str] = None


# ============================================================================
# BULK KEY OPERATIONS
# ============================================================================

class BulkKeyCreate(BaseModel):
    count: int = Field(..., ge=1, le=100)
    tier: str = "free"
    scopes: list[str] = ["read", "search"]


class BulkKeyResponse(BaseModel):
    keys: list[dict]
    total: int


# ============================================================================
# KEY SHARING
# ============================================================================

class KeyShare(BaseModel):
    key_id: str
    expires_in_hours: int = 24
    max_uses: Optional[int] = None


class KeyShareResponse(BaseModel):
    share_url: str
    expires_at: str
    max_uses: Optional[int] = None


# ============================================================================
# TEAM / COLLABORATOR MANAGEMENT
# ============================================================================

class TeamMember(BaseModel):
    user_id: int
    role: str  # admin, member, viewer
    key_id: Optional[str] = None


class TeamResponse(BaseModel):
    team_id: str
    name: str
    members: list[TeamMember]
    owner_id: int


# ============================================================================
# RBAC - ROLE-BASED ACCESS CONTROL
# ============================================================================

class RoleCreate(BaseModel):
    name: str
    permissions: list[str]


class RoleResponse(BaseModel):
    role_id: str
    name: str
    permissions: list[str]


class UserRoleAssign(BaseModel):
    user_id: int
    role_id: str


# ============================================================================
# AUDIT LOG
# ============================================================================

class AuditLogEntry(BaseModel):
    id: str
    user_id: Optional[int]
    action: str
    resource: str
    resource_id: Optional[str]
    details: dict
    ip_address: Optional[str]
    user_agent: Optional[str]
    timestamp: str


class AuditLogFilter(BaseModel):
    user_id: Optional[int] = None
    action: Optional[str] = None
    resource: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    limit: int = Field(default=50, ge=1, le=500)


# ============================================================================
# SESSION MANAGEMENT
# ============================================================================

class SessionInfo(BaseModel):
    session_id: str
    user_id: int
    device_id: Optional[str]
    ip_address: Optional[str]
    user_agent: Optional[str]
    created_at: str
    last_active: str
    active: bool


class SessionRevoke(BaseModel):
    session_id: str


# ============================================================================
# DEVICE FINGERPRINTING
# ============================================================================

class DeviceFingerprint(BaseModel):
    fingerprint_id: str
    user_agent: str
    accept_language: str
    platform: str
    screen_resolution: Optional[str] = None


# ============================================================================
# CONCURRENT SESSION LIMITS
# ============================================================================

class SessionLimit(BaseModel):
    max_sessions: int = Field(..., ge=1, le=100)


# ============================================================================
# PASSWORD RESET
# ============================================================================

class PasswordResetRequest(BaseModel):
    email: str


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str


# ============================================================================
# CUSTOM RATE LIMITS PER KEY
# ============================================================================

class CustomRateLimit(BaseModel):
    key_id: str
    requests_per_minute: int = Field(..., ge=1)
    burst: Optional[int] = None


# ============================================================================
# DOWNLOAD BANDWIDTH ALLOCATION
# ============================================================================

class BandwidthAllocation(BaseModel):
    key_id: str
    max_bytes_per_day: int
    max_bytes_per_month: int


# ============================================================================
# DOWNLOAD COMPLETION NOTIFICATIONS
# ============================================================================

class DownloadNotification(BaseModel):
    job_id: str
    notify_on_complete: bool = True
    notify_on_error: bool = True
    channels: list[str] = ["websocket"]  # websocket, email, push


# ============================================================================
# AUTO-RETRY FAILED DOWNLOADS
# ============================================================================

class DownloadRetryPolicy(BaseModel):
    max_retries: int = Field(default=3, ge=0, le=10)
    backoff_seconds: int = Field(default=60, ge=10, le=3600)
    retry_on_error: bool = True


# ============================================================================
# SOURCE HEALTH MONITORING
# ============================================================================

class SourceHealth(BaseModel):
    source_id: str
    status: str  # healthy, degraded, down
    latency_ms: Optional[float]
    uptime_percent: float
    last_checked: str
    error_count_24h: int


# ============================================================================
# SOURCE LATENCY TRACKING
# ============================================================================

class SourceLatency(BaseModel):
    source_id: str
    avg_latency_ms: float
    min_latency_ms: float
    max_latency_ms: float
    sample_count: int


# ============================================================================
# AUTOMATED FAILOVER
# ============================================================================

class FailoverRule(BaseModel):
    source_id: str
    fallback_source: str
    threshold: float = 0.5  # error rate threshold
    enabled: bool = True


# ============================================================================
# CACHE INVALIDATION BY TAG
# ============================================================================

class CacheInvalidation(BaseModel):
    tag: str
    pattern: Optional[str] = None


# ============================================================================
# CACHE WARMING
# ============================================================================

class CacheWarmRequest(BaseModel):
    queries: list[str]
    source: str = "youtube"
    limit_per_query: int = 5


# ============================================================================
# SEARCH HISTORY
# ============================================================================

class SearchHistoryEntry(BaseModel):
    id: str
    user_id: int
    query: str
    source: Optional[str]
    results_count: int
    timestamp: str


# ============================================================================
# SAVED SEARCHES
# ============================================================================

class SavedSearch(BaseModel):
    id: str
    user_id: int
    name: str
    query: str
    source: Optional[str]
    created_at: str


class SavedSearchCreate(BaseModel):
    name: str
    query: str
    source: Optional[str] = None


# ============================================================================
# SEARCH AUTOCOMPLETE
# ============================================================================

class AutocompleteRequest(BaseModel):
    query: str
    source: Optional[str] = None
    limit: int = Field(default=10, ge=1, le=50)


# ============================================================================
# TRENDING SEARCHES
# ============================================================================

class TrendingSearch(BaseModel):
    query: str
    count: int
    trend: str  # up, down, stable


# ============================================================================
# POPULAR CONTENT
# ============================================================================

class PopularContent(BaseModel):
    title: str
    url: str
    source: str
    download_count: int
    rating: Optional[float]


# ============================================================================
# USER ACTIVITY FEED
# ============================================================================

class ActivityFeedEntry(BaseModel):
    id: str
    user_id: int
    action: str  # download, search, key_create, etc.
    details: dict
    timestamp: str


# ============================================================================
# USAGE REPORTS CSV
# ============================================================================

class UsageReport(BaseModel):
    report_id: str
    user_id: int
    period: str  # daily, weekly, monthly
    format: str = "csv"
    download_url: str
    expires_at: str


# ============================================================================
# KEY SCOPE INHERITANCE / CUSTOM SCOPES
# ============================================================================

class KeyScopes(BaseModel):
    key_id: str
    scopes: list[str]


# ============================================================================
# KEY LAST-USED TRACKING
# ============================================================================

class KeyUsage(BaseModel):
    key_id: str
    last_used: Optional[str]
    total_requests: int
    requests_today: int
    requests_month: int


# ============================================================================
# SUSPICIOUS ACTIVITY DETECTION
# ============================================================================

class SuspiciousActivity(BaseModel):
    id: str
    user_id: Optional[int]
    ip_address: str
    activity_type: str
    risk_score: float = Field(..., ge=0, le=100)
    detected_at: str
    action_taken: str  # none, warn, block, require_2fa


# ============================================================================
# DOWNLOAD CONCURRENCY PER KEY
# ============================================================================

class DownloadConcurrency(BaseModel):
    key_id: str
    max_concurrent: int = Field(..., ge=1, le=20)


# ============================================================================
# FILE TYPE FILTERING
# ============================================================================

class FileTypeFilter(BaseModel):
    allowed_extensions: list[str]  # e.g. [".mp3", ".m4a", ".flac"]
    blocked_extensions: list[str] = []


# ============================================================================
# VIRUS SCAN (placeholder)
# ============================================================================

class VirusScanResult(BaseModel):
    file_path: str
    clean: bool
    threats: list[str] = []
    scanned_at: str


# ============================================================================
# CONTENT MODERATION QUEUE
# ============================================================================

class ModerationItem(BaseModel):
    id: str
    content_type: str  # track, playlist, comment
    content_id: str
    reporter_id: Optional[int]
    reason: str
    status: str  # pending, approved, rejected
    created_at: str


class ModerationAction(BaseModel):
    item_id: str
    action: str  # approve, reject, ban
    moderator_id: int
    reason: Optional[str] = None


# ============================================================================
# WATCHDOG / KEEP-ALIVE HEALTH
# ============================================================================

class ComponentHealthResponse(BaseModel):
    name: str
    healthy: bool
    last_check: float
    error: Optional[str] = None
    failure_count: int = 0
    details: dict = {}


class WatchdogHealthResponse(BaseModel):
    status: str  # healthy, degraded
    uptime_seconds: float
    check_interval: float
    components: dict[str, ComponentHealthResponse]
