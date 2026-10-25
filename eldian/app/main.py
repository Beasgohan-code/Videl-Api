# MIT License - Copyright (c) 2026 Videl Network

from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI
from fastapi.background import BackgroundTask
from fastapi.responses import FileResponse

from .db import ensure_indexes
from .schemas import VideoRequest
from .security import validate_api_key
from .youtube import cleanup_download, cleanup_stale_downloads, download_audio


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_indexes()
    cleanup_stale_downloads(Path("downloads"))
    yield


app = FastAPI(title="Videl Music API", version="1.0.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/v1/track/by-video-id")
async def fetch_track(payload: VideoRequest, _: dict = Depends(validate_api_key)):
    temp_dir = Path("downloads") / uuid4().hex
    file_path = download_audio(payload.video_id, temp_dir)
    return FileResponse(
        path=file_path,
        filename=file_path.name,
        media_type="application/octet-stream",
        background=BackgroundTask(cleanup_download, file_path),
    )
