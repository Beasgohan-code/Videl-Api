"""Videl-Api security: SSRF guard, credential redaction, URL validation."""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlparse

from fastapi import HTTPException, status
from config import settings

# Redactable credential patterns
_CREDENTIAL_PATTERNS = [
    re.compile(r"(api[_-]?key|apikey|authorization|bearer|token|password|passwd|secret|client[_-]?secret|client_secret)\s*[:=]\s*[^\s&]+", re.IGNORECASE),
    re.compile(r"(vyrn_|videl_|vyt_|vown_|sk_[a-zA-Z0-9]+|ghp_[a-zA-Z0-9]+)", re.IGNORECASE),
]


def redact_credentials(text: str) -> str:
    """Redact credentials from log text."""
    if not settings.credential_redaction:
        return text
    result = text
    for pat in _CREDENTIAL_PATTERNS:
        result = pat.sub(lambda m: m.group(0).split(":")[0] + "=***REDACTED***", result)
    return result


def is_private_host(host: str) -> bool:
    """Check if a host resolves to a private/internal IP (SSRF guard)."""
    if not settings.ssrf_guard:
        return False
    if settings.ssrf_allow_private:
        return False
    try:
        # Remove port if present
        host = host.split(":")[0]
        # Try direct IP
        try:
            ip = ipaddress.ip_address(host)
            return ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_multicast
        except ValueError:
            pass
        # DNS resolution check for common private names
        private_suffixes = (".local", ".internal", ".intranet", ".corp", ".home.arpa")
        if host.endswith(private_suffixes):
            return True
        return False
    except Exception:
        return False


def validate_url_safe(url: str) -> str:
    """Validate a URL is safe (no SSRF). Returns the URL if safe, raises HTTPException otherwise."""
    if not settings.ssrf_guard:
        return url
    try:
        parsed = urlparse(url)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid URL",
        )

    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only http/https URLs are allowed",
        )

    host = parsed.hostname or ""
    if is_private_host(host):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="SSRF guard: private/internal hosts are not allowed",
        )

    # Block known metadata endpoints
    metadata_hosts = {"169.254.169.254", "metadata.google.internal", "metadata.azure.com"}
    if host in metadata_hosts or host.endswith(".amazonaws.com"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="SSRF guard: cloud metadata hosts are not allowed",
        )

    return url


def strip_credentials_from_url(url: str) -> str:
    """Remove userinfo (credentials) from a URL for logging."""
    try:
        parsed = urlparse(url)
        if parsed.username or parsed.password:
            cleaned = parsed._replace(netloc=parsed.hostname or "")
            if parsed.port:
                cleaned = cleaned._replace(netloc=cleaned.netloc + f":{parsed.port}")
            return cleaned.geturl()
    except Exception:
        pass
    return url


class RequestContext:
    """Tracks request metadata for logging and metrics."""

    def __init__(self, request_id: str):
        self.request_id = request_id
        self.start_time: float = 0.0
        self.path: str = ""
        self.method: str = ""
        self.status_code: int = 0
        self.response_bytes: int = 0
        self.key_id: str = ""
        self.auth_mode: str = ""

    def to_log_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "path": self.path,
            "method": self.method,
            "status_code": self.status_code,
            "response_bytes": self.response_bytes,
            "key_id": self.key_id,
            "auth_mode": self.auth_mode,
            "duration_ms": round((time.time() - self.start_time) * 1000, 2),
        }


import time  # noqa: E402
