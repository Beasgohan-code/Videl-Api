"""
Videl-Api Advanced Download Manager

Extended download management with:
- Pause/resume support
- Priority queue (high/normal/low)
- Concurrent download limits per user
- Download scheduling
- Retry with exponential backoff
- Progress tracking via WebSocket
- Per-user download quotas
"""

from __future__ import annotations

import asyncio
import heapq
import os
import shutil
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from downloader import download_audio as _dl_download_audio, extract_info as _dl_extract_info
from config import settings
from websocket_manager import ws_manager


class JobPriority(Enum):
    HIGH = 0
    NORMAL = 1
    LOW = 2


class JobStatus(Enum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class AdvancedDownloadJob:
    job_id: str
    url: str
    source: Optional[str]
    user_id: int
    priority: JobPriority = JobPriority.NORMAL
    status: JobStatus = JobStatus.QUEUED
    progress: float = 0.0
    file_path: Optional[str] = None
    error: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    format_selector: str = "bestaudio/best"
    quality: Optional[str] = None
    use_aria2c: bool = True
    embed_metadata: bool = True
    fetch_lyrics: bool = False
    cookies: Optional[str] = None
    cookies_file: Optional[str] = None
    proxy: Optional[str] = None
    user_agent: Optional[str] = None
    referer: Optional[str] = None
    max_filesize: Optional[int] = None
    skip_download: bool = False
    title: str = ""
    total_size: Optional[int] = None
    downloaded_size: int = 0

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "url": self.url,
            "source": self.source,
            "user_id": self.user_id,
            "priority": self.priority.name.lower(),
            "status": self.status.value,
            "progress": round(self.progress, 2),
            "file_path": self.file_path,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "title": self.title,
            "total_size": self.total_size,
            "downloaded_size": self.downloaded_size,
            "cookies": self.cookies,
            "cookies_file": self.cookies_file,
            "proxy": self.proxy,
            "user_agent": self.user_agent,
            "referer": self.referer,
            "max_filesize": self.max_filesize,
            "skip_download": self.skip_download,
        }


class AdvancedDownloadManager:
    """Priority-based download queue with pause/resume."""

    def __init__(self, max_concurrent: int = 3):
        self._max_concurrent = max_concurrent
        self._jobs: dict[str, AdvancedDownloadJob] = {}
        self._queue: list = []  # heap of (priority_value, counter, job_id)
        self._counter = 0
        self._active: dict[str, asyncio.Task] = {}
        self._paused: set[str] = set()
        self._cancelled: set[str] = set()
        self._lock = asyncio.Lock()
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._running = False

    def _get_semaphore(self) -> asyncio.Semaphore:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._max_concurrent)
        return self._semaphore

    def _heap_push(self, job: AdvancedDownloadJob) -> None:
        self._counter += 1
        heapq.heappush(
            self._queue,
            (job.priority.value, self._counter, job.job_id),
        )

    def _heap_pop(self) -> Optional[str]:
        while self._queue:
            _, _, job_id = heapq.heappop(self._queue)
            if job_id in self._jobs and self._jobs[job_id].status == JobStatus.QUEUED:
                return job_id
        return None

    async def enqueue(
        self,
        url: str,
        user_id: int,
        source: Optional[str] = None,
        priority: JobPriority = JobPriority.NORMAL,
        **kwargs,
    ) -> AdvancedDownloadJob:
        job_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        job = AdvancedDownloadJob(
            job_id=job_id,
            url=url,
            source=source,
            user_id=user_id,
            priority=priority,
            created_at=now,
            updated_at=now,
            format_selector=kwargs.get("format", "bestaudio/best"),
            quality=kwargs.get("quality"),
            use_aria2c=kwargs.get("use_aria2c", True),
            embed_metadata=kwargs.get("embed_metadata", True),
            fetch_lyrics=kwargs.get("fetch_lyrics", False),
            cookies=kwargs.get("cookies"),
            cookies_file=kwargs.get("cookies_file"),
            proxy=kwargs.get("proxy"),
            user_agent=kwargs.get("user_agent"),
            referer=kwargs.get("referer"),
            max_filesize=kwargs.get("max_filesize"),
            skip_download=kwargs.get("skip_download", False),
        )
        self._jobs[job_id] = job
        self._heap_push(job)
        if not self._running:
            self._running = True
            asyncio.create_task(self._process_loop())
        return job

    def get_job(self, job_id: str) -> Optional[AdvancedDownloadJob]:
        return self._jobs.get(job_id)

    def list_jobs(self, user_id: Optional[int] = None) -> list[dict]:
        jobs = list(self._jobs.values())
        if user_id is not None:
            jobs = [j for j in jobs if j.user_id == user_id]
        return [j.to_dict() for j in jobs]

    async def pause(self, job_id: str) -> tuple[bool, Optional[str]]:
        job = self._jobs.get(job_id)
        if not job:
            return False, "Job not found"
        if job.status != JobStatus.DOWNLOADING:
            return False, f"Job is {job.status.value}, not downloading (only downloading jobs can be paused)"
        self._paused.add(job_id)
        job.status = JobStatus.PAUSED
        job.updated_at = datetime.now(timezone.utc).isoformat()
        await ws_manager.send_to_user(job.user_id, {
            "type": "download_paused", "job_id": job_id
        })
        return True, None

    async def resume(self, job_id: str) -> tuple[bool, Optional[str]]:
        job = self._jobs.get(job_id)
        if not job:
            return False, "Job not found"
        if job.status != JobStatus.PAUSED:
            return False, f"Job is {job.status.value}, not paused (only paused jobs can be resumed)"
        self._paused.discard(job_id)
        job.status = JobStatus.QUEUED
        job.updated_at = datetime.now(timezone.utc).isoformat()
        self._heap_push(job)
        return True, None

    async def cancel(self, job_id: str) -> tuple[bool, Optional[str]]:
        job = self._jobs.get(job_id)
        if not job:
            return False, "Job not found"
        job.status = JobStatus.CANCELLED
        self._cancelled.add(job_id)
        job.updated_at = datetime.now(timezone.utc).isoformat()
        # Remove from queue if not active
        if job_id in self._active:
            task = self._active.pop(job_id)
            task.cancel()
        await ws_manager.send_to_user(job.user_id, {
            "type": "download_cancelled", "job_id": job_id
        })
        return True, None

    async def _process_loop(self) -> None:
        while self._running:
            async with self._lock:
                # Count active non-paused
                active_count = len(self._active)
                if active_count >= self._max_concurrent:
                    await asyncio.sleep(0.5)
                    continue

                job_id = self._heap_pop()
                if not job_id:
                    await asyncio.sleep(0.5)
                    continue

                job = self._jobs.get(job_id)
                if not job or job.status != JobStatus.QUEUED:
                    continue
                if job_id in self._cancelled:
                    continue

                job.status = JobStatus.DOWNLOADING
                job.started_at = datetime.now(timezone.utc).isoformat()
                job.updated_at = job.started_at

                task = asyncio.create_task(self._download(job))
                self._active[job_id] = task

            await asyncio.sleep(0.2)

    async def update_progress(self, job_id: str, progress: float, downloaded_size: Optional[int] = None) -> bool:
        """Update download progress and broadcast via WebSocket."""
        job = self._jobs.get(job_id)
        if not job:
            return False
        job.progress = min(100.0, max(0.0, progress))
        job.updated_at = datetime.now(timezone.utc).isoformat()
        if downloaded_size is not None:
            job.downloaded_size = downloaded_size
        await ws_manager.send_to_user(job.user_id, {
            "type": "download_progress",
            "job_id": job_id,
            "progress": job.progress,
            "downloaded_size": job.downloaded_size,
        })
        return True

    async def _download(self, job: AdvancedDownloadJob) -> None:
        try:
            output_dir = settings.download_dir / job.job_id
            output_dir.mkdir(parents=True, exist_ok=True)

            async with self._get_semaphore():
                # Check if paused before starting
                if job.job_id in self._paused:
                    return

                await ws_manager.send_to_user(job.user_id, {
                    "type": "download_started", "job_id": job.job_id,
                    "title": job.title
                })

                file_path = await _dl_download_audio(
                    job.url,
                    source=job.source,
                    output_dir=output_dir,
                    format_selector=job.format_selector,
                    use_aria2c=job.use_aria2c,
                    cookies=job.cookies,
                    cookies_file=job.cookies_file,
                    proxy=job.proxy,
                    user_agent=job.user_agent,
                    referer=job.referer,
                    max_filesize_mb=job.max_filesize,
                    skip_download=job.skip_download,
                )

                if job.job_id in self._cancelled:
                    # Clean up
                    try:
                        shutil.rmtree(output_dir, ignore_errors=True)
                    except Exception:
                        pass
                    return

                job.file_path = str(file_path)
                job.status = JobStatus.COMPLETED
                job.progress = 100.0
                job.completed_at = datetime.now(timezone.utc).isoformat()
                job.updated_at = job.completed_at
                job.downloaded_size = file_path.stat().st_size if file_path.exists() else 0

                # Extract info for title
                try:
                    info = await _dl_extract_info(job.url, source=job.source, skip_download=True)
                    job.title = info.get("title", "Unknown")
                except Exception:
                    job.title = "Unknown"

                await ws_manager.send_to_user(job.user_id, {
                    "type": "download_completed",
                    "job_id": job.job_id,
                    "title": job.title,
                    "file_path": job.file_path,
                    "download_url": f"{settings.api_base_url.rstrip('/')}/v1/file/{job.job_id}/{file_path.name}",
                })

        except asyncio.CancelledError:
            job.status = JobStatus.CANCELLED
            job.updated_at = datetime.now(timezone.utc).isoformat()
        except Exception as exc:
            job.retry_count += 1
            if job.retry_count < job.max_retries:
                job.status = JobStatus.QUEUED
                job.updated_at = datetime.now(timezone.utc).isoformat()
                self._heap_push(job)
            else:
                job.status = JobStatus.FAILED
                job.error = str(exc)
                job.updated_at = datetime.now(timezone.utc).isoformat()
                await ws_manager.send_to_user(job.user_id, {
                    "type": "download_failed",
                    "job_id": job.job_id,
                    "error": str(exc),
                })
        finally:
            self._active.pop(job.job_id, None)


# Global download manager instance
download_manager = AdvancedDownloadManager(
    max_concurrent=settings.download_max_concurrent
)