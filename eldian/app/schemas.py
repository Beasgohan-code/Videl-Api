# MIT License - Copyright (c) 2026 Videl Network

from pydantic import BaseModel, Field


class VideoRequest(BaseModel):
    video_id: str = Field(..., min_length=5, description="YouTube video ID")


class ApiKeyCreateResponse(BaseModel):
    key: str
    owner_id: int


class ApiKeyRecord(BaseModel):
    key: str
    owner_id: int
    active: bool = True
    created_at: str | None = None
    last_used_at: str | None = None
