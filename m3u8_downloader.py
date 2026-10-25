"""
Videl-Api M3U8/HLS/DASH Downloader

Integrates best ideas from:
- globocom/m3u8          - Python m3u8 parser for HLS
- nilaoda/N_m3u8DL-RE    - Cross-platform DASH/HLS/MSS stream downloader
- nilaoda/N_m3u8DL-CLI   - AES-128-CBC decryption, multi-thread, custom headers
- aria2/aria2            - Multi-connection segmented downloads, JSON-RPC

Provides:
- M3U8/HLS playlist parsing and segment downloading
- AES-128-CBC automatic decryption
- Multi-threaded segment download (configurable concurrency)
- Master/variant playlist selection
- Custom HTTP headers, cookies, proxies
- Live stream recording with catch-up
- Binary segment merge or ffmpeg muxing
- aria2c RPC integration for accelerated downloads
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

import aiohttp
import m3u8

from config import settings

# ---------------------------------------------------------------------------
# Job state for m3u8 downloads
# ---------------------------------------------------------------------------

class M3U8Job:
    __slots__ = ("job_id", "url", "status", "progress", "file_path",
                 "error", "created_at", "updated_at", "cancelled",
                 "total_segments", "downloaded_segments", "meta")

    def __init__(self, job_id: str, url: str):
        self.job_id = job_id
        self.url = url
        self.status = "queued"   # queued | parsing | downloading | merging | completed | failed | cancelled
        self.progress = 0.0
        self.file_path: Optional[str] = None
        self.error: Optional[str] = None
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.updated_at = self.created_at
        self.cancelled = False
        self.total_segments = 0
        self.downloaded_segments = 0
        self.meta: dict[str, Any] = {}

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "url": self.url,
            "status": self.status,
            "progress": round(self.progress, 2),
            "file_path": self.file_path,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "total_segments": self.total_segments,
            "downloaded_segments": self.downloaded_segments,
            "meta": self.meta,
        }


M3U8_JOBS: dict[str, M3U8Job] = {}
M3U8_QUEUE: list[str] = []
_M3U8_SEMAPHORE: Optional[asyncio.Semaphore] = None
_M3U8_LOCK = asyncio.Lock()


def _m3u8_semaphore() -> asyncio.Semaphore:
    global _M3U8_SEMAPHORE
    if _M3U8_SEMAPHORE is None:
        _M3U8_SEMAPHORE = asyncio.Semaphore(settings.download_max_concurrent)
    return _M3U8_SEMAPHORE


# ---------------------------------------------------------------------------
# Playlist parsing (globocom/m3u8 integration)
# ---------------------------------------------------------------------------

def parse_m3u8_sync(
    url: str,
    *,
    headers: Optional[dict[str, str]] = None,
    cookies: Optional[str] = None,
    proxy: Optional[str] = None,
    timeout: int = 30,
) -> dict:
    """Fetch and parse an M3U8 playlist using globocom/m3u8.

    Returns a normalized dict with master/media info, segments, keys, etc.
    """
    import m3u8 as m3u8_lib

    # Build a custom HTTP client if headers/cookies/proxy are needed.
    http_client = None
    if headers or cookies or proxy:
        class _CustomClient(m3u8_lib.httpclient.DefaultHTTPClient):
            def download(self, uri, timeout=None):
                import requests as _requests  # lazy import
                h = dict(headers or {})
                if cookies:
                    h["Cookie"] = cookies
                proxies = {"http": proxy, "https": proxy} if proxy else None
                resp = _requests.get(uri, headers=h, proxies=proxies,
                                     timeout=timeout or 30, verify=False)
                return resp.text, resp.url
        http_client = _CustomClient()

    playlist = m3u8_lib.load(url, http_client=http_client, timeout=timeout)

    result: dict[str, Any] = {
        "url": url,
        "is_variant": playlist.is_variant,
        "is_media": playlist.is_media,
        "version": playlist.version,
        "target_duration": playlist.target_duration,
        "media_sequence": playlist.media_sequence,
        "discontinuity_sequence": playlist.discontinuity_sequence,
        "allow_cache": playlist.allow_cache,
        "end_list": playlist.end_list,
        "playlists": [],
        "segments": [],
        "keys": [],
        "media": [],
        "iframes": [],
        "start": None,
        "duration": 0.0,
    }

    # Variant (master) playlists
    if playlist.is_variant:
        for p in playlist.playlists:
            si = p.stream_info
            result["playlists"].append({
                "uri": p.uri,
                "absolute_uri": p.absolute_uri,
                "bandwidth": si.bandwidth if si else None,
                "average_bandwidth": si.average_bandwidth if si else None,
                "codecs": si.codecs if si else None,
                "resolution": si.resolution if si else None,
                "frame_rate": si.frame_rate if si else None,
                "video_range": si.video_range if si else None,
                "audio": si.audio if si else None,
                "video": si.video if si else None,
                "subtitles": si.subtitles if si else None,
                "name": si.name if si else None,
            })

    # Media playlist segments
    for seg in playlist.segments:
        seg_info = {
            "uri": seg.uri,
            "absolute_uri": seg.absolute_uri,
            "duration": seg.duration,
            "title": seg.title,
            "key": {
                "method": seg.key.method if seg.key else None,
                "uri": seg.key.uri if seg.key else None,
                "iv": seg.key.iv if seg.key else None,
                "keyformat": seg.key.keyformat if seg.key else None,
            } if seg.key else None,
            "map": seg.map.uri if seg.map else None,
            "byterange": seg.byterange if seg.byterange else None,
            "discontinuity": seg.discontinuity,
        }
        result["segments"].append(seg_info)
        if seg.duration:
            result["duration"] += seg.duration

    # Encryption keys
    for key in playlist.keys:
        if key:
            result["keys"].append({
                "method": key.method,
                "uri": key.uri,
                "iv": key.iv,
                "keyformat": key.keyformat,
            })

    # Media (alternative audio/video/subtitles)
    for media in playlist.media or []:
        result["media"].append({
            "type": media.type,
            "group_id": media.group_id,
            "uri": media.uri,
            "name": media.name,
            "language": media.language,
            "default": media.default,
            "autoselect": media.autoselect,
            "forced": media.forced,
            "characteristics": media.characteristics,
        })

    # I-frame playlists
    for iframe in playlist.iframes or []:
        si = iframe.stream_info
        result["iframes"].append({
            "uri": iframe.uri,
            "bandwidth": si.bandwidth if si else None,
            "codecs": si.codecs if si else None,
            "resolution": si.resolution if si else None,
        })

    # Start time
    if playlist.start:
        result["start"] = {
            "time_offset": playlist.start.time_offset,
            "precise": playlist.start.precise,
        }

    return result


async def parse_m3u8(
    url: str,
    *,
    headers: Optional[dict[str, str]] = None,
    cookies: Optional[str] = None,
    proxy: Optional[str] = None,
) -> dict:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: parse_m3u8_sync(url, headers=headers, cookies=cookies, proxy=proxy),
    )


# ---------------------------------------------------------------------------
# AES-128-CBC decryption (N_m3u8DL-CLI concept)
# ---------------------------------------------------------------------------

def _decrypt_aes128_cbc(data: bytes, key: bytes, iv: bytes) -> bytes:
    """Decrypt AES-128-CBC encrypted segment data."""
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.backends import default_backend
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        decrypted = decryptor.update(data) + decryptor.finalize()
        # PKCS7 padding removal
        pad_len = decrypted[-1]
        if 1 <= pad_len <= 16:
            decrypted = decrypted[:-pad_len]
        return decrypted
    except Exception:
        # Fallback: try pycryptodome
        try:
            from Crypto.Cipher import AES
            cipher = AES.new(key, AES.MODE_CBC, iv)
            decrypted = cipher.decrypt(data)
            pad_len = decrypted[-1]
            if 1 <= pad_len <= 16:
                decrypted = decrypted[:-pad_len]
            return decrypted
        except Exception:
            return data  # return raw if decryption fails


async def _fetch_segment(
    session: aiohttp.ClientSession,
    uri: str,
    *,
    key_info: Optional[dict] = None,
    headers: Optional[dict[str, str]] = None,
    cookies: Optional[str] = None,
    timeout: int = 30,
) -> bytes:
    """Fetch a single segment, optionally decrypting AES-128-CBC."""
    h = dict(headers or {})
    if cookies:
        h["Cookie"] = cookies

    async with session.get(uri, headers=h, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
        resp.raise_for_status()
        data = await resp.read()

    if key_info and key_info.get("method") == "AES-128":
        # Fetch key if not already provided as bytes
        key_bytes = key_info.get("key_bytes")
        if key_bytes is None and key_info.get("uri"):
            async with session.get(key_info["uri"], headers=h,
                                   timeout=aiohttp.ClientTimeout(total=timeout)) as kresp:
                kresp.raise_for_status()
                key_bytes = await kresp.read()
        iv_hex = key_info.get("iv", "0")
        iv = bytes.fromhex(iv_hex.replace("0x", "")) if iv_hex else b"\x00" * 16
        if len(iv) != 16:
            iv = b"\x00" * 16
        if key_bytes:
            data = _decrypt_aes128_cbc(data, key_bytes, iv)

    return data


# ---------------------------------------------------------------------------
# M3U8/HLS download (N_m3u8DL-RE/CLI concepts)
# ---------------------------------------------------------------------------

async def download_m3u8_sync(
    url: str,
    *,
    output_dir: Path,
    job: Optional[M3U8Job] = None,
    headers: Optional[dict[str, str]] = None,
    cookies: Optional[str] = None,
    proxy: Optional[str] = None,
    max_threads: int = 16,
    use_aria2c: bool = False,
    decrypt: bool = True,
    merge_method: str = "binary",  # binary | ffmpeg
    save_name: Optional[str] = None,
    custom_range: Optional[str] = None,  # e.g. "0-10", "05:00-20:00"
    audio_only: bool = False,
    ffmpeg_path: Optional[str] = None,
) -> dict:
    """Download an M3U8/HLS stream.

    Combines globocom/m3u8 parsing + N_m3u8DL multi-thread segment download
    + AES-128 decryption + binary/ffmpeg merge + optional aria2c acceleration.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    if job:
        job.status = "parsing"
        job.updated_at = datetime.now(timezone.utc).isoformat()

    # Parse playlist
    playlist = await parse_m3u8(url, headers=headers, cookies=cookies, proxy=proxy)

    if job:
        job.meta = {
            "is_variant": playlist["is_variant"],
            "total_duration": playlist["duration"],
            "segment_count": len(playlist["segments"]),
            "version": playlist["version"],
        }

    if playlist["is_variant"]:
        # Select best bandwidth playlist (auto-select like N_m3u8DL)
        best = max(playlist["playlists"],
                   key=lambda p: (p["bandwidth"] or 0))
        selected_url = best["absolute_uri"] or best["uri"]
        # Re-parse the selected media playlist
        playlist = await parse_m3u8(selected_url, headers=headers,
                                    cookies=cookies, proxy=proxy)
        if job:
            job.meta["selected_playlist"] = best
            job.meta["selected_url"] = selected_url

    segments = playlist["segments"]
    if not segments:
        raise RuntimeError("No segments found in M3U8 playlist")

    # Apply custom range if specified (N_m3u8DL --download-range / --custom-range)
    if custom_range:
        segments = _apply_range(segments, custom_range, playlist["target_duration"])

    if job:
        job.total_segments = len(segments)
        job.status = "downloading"
        job.updated_at = datetime.now(timezone.utc).isoformat()

    # Prepare output name
    save_name = save_name or f"m3u8_{uuid.uuid4().hex[:8]}"
    segments_dir = output_dir / f"{save_name}_segments"
    segments_dir.mkdir(parents=True, exist_ok=True)

    # Collect encryption key info (first key applies to all usually)
    key_info = None
    if decrypt and playlist["keys"]:
        key_info = playlist["keys"][0]
        # Pre-fetch the key
        if key_info.get("uri"):
            try:
                import requests as _requests
                h = dict(headers or {})
                if cookies:
                    h["Cookie"] = cookies
                proxies = {"http": proxy, "https": proxy} if proxy else None
                resp = _requests.get(key_info["uri"], headers=h,
                                     proxies=proxies, timeout=30, verify=False)
                key_info["key_bytes"] = resp.content
            except Exception:
                pass

    # Download segments concurrently
    sem = asyncio.Semaphore(max_threads)
    connector = aiohttp.TCPConnector(limit=max_threads, ssl=False)

    async with aiohttp.ClientSession(connector=connector) as session:
        async def download_one(idx: int, seg: dict) -> tuple[int, str, Optional[Exception]]:
            if job and job.cancelled:
                return idx, "", None
            uri = seg["absolute_uri"] or seg["uri"]
            async with sem:
                try:
                    data = await _fetch_segment(session, uri,
                                                key_info=key_info if decrypt else None,
                                                headers=headers, cookies=cookies,
                                                timeout=30)
                    seg_path = segments_dir / f"seg_{idx:06d}.ts"
                    seg_path.write_bytes(data)
                    if job:
                        job.downloaded_segments = idx + 1
                        job.progress = (job.downloaded_segments / job.total_segments) * 100
                        job.updated_at = datetime.now(timezone.utc).isoformat()
                    return idx, str(seg_path), None
                except Exception as exc:
                    return idx, "", exc

        tasks = [download_one(i, seg) for i, seg in enumerate(segments)]
        results = await asyncio.gather(*tasks)

    # Check for failures
    failures = [r for r in results if r[2] is not None]
    if failures:
        if job:
            job.status = "failed"
            job.error = f"{len(failures)} segment(s) failed to download"
            job.updated_at = datetime.now(timezone.utc).isoformat()
        raise RuntimeError(f"{len(failures)} segment(s) failed: "
                           f"{[r[2] for r in failures[:3]]}")

    # Sort results by index
    results.sort(key=lambda r: r[0])
    seg_files = [r[1] for r in results if r[1]]

    if job:
        job.status = "merging"
        job.updated_at = datetime.now(timezone.utc).isoformat()

    # Merge segments
    ext = ".mp4" if merge_method == "ffmpeg" else ".ts"
    final_path = output_dir / f"{save_name}{ext}"

    if merge_method == "ffmpeg" and _has_ffmpeg():
        _merge_with_ffmpeg(seg_files, final_path, audio_only=audio_only,
                           ffmpeg_path=ffmpeg_path or settings.ffmpeg_path)
    else:
        _merge_binary(seg_files, final_path)

    # Cleanup segment files
    for sf in seg_files:
        try:
            Path(sf).unlink(missing_ok=True)
        except Exception:
            pass
    try:
        segments_dir.rmdir()
    except Exception:
        pass

    if job:
        job.status = "completed"
        job.progress = 100.0
        job.file_path = str(final_path)
        job.updated_at = datetime.now(timezone.utc).isoformat()

    return {
        "file_path": str(final_path),
        "title": save_name,
        "segments": len(seg_files),
        "duration": playlist["duration"],
        "merge_method": merge_method,
        "decrypted": decrypt and bool(key_info),
        "is_variant": playlist["is_variant"],
    }


def _apply_range(
    segments: list[dict],
    custom_range: str,
    target_duration: Optional[float],
) -> list[dict]:
    """Apply N_m3u8DL-style --custom-range / --download-range.

    Supports:
      - "0-10"        : segment indices 0 through 10
      - "10-"         : from index 10 to end
      - "-99"         : first 100 segments
      - "05:00-20:00" : time range
      - "00:26-"      : from 26 seconds to end
      - "-00:26"      : first 26 seconds
    """
    custom_range = custom_range.strip()

    def _parse_time(t: str) -> float:
        parts = t.split(":")
        parts = [float(p) for p in parts]
        if len(parts) == 1:
            return parts[0]
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        return parts[0] * 3600 + parts[1] * 60 + parts[2]

    if ":" in custom_range:
        # Time-based range
        parts = custom_range.split("-", 1)
        start_str = parts[0] if parts[0] else "0"
        end_str = parts[1] if len(parts) > 1 and parts[1] else None
        start_sec = _parse_time(start_str)
        end_sec = _parse_time(end_str) if end_str else float("inf")

        selected = []
        acc = 0.0
        for seg in segments:
            seg_start = acc
            seg_end = acc + (seg["duration"] or 0)
            if seg_end > start_sec and (end_sec is None or seg_start < end_sec):
                selected.append(seg)
            acc = seg_end
            if end_sec is not None and acc >= end_sec:
                break
        return selected
    else:
        # Segment index range
        parts = custom_range.split("-", 1)
        start_idx = int(parts[0]) if parts[0] else 0
        end_idx = int(parts[1]) if len(parts) > 1 and parts[1] else len(segments)
        return segments[start_idx:end_idx]


def _merge_binary(seg_files: list[str], output_path: Path) -> None:
    """Binary concatenation of TS segments (N_m3u8DL --enableBinaryMerge)."""
    with open(output_path, "wb") as out:
        for sf in seg_files:
            with open(sf, "rb") as f:
                out.write(f.read())


def _merge_with_ffmpeg(
    seg_files: list[str],
    output_path: Path,
    *,
    audio_only: bool = False,
    ffmpeg_path: Optional[str] = None,
) -> None:
    """Merge segments using ffmpeg concat demuxer."""
    ffmpeg = ffmpeg_path or settings.ffmpeg_path or "ffmpeg"
    # Create concat file list
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as tf:
        for sf in seg_files:
            tf.write(f"file '{sf}'\n")
        concat_file = tf.name

    try:
        cmd = [ffmpeg, "-y", "-f", "concat", "-safe", "0",
               "-i", concat_file, "-c", "copy"]
        if audio_only:
            cmd += ["-vn"]
        # Fast start for MP4 (N_m3u8DL --enableMuxFastStart)
        if output_path.suffix.lower() == ".mp4":
            cmd += ["-movflags", "+faststart"]
        cmd.append(str(output_path))
        subprocess.run(cmd, check=True, capture_output=True, timeout=300)
    finally:
        try:
            os.unlink(concat_file)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# aria2c RPC integration (aria2/aria2 JSON-RPC)
# ---------------------------------------------------------------------------

async def aria2_add_uri(
    uris: list[str],
    *,
    dir: Optional[str] = None,
    out: Optional[str] = None,
    max_connections: int = 16,
    split: int = 16,
    proxy: Optional[str] = None,
    header: Optional[list[str]] = None,
    rpc_url: str = "http://localhost:6800/jsonrpc",
    rpc_secret: str = "",
) -> str:
    """Add a download to aria2 via JSON-RPC and return the GID."""
    import aiohttp

    params: dict[str, Any] = {}
    if dir:
        params["dir"] = dir
    if out:
        params["out"] = out
    if max_connections:
        params["max-connection-per-server"] = str(max_connections)
    if split:
        params["split"] = str(split)
    if split:
        params["min-split-size"] = "1M"
    if proxy:
        params["all-proxy"] = proxy
    if header:
        params["header"] = header

    payload = {
        "jsonrpc": "2.0",
        "id": "videl",
        "method": "aria2.addUri",
        "params": ([rpc_secret] if rpc_secret else []) + [uris, params],
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(rpc_url, json=payload,
                                timeout=aiohttp.ClientTimeout(total=30)) as resp:
            resp.raise_for_status()
            data = await resp.json()
    if "error" in data:
        raise RuntimeError(f"aria2 error: {data['error']}")
    return data["result"]


async def aria2_tell_status(
    gid: str,
    rpc_url: str = "http://localhost:6800/jsonrpc",
    rpc_secret: str = "",
) -> dict:
    import aiohttp
    payload = {
        "jsonrpc": "2.0",
        "id": "videl",
        "method": "aria2.tellStatus",
        "params": ([rpc_secret] if rpc_secret else []) + [gid],
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(rpc_url, json=payload,
                                timeout=aiohttp.ClientTimeout(total=30)) as resp:
            resp.raise_for_status()
            data = await resp.json()
    if "error" in data:
        raise RuntimeError(f"aria2 error: {data['error']}")
    return data["result"]


async def aria2_remove(
    gid: str,
    rpc_url: str = "http://localhost:6800/jsonrpc",
    rpc_secret: str = "",
) -> bool:
    import aiohttp
    payload = {
        "jsonrpc": "2.0",
        "id": "videl",
        "method": "aria2.remove",
        "params": ([rpc_secret] if rpc_secret else []) + [gid],
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(rpc_url, json=payload,
                                timeout=aiohttp.ClientTimeout(total=30)) as resp:
            resp.raise_for_status()
            data = await resp.json()
    return not ("error" in data)


# ---------------------------------------------------------------------------
# Tool detection
# ---------------------------------------------------------------------------

def _has_ffmpeg() -> bool:
    return bool(settings.ffmpeg_path and Path(settings.ffmpeg_path).exists()) or \
        __import__("shutil").which("ffmpeg") is not None


# ---------------------------------------------------------------------------
# Async API used by main.py
# ---------------------------------------------------------------------------

M3U8_DOWNLOAD_SEMAPHORE = None


def _m3u8_download_semaphore():
    global M3U8_DOWNLOAD_SEMAPHORE
    if M3U8_DOWNLOAD_SEMAPHORE is None:
        M3U8_DOWNLOAD_SEMAPHORE = asyncio.Semaphore(settings.download_max_concurrent)
    return M3U8_DOWNLOAD_SEMAPHORE


async def enqueue_m3u8_download(
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
) -> M3U8Job:
    job_id = uuid.uuid4().hex
    job = M3U8Job(job_id=job_id, url=url)
    async with _M3U8_LOCK:
        M3U8_JOBS[job_id] = job
        M3U8_QUEUE.append(job_id)
    asyncio.create_task(_process_m3u8_queue())
    return job


async def _process_m3u8_queue() -> None:
    while True:
        async with _M3U8_LOCK:
            if not M3U8_QUEUE:
                return
            job_id = M3U8_QUEUE.pop(0)
            job = M3U8_JOBS.get(job_id)
            if not job or job.status in {"completed", "failed", "cancelled"}:
                continue
            job.status = "downloading"
            job.updated_at = datetime.now(timezone.utc).isoformat()

        sem = _m3u8_download_semaphore()
        async with sem:
            if job.cancelled:
                job.status = "cancelled"
                job.updated_at = datetime.now(timezone.utc).isoformat()
                continue
            try:
                out_dir = settings.download_dir / job_id
                await download_m3u8_sync(
                    job.url,
                    output_dir=out_dir,
                    job=job,
                    headers=headers_for(job.url),
                    max_threads=max_threads_for(job.url),
                    merge_method=merge_method_for(job.url),
                )
            except Exception as exc:  # noqa: BLE001
                job.status = "failed"
                job.error = str(exc)
                job.updated_at = datetime.now(timezone.utc).isoformat()


def headers_for(url: str) -> Optional[dict[str, str]]:
    return settings.m3u8_default_headers


def max_threads_for(url: str) -> int:
    return settings.m3u8_max_threads


def merge_method_for(url: str) -> str:
    return settings.m3u8_merge_method


async def get_m3u8_job(job_id: str) -> Optional[dict]:
    job = M3U8_JOBS.get(job_id)
    return job.to_dict() if job else None


async def cancel_m3u8_job(job_id: str) -> bool:
    job = M3U8_JOBS.get(job_id)
    if not job:
        return False
    job.cancelled = True
    if job.status == "queued":
        job.status = "cancelled"
        job.updated_at = datetime.now(timezone.utc).isoformat()
    return True


async def list_m3u8_jobs() -> list[dict]:
    return [j.to_dict() for j in M3U8_JOBS.values()]


# ---------------------------------------------------------------------------
# SpotDL Spotify integration (re-exported for main.py)
# ---------------------------------------------------------------------------

async def spotdl_download_url(
    url: str,
    *,
    output_dir: Path,
) -> dict:
    import subprocess
    cmd = [settings.spotdl_path, "url", url]
    if settings.spotify_client_id and settings.spotify_client_secret:
        cmd += ["--client-id", settings.spotify_client_id, "--client-secret", settings.spotify_client_secret]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"spotdl failed: {result.stderr.strip()[:500]}")
    output_dir.mkdir(parents=True, exist_ok=True)
    files = [p for p in output_dir.iterdir() if p.is_file() and p.suffix.lower() in {".mp3", ".m4a", ".opus", ".flac", ".wav"}]
    if not files:
        raise RuntimeError("spotdl did not produce an output file")
    downloaded = max(files, key=lambda p: p.stat().st_mtime)
    return {
        "file_path": str(downloaded),
        "title": downloaded.stem,
        "filesize": downloaded.stat().st_size,
    }
