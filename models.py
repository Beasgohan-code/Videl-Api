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
    name: str
    domains: list[str]
    supports_search: bool
    supports_playlist: bool
    supports_album: bool
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
