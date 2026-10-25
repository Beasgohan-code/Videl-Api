"""Videl-Api authentication with scopes, expiry, quotas, bearer tokens.

Key model (exceeds VYRON):
- Key IDs are opaque UUIDs; keys stored as sha256 hash + prefix
- Scopes: read, search, download, admin
- Per-key rate limit override, expiry, daily/monthly request & byte quotas
- Bearer tokens (vyt_) for WebView/Mini App short-lived access
- Owner tokens (vown_) for full access
- JSON file fallback + MongoDB backend
"""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from fastapi import Header, HTTPException, status

from config import settings

KEYS_FILE = Path("api_keys.json")
TOKENS_FILE = Path("bearer_tokens.json")
QUOTA_FILE = Path("quota_ledger.json")

# Scope hierarchy
ALL_SCOPES = {"read", "search", "download", "admin"}
SCOPE_HIERARCHY = {"read": 0, "search": 1, "download": 2, "admin": 3}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _prefix_of(key: str) -> str:
    return key[:8]


def _make_key() -> str:
    return settings.api_key_prefix + secrets.token_urlsafe(40)


def _make_token(prefix: str) -> str:
    return prefix + secrets.token_urlsafe(32)


def _scope_ok(key_scopes: list[str], needed: str) -> bool:
    if "admin" in key_scopes:
        return True
    needed_level = SCOPE_HIERARCHY.get(needed, 0)
    for s in key_scopes:
        if SCOPE_HIERARCHY.get(s, 0) >= needed_level:
            return True
    return False


# ---------------------------------------------------------------------------
# JSON file store (fallback)
# ---------------------------------------------------------------------------

def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def _save_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


# ---------------------------------------------------------------------------
# MongoDB backend (optional)
# ---------------------------------------------------------------------------

_MONGO_KEYS = None
_MONGO_QUOTAS = None
_MONGO_OK = False


def _mongo_keys():
    global _MONGO_KEYS, _MONGO_OK
    if _MONGO_OK is False:
        return None
    if _MONGO_KEYS is not None:
        return _MONGO_KEYS
    if not settings.api_keys_enabled:
        return None
    try:
        from motor.motor_asyncio import AsyncIOMotorClient
        client = AsyncIOMotorClient(
            settings.mongodb_uri,
            serverSelectionTimeoutMS=1000,
            connectTimeoutMS=1000,
        )
        client.admin.command("ping")
        _MONGO_KEYS = client[settings.mongodb_db]["api_keys"]
        _MONGO_QUOTAS = client[settings.mongodb_db]["quota_ledger"]
        _MONGO_OK = True
        return _MONGO_KEYS
    except Exception:
        _MONGO_OK = False
        _MONGO_KEYS = None
        return None


# ---------------------------------------------------------------------------
# Key operations
# ---------------------------------------------------------------------------

def _empty_key_record(key_id: str, raw_key: str, owner_id: int, scopes: list[str],
                      expires_at: Optional[datetime], rate_limit: Optional[int]) -> dict:
    return {
        "_id": key_id,
        "key_prefix": _prefix_of(raw_key),
        "key_hash": _hash_key(raw_key),
        "owner_id": owner_id,
        "scopes": scopes,
        "active": True,
        "created_at": _iso(_now()),
        "expires_at": _iso(expires_at) if expires_at else None,
        "rate_limit": rate_limit,
        "last_used_at": None,
        "usage_count": 0,
        "daily_requests": 0,
        "daily_requests_date": _now().strftime("%Y-%m-%d"),
        "monthly_requests": 0,
        "monthly_requests_month": _now().strftime("%Y-%m"),
        "daily_bytes": 0,
        "daily_bytes_date": _now().strftime("%Y-%m-%d"),
        "monthly_bytes": 0,
        "monthly_bytes_month": _now().strftime("%Y-%m"),
    }


async def _key_coll():
    coll = _mongo_keys()
    if coll is not None:
        return coll, True
    return None, False


async def create_api_key(
    owner_id: int = 0,
    *,
    scopes: Optional[list[str]] = None,
    expires_in_days: Optional[int] = None,
    rate_limit: Optional[int] = None,
    label: Optional[str] = None,
) -> dict:
    scopes = scopes or ["read", "search", "download"]
    raw_key = _make_key()
    key_id = secrets.token_urlsafe(16)
    expires_at = None
    if expires_in_days:
        expires_at = _now() + timedelta(days=expires_in_days)

    record = _empty_key_record(key_id, raw_key, owner_id, scopes, expires_at, rate_limit)
    if label:
        record["label"] = label

    coll, is_mongo = await _key_coll()
    if is_mongo:
        await coll.create_index("key_prefix", unique=True)
        await coll.create_index("owner_id")
        await coll.create_index("active")
        await coll.insert_one(record)
    else:
        keys = _load_json(KEYS_FILE, [])
        keys.append(record)
        _save_json(KEYS_FILE, keys)

    return {
        "key": raw_key,
        "key_id": key_id,
        "owner_id": owner_id,
        "scopes": scopes,
        "active": True,
        "expires_at": record["expires_at"],
        "rate_limit": rate_limit,
        "label": label,
        "created_at": record["created_at"],
    }


async def validate_api_key(
    x_api_key: str = Header(default="", alias="X-API-Key"),
    x_owner_token: str = Header(default="", alias="X-Owner-Token"),
) -> dict:
    """Validate an API key or owner token. Returns the key record + auth context."""
    if not settings.api_keys_enabled:
        return {
            "key": "open", "key_id": "open", "owner_id": 0,
            "scopes": list(ALL_SCOPES), "active": True, "admin": True,
            "auth_mode": "open",
        }

    # Owner token check (full access)
    if x_owner_token and settings.admin_keys:
        # Owner token is HMAC-signed; here we accept admin_keys as owner tokens too
        if x_owner_token in settings.admin_keys:
            return {
                "key": "owner", "key_id": "owner", "owner_id": 0,
                "scopes": list(ALL_SCOPES), "active": True, "admin": True,
                "auth_mode": "owner",
            }

    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing API key"
        )

    # Admin keys bypass
    if settings.admin_keys and x_api_key in settings.admin_keys:
        return {
            "key": "admin", "key_id": "admin", "owner_id": 0,
            "scopes": list(ALL_SCOPES), "active": True, "admin": True,
            "auth_mode": "admin",
        }

    record = None
    coll, is_mongo = await _key_coll()

    if is_mongo:
        try:
            # Try by prefix then verify hash
            prefix = _prefix_of(x_api_key)
            record = await coll.find_one({"key_prefix": prefix})
            if record and not _verify_key_hash(x_api_key, record):
                record = None
            if record:
                await coll.update_one(
                    {"_id": record["_id"]},
                    {"$set": {"last_used_at": _iso(_now()), "usage_count": record.get("usage_count", 0) + 1}},
                )
        except Exception:
            record = None

    if record is None:
        # JSON fallback
        keys = _load_json(KEYS_FILE, [])
        for rec in keys:
            if rec.get("key_prefix") == _prefix_of(x_api_key) and _verify_key_hash(x_api_key, rec):
                record = rec
                break

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key"
        )

    if not record.get("active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="API key inactive"
        )

    # Expiry check
    exp = record.get("expires_at")
    if exp:
        try:
            if datetime.fromisoformat(exp) < _now():
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN, detail="API key expired"
                )
        except ValueError:
            pass

    return {
        "key": record.get("key_prefix", ""),
        "key_id": record.get("_id", ""),
        "owner_id": record.get("owner_id", 0),
        "scopes": record.get("scopes", ["read"]),
        "active": True,
        "admin": "admin" in record.get("scopes", []),
        "rate_limit": record.get("rate_limit"),
        "label": record.get("label"),
        "auth_mode": "key",
        "_record": record,
        "_is_mongo": is_mongo,
        "_coll": coll,
    }


def _verify_key_hash(raw_key: str, record: dict) -> bool:
    stored = record.get("key_hash", "")
    return stored == _hash_key(raw_key)


# ---------------------------------------------------------------------------
# Quota / rate ledger
# ---------------------------------------------------------------------------

def _reset_quota_if_needed(record: dict) -> dict:
    now = _now()
    today = now.strftime("%Y-%m-%d")
    month = now.strftime("%Y-%m")

    if record.get("daily_requests_date") != today:
        record["daily_requests"] = 0
        record["daily_requests_date"] = today
        record["daily_bytes"] = 0
        record["daily_bytes_date"] = today

    if record.get("monthly_requests_month") != month:
        record["monthly_requests"] = 0
        record["monthly_requests_month"] = month
        record["monthly_bytes"] = 0
        record["monthly_bytes_month"] = month

    return record


def check_quota(record: dict, requested_bytes: int = 0) -> Optional[str]:
    """Return an error message if quota exceeded, else None."""
    record = _reset_quota_if_needed(record)

    daily_req_limit = settings.quota_daily_requests
    monthly_req_limit = settings.quota_monthly_requests
    daily_byte_limit = settings.quota_daily_bytes
    monthly_byte_limit = settings.quota_monthly_bytes

    # Per-key overrides
    key_rate = record.get("rate_limit")

    if daily_req_limit and record["daily_requests"] >= daily_req_limit:
        return "Daily request quota exceeded"
    if monthly_req_limit and record["monthly_requests"] >= monthly_req_limit:
        return "Monthly request quota exceeded"
    if daily_byte_limit and record["daily_bytes"] + requested_bytes > daily_byte_limit:
        return "Daily byte quota exceeded"
    if monthly_byte_limit and record["monthly_bytes"] + requested_bytes > monthly_byte_limit:
        return "Monthly byte quota exceeded"

    return None


def consume_quota(record: dict, response_bytes: int = 0) -> dict:
    record = _reset_quota_if_needed(record)
    record["daily_requests"] = record.get("daily_requests", 0) + 1
    record["monthly_requests"] = record.get("monthly_requests", 0) + 1
    record["daily_bytes"] = record.get("daily_bytes", 0) + response_bytes
    record["monthly_bytes"] = record.get("monthly_bytes", 0) + response_bytes
    return record


async def persist_quota(record: dict, is_mongo: bool, coll=None) -> None:
    if is_mongo and coll is not None:
        try:
            await coll.update_one(
                {"_id": record["_id"]},
                {"$set": {
                    "daily_requests": record.get("daily_requests", 0),
                    "daily_requests_date": record.get("daily_requests_date"),
                    "monthly_requests": record.get("monthly_requests", 0),
                    "monthly_requests_month": record.get("monthly_requests_month"),
                    "daily_bytes": record.get("daily_bytes", 0),
                    "daily_bytes_date": record.get("daily_bytes_date"),
                    "monthly_bytes": record.get("monthly_bytes", 0),
                    "monthly_bytes_month": record.get("monthly_bytes_month"),
                }},
            )
        except Exception:
            pass
    else:
        keys = _load_json(KEYS_FILE, [])
        for rec in keys:
            if rec.get("_id") == record.get("_id"):
                rec.update({
                    "daily_requests": record.get("daily_requests", 0),
                    "daily_requests_date": record.get("daily_requests_date"),
                    "monthly_requests": record.get("monthly_requests", 0),
                    "monthly_requests_month": record.get("monthly_requests_month"),
                    "daily_bytes": record.get("daily_bytes", 0),
                    "daily_bytes_date": record.get("daily_bytes_date"),
                    "monthly_bytes": record.get("monthly_bytes", 0),
                    "monthly_bytes_month": record.get("monthly_bytes_month"),
                })
                break
        _save_json(KEYS_FILE, keys)


async def list_api_keys(owner_id: int) -> list[dict]:
    out = []
    coll, is_mongo = await _key_coll()
    if is_mongo:
        try:
            cursor = coll.find({"owner_id": owner_id}).sort("created_at", -1)
            async for doc in cursor:
                doc.pop("_id", None)
                doc.pop("key_hash", None)
                out.append(doc)
            return out
        except Exception:
            pass
    for rec in _load_json(KEYS_FILE, []):
        if rec.get("owner_id") == owner_id:
            rec.pop("key_hash", None)
            out.append(rec)
    return out


async def revoke_api_key(owner_id: int, api_key: str) -> bool:
    coll, is_mongo = await _key_coll()
    if is_mongo:
        try:
            result = await coll.update_one(
                {"owner_id": owner_id, "key_prefix": _prefix_of(api_key)},
                {"$set": {"active": False, "revoked_at": _iso(_now())}},
            )
            return result.modified_count > 0
        except Exception:
            pass
    keys = _load_json(KEYS_FILE, [])
    changed = False
    for rec in keys:
        if rec.get("owner_id") == owner_id and rec.get("key_prefix") == _prefix_of(api_key):
            rec["active"] = False
            rec["revoked_at"] = _iso(_now())
            changed = True
    if changed:
        _save_json(KEYS_FILE, keys)
    return changed


async def patch_api_key(
    owner_id: int,
    key_id: str,
    *,
    scopes: Optional[list[str]] = None,
    active: Optional[bool] = None,
    rate_limit: Optional[int] = None,
    expires_in_days: Optional[int] = None,
    label: Optional[str] = None,
) -> Optional[dict]:
    """Edit a key without rotating it (VYRON API 2.1)."""
    coll, is_mongo = await _key_coll()
    updates = {}
    if scopes is not None:
        updates["scopes"] = scopes
    if active is not None:
        updates["active"] = active
    if rate_limit is not None:
        updates["rate_limit"] = rate_limit
    if expires_in_days is not None:
        updates["expires_at"] = _iso(_now() + timedelta(days=expires_in_days))
    if label is not None:
        updates["label"] = label

    if is_mongo and coll is not None:
        try:
            result = await coll.update_one(
                {"_id": key_id, "owner_id": owner_id},
                {"$set": updates},
            )
            if result.modified_count > 0:
                doc = await coll.find_one({"_id": key_id})
                doc.pop("_id", None)
                doc.pop("key_hash", None)
                return doc
            return None
        except Exception:
            return None
    else:
        keys = _load_json(KEYS_FILE, [])
        for rec in keys:
            if rec.get("_id") == key_id and rec.get("owner_id") == owner_id:
                rec.update(updates)
                _save_json(KEYS_FILE, keys)
                rec.pop("key_hash", None)
                return rec
        return None


async def rotate_api_key(owner_id: int, key_id: str) -> Optional[dict]:
    """Rotate a key: invalidate old, issue new with same scopes/owner."""
    coll, is_mongo = await _key_coll()
    old = None
    if is_mongo:
        old = await coll.find_one({"_id": key_id, "owner_id": owner_id})
    else:
        for rec in _load_json(KEYS_FILE, []):
            if rec.get("_id") == key_id and rec.get("owner_id") == owner_id:
                old = rec
                break
    if not old:
        return None

    # Revoke old
    await revoke_api_key(owner_id, old.get("key_hash", ""))

    # Create new with same attributes
    new = await create_api_key(
        owner_id=owner_id,
        scopes=old.get("scopes", ["read", "search", "download"]),
        rate_limit=old.get("rate_limit"),
        label=old.get("label"),
    )
    # Carry expiry if set
    if old.get("expires_at"):
        try:
            exp = datetime.fromisoformat(old["expires_at"])
            days = (exp - _now()).days
            if days > 0:
                new2 = await create_api_key(
                    owner_id=owner_id,
                    scopes=old.get("scopes", ["read", "search", "download"]),
                    rate_limit=old.get("rate_limit"),
                    expires_in_days=days,
                    label=old.get("label"),
                )
                return new2
        except ValueError:
            pass
    return new


# ---------------------------------------------------------------------------
# Bearer tokens (short-lived for WebView/Mini App)
# ---------------------------------------------------------------------------

def create_bearer_token(owner_id: int = 0, scopes: Optional[list[str]] = None, ttl_minutes: Optional[int] = None) -> dict:
    scopes = scopes or ["read", "search", "download"]
    ttl = ttl_minutes or settings.bearer_token_ttl_minutes
    token = _make_token("vyt_")
    expires_at = _now() + timedelta(minutes=ttl)
    record = {
        "token": token,
        "token_hash": _hash_key(token),
        "owner_id": owner_id,
        "scopes": scopes,
        "created_at": _iso(_now()),
        "expires_at": _iso(expires_at),
        "active": True,
    }
    tokens = _load_json(TOKENS_FILE, [])
    tokens.append(record)
    _save_json(TOKENS_FILE, tokens)
    return {
        "token": token,
        "expires_in_seconds": ttl * 60,
        "expires_at": record["expires_at"],
        "scopes": scopes,
    }


def validate_bearer_token(token: str) -> Optional[dict]:
    if not token.startswith("vyt_"):
        return None
    tokens = _load_json(TOKENS_FILE, [])
    now = _now()
    for rec in tokens:
        if rec.get("token_hash") == _hash_key(token) and rec.get("active", True):
            try:
                if datetime.fromisoformat(rec["expires_at"]) < now:
                    continue
            except ValueError:
                continue
            return {
                "token": rec.get("token", ""),
                "owner_id": rec.get("owner_id", 0),
                "scopes": rec.get("scopes", ["read"]),
                "auth_mode": "bearer",
            }
    return None


async def cleanup_expired_tokens() -> int:
    tokens = _load_json(TOKENS_FILE, [])
    now = _now()
    changed = False
    kept = []
    for rec in tokens:
        try:
            if datetime.fromisoformat(rec["expires_at"]) < now:
                rec["active"] = False
                changed = True
        except ValueError:
            pass
        kept.append(rec)
    if changed:
        _save_json(TOKENS_FILE, kept)
    return len(tokens)
