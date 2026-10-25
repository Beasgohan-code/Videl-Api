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
    duration: Optional[int] = None  # seconds
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
    abr: Optional[float] = None  # audio bitrate
    filesize: Optional[int] = None
    is_playlist: bool = False
    is_album: bool = False
    track_number: Optional[int] = None
    album: Optional[str] = None
    artist: Optional[str] = None
    genres: list[str] = []
    release_year: Optional[int] = None
    webpages: list[str] = []
    entries: list[TrackMini] = []  # playlist/album tracks


# ---------------------------------------------------------------------------
# Download / stream
# ---------------------------------------------------------------------------

class DownloadRequest(BaseModel):
    url: str = Field(..., min_length=1, description="Media URL or video/track id")
    source: Optional[str] = Field(default=None, description="Force a source id")
    format: str = Field(default="bestaudio/best", description="yt-dlp format selector")
    quality: Optional[str] = Field(default=None, description="best/worst or audio bitrate hint")


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


# ---------------------------------------------------------------------------
# Lyrics
# ---------------------------------------------------------------------------

class LyricsRequest(BaseModel):
    url: str = Field(..., min_length=1, description="Media URL or video/track id")


class LyricsResponse(BaseModel):
    id: str
    title: str
    source: str
    source_name: Optional[str] = None
    lyrics: Optional[str] = None
    lyrics_provider: Optional[str] = None


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



