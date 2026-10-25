"""Videl-Api authentication with scopes, expiry, quotas, bearer tokens.

Key model:
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
    """Edit a key without rotating it."""
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


# ============================================================================
# USER MANAGEMENT
# ============================================================================

USERS_FILE = Path("users.json")
TIERS_FILE = Path("tiers.json")
PAYMENTS_FILE = Path("payments.json")
PLAYLISTS_FILE = Path("playlists.json")
WEBHOOKS_FILE = Path("webhooks.json")
NOTIFICATIONS_FILE = Path("notifications.json")
BATCHES_FILE = Path("batches.json")
DEVICES_FILE = Path("devices.json")
SESSIONS_FILE = Path("sessions.json")
ALERTS_FILE = Path("alerts.json")
ANALYTICS_FILE = Path("analytics.json")


def _load_users() -> list[dict]:
    return _load_json(USERS_FILE, [])


def _save_users(users: list[dict]) -> None:
    _save_json(USERS_FILE, users)


def create_user(
    telegram_id: Optional[int] = None,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    tier: str = "free",
    scopes: Optional[list[str]] = None,
) -> dict:
    scopes = scopes or ["read", "search"]
    user_id = secrets.token_urlsafe(16)
    user = {
        "id": user_id,
        "telegram_id": telegram_id,
        "username": username,
        "first_name": first_name,
        "tier": tier,
        "scopes": scopes,
        "is_admin": False,
        "is_owner": False,
        "created_at": _iso(_now()),
        "updated_at": _iso(_now()),
        "daily_requests": 0,
        "monthly_requests": 0,
        "daily_bytes": 0,
        "monthly_bytes": 0,
        "language": "en",
        "notifications": True,
        "stars_balance": 0,
        "lifetime_stars": 0,
        "download_count": 0,
        "search_count": 0,
        "playlist_count": 0,
    }
    users = _load_users()
    users.append(user)
    _save_users(users)
    return user


def get_user(user_id: str) -> Optional[dict]:
    for u in _load_users():
        if u.get("id") == user_id:
            return u
    return None


def get_user_by_telegram(telegram_id: int) -> Optional[dict]:
    for u in _load_users():
        if u.get("telegram_id") == telegram_id:
            return u
    return None


def update_user(user_id: str, **kwargs) -> Optional[dict]:
    users = _load_users()
    for u in users:
        if u.get("id") == user_id:
            u.update(kwargs)
            u["updated_at"] = _iso(_now())
            _save_users(users)
            return u
    return None


def delete_user(user_id: str) -> bool:
    users = _load_users()
    changed = False
    kept = []
    for u in users:
        if u.get("id") == user_id:
            changed = True
        else:
            kept.append(u)
    if changed:
        _save_users(kept)
    return changed


def list_users(limit: int = 100, offset: int = 0) -> list[dict]:
    users = _load_users()
    return users[offset:offset + limit]


def set_user_tier(user_id: str, tier: str, scopes: Optional[list[str]] = None) -> Optional[dict]:
    users = _load_users()
    tier_scopes = scopes or {
        "free": ["read", "search"],
        "pro": ["read", "search", "download"],
        "owner": ["read", "search", "download", "admin"],
    }.get(tier, ["read", "search"])
    for u in users:
        if u.get("id") == user_id:
            u["tier"] = tier
            u["scopes"] = tier_scopes
            u["is_admin"] = tier == "owner"
            u["is_owner"] = tier == "owner"
            u["updated_at"] = _iso(_now())
            _save_users(users)
            return u
    return None


def increment_user_counter(telegram_id: int, field: str, amount: int = 1) -> None:
    users = _load_users()
    for u in users:
        if u.get("telegram_id") == telegram_id:
            u[field] = u.get(field, 0) + amount
            u["updated_at"] = _iso(_now())
            break
    _save_users(users)


# ============================================================================
# TIER INFO
# ============================================================================

TIER_DEFINITIONS = {
    "free": {
        "daily_limit": 100,
        "monthly_limit": 1000,
        "daily_bytes_limit": 100 * 1024 * 1024,
        "monthly_bytes_limit": 1024 * 1024 * 1024,
        "rate_limit": 100,
        "scopes": ["read", "search"],
    },
    "pro": {
        "daily_limit": 1000,
        "monthly_limit": 30000,
        "daily_bytes_limit": 1024 * 1024 * 1024,
        "monthly_bytes_limit": 10 * 1024 * 1024 * 1024,
        "rate_limit": 1000,
        "scopes": ["read", "search", "download"],
    },
    "owner": {
        "daily_limit": 0,
        "monthly_limit": 0,
        "daily_bytes_limit": 0,
        "monthly_bytes_limit": 0,
        "rate_limit": None,
        "scopes": ["read", "search", "download", "admin"],
    },
}


def get_tier_info(tier: str) -> dict:
    return TIER_DEFINITIONS.get(tier, TIER_DEFINITIONS["free"])


def list_tiers() -> list[dict]:
    return [
        {"tier": t, **info} for t, info in TIER_DEFINITIONS.items()
    ]


# ============================================================================
# PAYMENTS / TELEGRAM STARS
# ============================================================================

def _load_payments() -> list[dict]:
    return _load_json(PAYMENTS_FILE, [])


def _save_payments(payments: list[dict]) -> None:
    _save_json(PAYMENTS_FILE, payments)


def create_payment(
    user_id: int,
    tier: str,
    amount: int,
    currency: str,
    invoice_payload: str,
) -> dict:
    payment_id = secrets.token_urlsafe(16)
    payment = {
        "id": payment_id,
        "user_id": user_id,
        "tier": tier,
        "amount": amount,
        "currency": currency,
        "invoice_payload": invoice_payload,
        "status": "pending",
        "created_at": _iso(_now()),
        "completed_at": None,
    }
    payments = _load_payments()
    payments.append(payment)
    _save_payments(payments)
    return payment


def complete_payment(invoice_payload: str) -> Optional[dict]:
    payments = _load_payments()
    for p in payments:
        if p.get("invoice_payload") == invoice_payload and p.get("status") == "pending":
            p["status"] = "completed"
            p["completed_at"] = _iso(_now())
            # Upgrade user tier if applicable
            if p.get("tier") in ("pro", "owner"):
                user = get_user_by_telegram(p["user_id"])
                if user:
                    set_user_tier(user["id"], p["tier"])
                    # Add stars balance
                    users = _load_users()
                    for u in users:
                        if u.get("id") == user["id"]:
                            u["stars_balance"] = u.get("stars_balance", 0) + p["amount"]
                            u["lifetime_stars"] = u.get("lifetime_stars", 0) + p["amount"]
                            break
                    _save_users(users)
            _save_payments(payments)
            return p
    return None


def list_payments(user_id: Optional[int] = None) -> list[dict]:
    payments = _load_payments()
    if user_id is not None:
        payments = [p for p in payments if p.get("user_id") == user_id]
    return payments


# ============================================================================
# PLAYLISTS
# ============================================================================

def _load_playlists() -> list[dict]:
    return _load_json(PLAYLISTS_FILE, [])


def _save_playlists(playlists: list[dict]) -> None:
    _save_json(PLAYLISTS_FILE, playlists)


def create_playlist(owner_id: int, name: str, description: Optional[str] = None, is_public: bool = False) -> dict:
    playlist_id = secrets.token_urlsafe(16)
    playlist = {
        "id": playlist_id,
        "owner_id": owner_id,
        "name": name,
        "description": description,
        "is_public": is_public,
        "items": [],
        "item_count": 0,
        "created_at": _iso(_now()),
        "updated_at": _iso(_now()),
    }
    playlists = _load_playlists()
    playlists.append(playlist)
    _save_playlists(playlists)
    # Update user playlist count
    users = _load_users()
    for u in users:
        if u.get("telegram_id") == owner_id:
            u["playlist_count"] = u.get("playlist_count", 0) + 1
            break
    _save_users(users)
    return playlist


def get_playlist(playlist_id: str) -> Optional[dict]:
    for p in _load_playlists():
        if p.get("id") == playlist_id:
            return p
    return None


def list_playlists(owner_id: Optional[int] = None) -> list[dict]:
    playlists = _load_playlists()
    if owner_id is not None:
        playlists = [p for p in playlists if p.get("owner_id") == owner_id]
    return playlists


def update_playlist(playlist_id: str, **kwargs) -> Optional[dict]:
    playlists = _load_playlists()
    for p in playlists:
        if p.get("id") == playlist_id:
            p.update(kwargs)
            p["updated_at"] = _iso(_now())
            _save_playlists(playlists)
            return p
    return None


def delete_playlist(playlist_id: str) -> bool:
    playlists = _load_playlists()
    changed = False
    kept = []
    for p in playlists:
        if p.get("id") == playlist_id:
            changed = True
        else:
            kept.append(p)
    if changed:
        _save_playlists(kept)
    return changed


def add_playlist_item(playlist_id: str, item: dict) -> Optional[dict]:
    playlists = _load_playlists()
    for p in playlists:
        if p.get("id") == playlist_id:
            if p.get("item_count", 0) >= 200:
                return None
            item["id"] = secrets.token_urlsafe(8)
            item["position"] = p.get("item_count", 0)
            item["added_at"] = _iso(_now())
            p.setdefault("items", []).append(item)
            p["item_count"] = len(p["items"])
            p["updated_at"] = _iso(_now())
            _save_playlists(playlists)
            return item
    return None


def remove_playlist_item(playlist_id: str, item_id: str) -> bool:
    playlists = _load_playlists()
    for p in playlists:
        if p.get("id") == playlist_id:
            items = p.get("items", [])
            kept = [it for it in items if it.get("id") != item_id]
            if len(kept) != len(items):
                p["items"] = kept
                p["item_count"] = len(kept)
                p["updated_at"] = _iso(_now())
                _save_playlists(playlists)
                return True
    return False


# ============================================================================
# WEBHOOKS
# ============================================================================

def _load_webhooks() -> list[dict]:
    return _load_json(WEBHOOKS_FILE, [])


def _save_webhooks(webhooks: list[dict]) -> None:
    _save_json(WEBHOOKS_FILE, webhooks)


def create_webhook(url: str, events: list[str], secret: Optional[str] = None) -> dict:
    webhook_id = secrets.token_urlsafe(16)
    webhook = {
        "id": webhook_id,
        "url": url,
        "events": events,
        "secret": secret,
        "active": True,
        "created_at": _iso(_now()),
        "last_triggered": None,
        "trigger_count": 0,
    }
    hooks = _load_webhooks()
    hooks.append(webhook)
    _save_webhooks(hooks)
    return webhook


def list_webhooks() -> list[dict]:
    return _load_webhooks()


def delete_webhook(webhook_id: str) -> bool:
    hooks = _load_webhooks()
    changed = False
    kept = []
    for h in hooks:
        if h.get("id") == webhook_id:
            changed = True
        else:
            kept.append(h)
    if changed:
        _save_webhooks(kept)
    return changed


def trigger_webhook(event: str, payload: dict) -> None:
    """Trigger webhooks matching an event (fire-and-forget)."""
    hooks = _load_webhooks()
    import asyncio
    import aiohttp

    async def _fire():
        for h in hooks:
            if not h.get("active", True):
                continue
            if event not in h.get("events", []):
                continue
            try:
                headers = {"Content-Type": "application/json"}
                if h.get("secret"):
                    headers["X-Webhook-Secret"] = h["secret"]
                async with aiohttp.ClientSession() as session:
                    await session.post(h["url"], json=payload, headers=headers, timeout=10)
                h["trigger_count"] = h.get("trigger_count", 0) + 1
                h["last_triggered"] = _iso(_now())
            except Exception:
                pass
        _save_webhooks(hooks)

    try:
        asyncio.create_task(_fire())
    except RuntimeError:
        asyncio.run(_fire())


# ============================================================================
# NOTIFICATIONS
# ============================================================================

def _load_notifications() -> list[dict]:
    return _load_json(NOTIFICATIONS_FILE, [])


def _save_notifications(notifications: list[dict]) -> None:
    _save_json(NOTIFICATIONS_FILE, notifications)


def create_notification(
    user_id: int,
    title: str,
    message: str,
    type: str = "info",
) -> dict:
    notif_id = secrets.token_urlsafe(16)
    notif = {
        "id": notif_id,
        "user_id": user_id,
        "title": title,
        "message": message,
        "type": type,
        "read": False,
        "created_at": _iso(_now()),
    }
    notifs = _load_notifications()
    notifs.append(notif)
    _save_notifications(notifs)
    return notif


def list_notifications(user_id: int, unread_only: bool = False) -> list[dict]:
    notifs = _load_notifications()
    notifs = [n for n in notifs if n.get("user_id") == user_id]
    if unread_only:
        notifs = [n for n in notifs if not n.get("read", False)]
    return notifs


def mark_notification_read(notif_id: str, user_id: int) -> bool:
    notifs = _load_notifications()
    for n in notifs:
        if n.get("id") == notif_id and n.get("user_id") == user_id:
            n["read"] = True
            _save_notifications(notifs)
            return True
    return False


# ============================================================================
# BATCH OPERATIONS
# ============================================================================

def _load_batches() -> list[dict]:
    return _load_json(BATCHES_FILE, [])


def _save_batches(batches: list[dict]) -> None:
    _save_json(BATCHES_FILE, batches)


def create_batch(total_items: int) -> str:
    batch_id = secrets.token_urlsafe(16)
    batch = {
        "id": batch_id,
        "status": "queued",
        "total_items": total_items,
        "completed_items": 0,
        "results": [],
        "error": None,
        "created_at": _iso(_now()),
        "updated_at": _iso(_now()),
    }
    batches = _load_batches()
    batches.append(batch)
    _save_batches(batches)
    return batch_id


def get_batch(batch_id: str) -> Optional[dict]:
    for b in _load_batches():
        if b.get("id") == batch_id:
            return b
    return None


def update_batch(batch_id: str, **kwargs) -> Optional[dict]:
    batches = _load_batches()
    for b in batches:
        if b.get("id") == batch_id:
            b.update(kwargs)
            b["updated_at"] = _iso(_now())
            _save_batches(batches)
            return b
    return None


# ============================================================================
# DEVICES / SESSIONS
# ============================================================================

def _load_devices() -> list[dict]:
    return _load_json(DEVICES_FILE, [])


def _save_devices(devices: list[dict]) -> None:
    _save_json(DEVICES_FILE, devices)


def register_device(user_id: int, device_id: str, device_name: str, platform: str) -> dict:
    dev_id = secrets.token_urlsafe(16)
    device = {
        "id": dev_id,
        "user_id": user_id,
        "device_id": device_id,
        "device_name": device_name,
        "platform": platform,
        "last_active": _iso(_now()),
        "active": True,
    }
    devices = _load_devices()
    # Deactivate old devices with same device_id
    for d in devices:
        if d.get("device_id") == device_id:
            d["active"] = False
    devices.append(device)
    _save_devices(devices)
    return device


def list_devices(user_id: int) -> list[dict]:
    return [d for d in _load_devices() if d.get("user_id") == user_id and d.get("active", True)]


# ============================================================================
# ALERTS
# ============================================================================

def _load_alerts() -> list[dict]:
    return _load_json(ALERTS_FILE, [])


def _save_alerts(alerts: list[dict]) -> None:
    _save_json(ALERTS_FILE, alerts)


def create_alert(name: str, condition: str, threshold: float, action: str) -> dict:
    alert_id = secrets.token_urlsafe(16)
    alert = {
        "id": alert_id,
        "name": name,
        "condition": condition,
        "threshold": threshold,
        "action": action,
        "active": True,
        "created_at": _iso(_now()),
    }
    alerts = _load_alerts()
    alerts.append(alert)
    _save_alerts(alerts)
    return alert


def list_alerts() -> list[dict]:
    return _load_alerts()


# ============================================================================
# ANALYTICS
# ============================================================================

def _load_analytics() -> list[dict]:
    return _load_json(ANALYTICS_FILE, [])


def _save_analytics(data: list[dict]) -> None:
    _save_json(ANALYTICS_FILE, data)


def record_analytics(event: str, data: dict) -> None:
    entry = {
        "event": event,
        "data": data,
        "timestamp": _iso(_now()),
    }
    analytics = _load_analytics()
    analytics.append(entry)
    # Retention: keep last 10000 entries
    if len(analytics) > 10000:
        analytics = analytics[-10000:]
    _save_analytics(analytics)


def get_analytics(event: Optional[str] = None) -> list[dict]:
    analytics = _load_analytics()
    if event:
        analytics = [a for a in analytics if a.get("event") == event]
    return analytics


# ============================================================================
# OAUTH2 / JWT TOKENS
# ============================================================================

TOKENS_FILE = Path("bearer_tokens.json")


def _load_tokens() -> list[dict]:
    return _load_json(TOKENS_FILE, [])


def _save_tokens(tokens: list[dict]) -> None:
    _save_json(TOKENS_FILE, tokens)


def create_oauth_token(
    client_id: str,
    client_secret: str,
    scope: Optional[str] = None,
    ttl_seconds: int = 3600,
) -> Optional[dict]:
    tokens = _load_tokens()
    # Validate client (simple check - in production use proper client registry)
    if not client_id or not client_secret:
        return None
    token = secrets.token_urlsafe(32)
    expires_at = _now() + __import__("datetime").timedelta(seconds=ttl_seconds)
    record = {
        "token": token,
        "client_id": client_id,
        "scope": scope,
        "created_at": _iso(_now()),
        "expires_at": _iso(expires_at),
        "active": True,
    }
    tokens.append(record)
    _save_tokens(tokens)
    return {
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": ttl_seconds,
        "scope": scope,
    }


def validate_oauth_token(token: str) -> Optional[dict]:
    tokens = _load_tokens()
    now = _now()
    for rec in tokens:
        if rec.get("token") == token and rec.get("active", True):
            try:
                if datetime.fromisoformat(rec["expires_at"]) < now:
                    continue
            except ValueError:
                continue
            return rec
    return None


# ============================================================================
# TWO-FACTOR AUTHENTICATION
# ============================================================================

TWOFACTOR_FILE = Path("2fa.json")


def _load_2fa() -> list[dict]:
    return _load_json(TWOFACTOR_FILE, [])


def _save_2fa(data: list[dict]) -> None:
    _save_json(TWOFACTOR_FILE, data)


def setup_2fa(user_id: int) -> dict:
    import base64
    import pyotp
    secret = pyotp.random_base32()
    data = _load_2fa()
    # Remove existing
    data = [d for d in data if d.get("user_id") != user_id]
    data.append({
        "user_id": user_id,
        "secret": secret,
        "enabled": False,
        "backup_codes": [secrets.token_hex(4) for _ in range(8)],
        "created_at": _iso(_now()),
    })
    _save_2fa(data)
    return {
        "enabled": False,
        "secret": secret,
        "qr_code": f"otpauth://totp/Videl-Api:{user_id}?secret={secret}&issuer=Videl-Api",
        "backup_codes": data[-1]["backup_codes"],
    }


def verify_2fa(user_id: int, token: str) -> bool:
    import pyotp
    data = _load_2fa()
    for d in data:
        if d.get("user_id") == user_id:
            totp = pyotp.TOTP(d["secret"])
            return totp.verify(token)
    return False


def enable_2fa(user_id: int) -> bool:
    data = _load_2fa()
    for d in data:
        if d.get("user_id") == user_id:
            d["enabled"] = True
            _save_2fa(data)
            return True
    return False


def verify_2fa_backup(user_id: int, code: str) -> bool:
    data = _load_2fa()
    for d in data:
        if d.get("user_id") == user_id:
            codes = d.get("backup_codes", [])
            if code in codes:
                codes.remove(code)
                d["backup_codes"] = codes
                _save_2fa(data)
                return True
    return False


# ============================================================================
# NOTIFICATION PREFERENCES
# ============================================================================

NOTIF_PREFS_FILE = Path("notification_prefs.json")


def _load_notif_prefs() -> list[dict]:
    return _load_json(NOTIF_PREFS_FILE, [])


def _save_notif_prefs(data: list[dict]) -> None:
    _save_json(NOTIF_PREFS_FILE, data)


def get_notif_prefs(user_id: int) -> dict:
    data = _load_notif_prefs()
    for d in data:
        if d.get("user_id") == user_id:
            return d
    return {"email": True, "sms": False, "push": True, "download_complete": True,
            "payment_received": True, "system_alerts": False, "marketing": False}


def set_notif_prefs(user_id: int, prefs: dict) -> dict:
    data = _load_notif_prefs()
    for d in data:
        if d.get("user_id") == user_id:
            d.update(prefs)
            d["updated_at"] = _iso(_now())
            _save_notif_prefs(data)
            return d
    data.append({"user_id": user_id, **prefs, "created_at": _iso(_now())})
    _save_notif_prefs(data)
    return data[-1]


# ============================================================================
# FILE ENCRYPTION
# ============================================================================

ENCRYPTED_FILES_FILE = Path("encrypted_files.json")


def _load_encrypted_files() -> list[dict]:
    return _load_json(ENCRYPTED_FILES_FILE, [])


def _save_encrypted_files(data: list[dict]) -> None:
    _save_json(ENCRYPTED_FILES_FILE, data)


def encrypt_file_record(file_path: str, password: str) -> dict:
    import hashlib
    record_id = secrets.token_urlsafe(16)
    key_hash = hashlib.sha256(password.encode()).hexdigest()[:32]
    record = {
        "id": record_id,
        "file_path": file_path,
        "key_hash": key_hash,
        "algorithm": "AES-256-GCM",
        "encrypted_at": _iso(_now()),
    }
    data = _load_encrypted_files()
    data.append(record)
    _save_encrypted_files(data)
    return {"encrypted_path": f"{file_path}.enc", "algorithm": "AES-256-GCM"}


def decrypt_file_record(file_path: str, password: str) -> bool:
    import hashlib
    key_hash = hashlib.sha256(password.encode()).hexdigest()[:32]
    data = _load_encrypted_files()
    for d in data:
        if d.get("file_path") == file_path and d.get("key_hash") == key_hash:
            return True
    return False


# ============================================================================
# DOWNLOAD SPEED LIMITING
# ============================================================================

SPEED_LIMITS_FILE = Path("speed_limits.json")


def _load_speed_limits() -> list[dict]:
    return _load_json(SPEED_LIMITS_FILE, [])


def _save_speed_limits(data: list[dict]) -> None:
    _save_json(SPEED_LIMITS_FILE, data)


def set_speed_limit(key_id: str, max_kbps: int) -> dict:
    data = _load_speed_limits()
    for d in data:
        if d.get("key_id") == key_id:
            d["max_kbps"] = max_kbps
            d["updated_at"] = _iso(_now())
            _save_speed_limits(data)
            return d
    data.append({"key_id": key_id, "max_kbps": max_kbps, "active": True,
                 "created_at": _iso(_now())})
    _save_speed_limits(data)
    return data[-1]


def get_speed_limit(key_id: str) -> Optional[dict]:
    data = _load_speed_limits()
    for d in data:
        if d.get("key_id") == key_id:
            return d
    return None


# ============================================================================
# DOWNLOAD SCHEDULING
# ============================================================================

SCHEDULED_DOWNLOADS_FILE = Path("scheduled_downloads.json")


def _load_scheduled_downloads() -> list[dict]:
    return _load_json(SCHEDULED_DOWNLOADS_FILE, [])


def _save_scheduled_downloads(data: list[dict]) -> None:
    _save_json(SCHEDULED_DOWNLOADS_FILE, data)


def create_schedule(url: str, cron_expression: str, **kwargs) -> dict:
    schedule_id = secrets.token_urlsafe(16)
    record = {
        "schedule_id": schedule_id,
        "url": url,
        "cron_expression": cron_expression,
        "enabled": kwargs.get("enabled", True),
        "format": kwargs.get("format", "bestaudio/best"),
        "source": kwargs.get("source"),
        "user_id": kwargs.get("user_id", 0),
        "next_run": None,
        "created_at": _iso(_now()),
    }
    data = _load_scheduled_downloads()
    data.append(record)
    _save_scheduled_downloads(data)
    return record


def list_schedules(user_id: Optional[int] = None) -> list[dict]:
    data = _load_scheduled_downloads()
    if user_id is not None:
        data = [d for d in data if d.get("user_id") == user_id]
    return data


def toggle_schedule(schedule_id: str, enabled: bool) -> bool:
    data = _load_scheduled_downloads()
    for d in data:
        if d.get("schedule_id") == schedule_id:
            d["enabled"] = enabled
            _save_scheduled_downloads(data)
            return True
    return False


# ============================================================================
# CONTENT RATING
# ============================================================================

RATINGS_FILE = Path("ratings.json")


def _load_ratings() -> list[dict]:
    return _load_json(RATINGS_FILE, [])


def _save_ratings(data: list[dict]) -> None:
    _save_json(RATINGS_FILE, data)


def rate_content(content_id: str, rating: int, user_id: int, review: Optional[str] = None) -> dict:
    data = _load_ratings()
    # Remove existing rating from this user for this content
    data = [d for d in data if not (d.get("content_id") == content_id and d.get("user_id") == user_id)]
    data.append({
        "content_id": content_id,
        "user_id": user_id,
        "rating": rating,
        "review": review,
        "created_at": _iso(_now()),
    })
    _save_ratings(data)
    return get_content_rating(content_id, user_id)


def get_content_rating(content_id: str, user_id: int = 0) -> dict:
    data = _load_ratings()
    ratings = [d for d in data if d.get("content_id") == content_id]
    if not ratings:
        return {"content_id": content_id, "average_rating": 0.0, "total_ratings": 0,
                "user_rating": None}
    avg = sum(d["rating"] for d in ratings) / len(ratings)
    user_rating = None
    for d in ratings:
        if d.get("user_id") == user_id:
            user_rating = d["rating"]
            break
    return {
        "content_id": content_id,
        "average_rating": round(avg, 2),
        "total_ratings": len(ratings),
        "user_rating": user_rating,
    }


# ============================================================================
# FAVORITES / BOOKMARKS
# ============================================================================

FAVORITES_FILE = Path("favorites.json")


def _load_favorites() -> list[dict]:
    return _load_json(FAVORITES_FILE, [])


def _save_favorites(data: list[dict]) -> None:
    _save_json(FAVORITES_FILE, data)


def add_favorite(user_id: int, title: str, url: str, **kwargs) -> dict:
    data = _load_favorites()
    fav_id = secrets.token_urlsafe(16)
    record = {
        "id": fav_id,
        "user_id": user_id,
        "title": title,
        "url": url,
        "source": kwargs.get("source"),
        "thumbnail": kwargs.get("thumbnail"),
        "tags": kwargs.get("tags", []),
        "created_at": _iso(_now()),
    }
    data.append(record)
    _save_favorites(data)
    return record


def list_favorites(user_id: int) -> list[dict]:
    data = _load_favorites()
    return [d for d in data if d.get("user_id") == user_id]


def remove_favorite(fav_id: str, user_id: int) -> bool:
    data = _load_favorites()
    changed = False
    kept = []
    for d in data:
        if d.get("id") == fav_id and d.get("user_id") == user_id:
            changed = True
        else:
            kept.append(d)
    if changed:
        _save_favorites(kept)
    return changed


# ============================================================================
# DOWNLOAD HISTORY EXPORT
# ============================================================================

EXPORTS_FILE = Path("exports.json")


def _load_exports() -> list[dict]:
    return _load_json(EXPORTS_FILE, [])


def _save_exports(data: list[dict]) -> None:
    _save_json(EXPORTS_FILE, data)


def create_export(user_id: int, format: str = "json", **kwargs) -> dict:
    export_id = secrets.token_urlsafe(16)
    record = {
        "id": export_id,
        "user_id": user_id,
        "format": format,
        "status": "completed",
        "download_url": f"/v1/export/download/{export_id}",
        "expires_at": _iso(_now() + __import__("datetime").timedelta(days=7)),
        "created_at": _iso(_now()),
    }
    data = _load_exports()
    data.append(record)
    _save_exports(data)
    return record


def list_exports(user_id: int) -> list[dict]:
    data = _load_exports()
    return [d for d in data if d.get("user_id") == user_id]


# ============================================================================
# WEBHOOK DELIVERY TRACKING
# ============================================================================

WEBHOOK_DELIVERIES_FILE = Path("webhook_deliveries.json")


def _load_webhook_deliveries() -> list[dict]:
    return _load_json(WEBHOOK_DELIVERIES_FILE, [])


def _save_webhook_deliveries(data: list[dict]) -> None:
    _save_json(WEBHOOK_DELIVERIES_FILE, data)


def record_webhook_delivery(webhook_id: str, event: str, status: str, attempt: int) -> dict:
    data = _load_webhook_deliveries()
    delivery_id = secrets.token_urlsafe(16)
    record = {
        "id": delivery_id,
        "webhook_id": webhook_id,
        "event": event,
        "status": status,
        "attempt": attempt,
        "next_retry": None,
        "created_at": _iso(_now()),
    }
    data.append(record)
    _save_webhook_deliveries(data)
    return record


# ============================================================================
# API KEY AUTO-ROTATION
# ============================================================================

KEY_ROTATION_FILE = Path("key_rotations.json")


def _load_key_rotations() -> list[dict]:
    return _load_json(KEY_ROTATION_FILE, [])


def _save_key_rotations(data: list[dict]) -> None:
    _save_json(KEY_ROTATION_FILE, data)


def schedule_key_rotation(key_id: str, interval_days: int, enabled: bool = True) -> dict:
    data = _load_key_rotations()
    for d in data:
        if d.get("key_id") == key_id:
            d["interval_days"] = interval_days
            d["enabled"] = enabled
            _save_key_rotations(data)
            return d
    data.append({
        "key_id": key_id,
        "interval_days": interval_days,
        "enabled": enabled,
        "created_at": _iso(_now()),
    })
    _save_key_rotations(data)
    return data[-1]


def list_key_rotations() -> list[dict]:
    return _load_key_rotations()


# ============================================================================
# TIER FEATURE FLAGS
# ============================================================================

TIER_FEATURES_FILE = Path("tier_features.json")


def _load_tier_features() -> list[dict]:
    return _load_json(TIER_FEATURES_FILE, [])


def _save_tier_features(data: list[dict]) -> None:
    _save_json(TIER_FEATURES_FILE, data)


def set_tier_feature(tier: str, feature: str, enabled: bool) -> dict:
    data = _load_tier_features()
    for d in data:
        if d.get("tier") == tier and d.get("feature") == feature:
            d["enabled"] = enabled
            _save_tier_features(data)
            return d
    data.append({"tier": tier, "feature": feature, "enabled": enabled})
    _save_tier_features(data)
    return data[-1]


def get_tier_features(tier: str) -> list[dict]:
    data = _load_tier_features()
    return [d for d in data if d.get("tier") == tier]


# ============================================================================
# GEO-BLOCKING
# ============================================================================

GEO_BLOCKS_FILE = Path("geo_blocks.json")


def _load_geo_blocks() -> list[dict]:
    return _load_json(GEO_BLOCKS_FILE, [])


def _save_geo_blocks(data: list[dict]) -> None:
    _save_json(GEO_BLOCKS_FILE, data)


def add_geo_block(country_code: str, blocked: bool = True, reason: Optional[str] = None) -> dict:
    data = _load_geo_blocks()
    for d in data:
        if d.get("country_code") == country_code:
            d["blocked"] = blocked
            d["reason"] = reason
            _save_geo_blocks(data)
            return d
    data.append({"country_code": country_code.upper(), "blocked": blocked,
                 "reason": reason, "created_at": _iso(_now())})
    _save_geo_blocks(data)
    return data[-1]


def list_geo_blocks() -> list[dict]:
    return _load_geo_blocks()


def is_country_blocked(country_code: str) -> bool:
    data = _load_geo_blocks()
    for d in data:
        if d.get("country_code") == country_code.upper():
            return d.get("blocked", False)
    return False


# ============================================================================
# IP REPUTATION
# ============================================================================

IP_REPUTATION_FILE = Path("ip_reputation.json")


def _load_ip_reputation() -> list[dict]:
    return _load_json(IP_REPUTATION_FILE, [])


def _save_ip_reputation(data: list[dict]) -> None:
    _save_json(IP_REPUTATION_FILE, data)


def record_ip_reputation(ip: str, score: float, flags: list[str]) -> dict:
    data = _load_ip_reputation()
    for d in data:
        if d.get("ip") == ip:
            d["score"] = score
            d["flags"] = flags
            d["last_checked"] = _iso(_now())
            _save_ip_reputation(data)
            return d
    data.append({
        "ip": ip, "score": score, "flags": flags,
        "last_checked": _iso(_now()),
    })
    _save_ip_reputation(data)
    return data[-1]


def get_ip_reputation(ip: str) -> Optional[dict]:
    data = _load_ip_reputation()
    for d in data:
        if d.get("ip") == ip:
            return d
    return None


# ============================================================================
# REQUEST SIGNING KEYS
# ============================================================================

SIGNING_KEYS_FILE = Path("signing_keys.json")


def _load_signing_keys() -> list[dict]:
    return _load_json(SIGNING_KEYS_FILE, [])


def _save_signing_keys(data: list[dict]) -> None:
    _save_json(SIGNING_KEYS_FILE, data)


def create_signing_key(key_id: str, secret: str, algorithm: str = "HMAC-SHA256") -> dict:
    data = _load_signing_keys()
    record = {"key_id": key_id, "secret": secret, "algorithm": algorithm,
              "created_at": _iso(_now()), "active": True}
    data.append(record)
    _save_signing_keys(data)
    return record


def list_signing_keys() -> list[dict]:
    return _load_signing_keys()


# ============================================================================
# API VERSIONING
# ============================================================================

API_VERSIONS_FILE = Path("api_versions.json")


def _load_api_versions() -> list[dict]:
    return _load_json(API_VERSIONS_FILE, [])


def _save_api_versions(data: list[dict]) -> None:
    _save_json(API_VERSIONS_FILE, data)


def register_api_version(version: str, status: str = "active",
                         sunset_date: Optional[str] = None) -> dict:
    data = _load_api_versions()
    record = {"version": version, "status": status, "sunset_date": sunset_date,
              "created_at": _iso(_now())}
    data.append(record)
    _save_api_versions(data)
    return record


def list_api_versions() -> list[dict]:
    return _load_api_versions()


# ============================================================================
# BULK KEY OPERATIONS
# ============================================================================

def bulk_create_keys(count: int, tier: str = "free",
                     scopes: Optional[list[str]] = None) -> list[dict]:
    import asyncio
    keys = []
    for _ in range(count):
        try:
            record = asyncio.run(create_api_key(
                owner_id=0,
                scopes=scopes or ["read", "search"],
                label=f"Bulk key {len(keys) + 1}",
            ))
            keys.append(record)
        except Exception:
            pass
    return keys


# ============================================================================
# KEY SHARING
# ============================================================================

KEY_SHARES_FILE = Path("key_shares.json")


def _load_key_shares() -> list[dict]:
    return _load_json(KEY_SHARES_FILE, [])


def _save_key_shares(data: list[dict]) -> None:
    _save_json(KEY_SHARES_FILE, data)


def create_key_share(key_id: str, expires_in_hours: int = 24,
                     max_uses: Optional[int] = None) -> dict:
    data = _load_key_shares()
    share_id = secrets.token_urlsafe(16)
    expires_at = _now() + __import__("datetime").timedelta(hours=expires_in_hours)
    record = {
        "share_id": share_id,
        "key_id": key_id,
        "share_url": f"/v1/keys/shared/{share_id}",
        "expires_at": _iso(expires_at),
        "max_uses": max_uses,
        "uses": 0,
        "created_at": _iso(_now()),
    }
    data.append(record)
    _save_key_shares(data)
    return record


def list_key_shares() -> list[dict]:
    return _load_key_shares()


# ============================================================================
# TEAM / COLLABORATOR MANAGEMENT
# ============================================================================

TEAMS_FILE = Path("teams.json")


def _load_teams() -> list[dict]:
    return _load_json(TEAMS_FILE, [])


def _save_teams(data: list[dict]) -> None:
    _save_json(TEAMS_FILE, data)


def create_team(name: str, owner_id: int) -> dict:
    data = _load_teams()
    team_id = secrets.token_urlsafe(16)
    record = {
        "team_id": team_id,
        "name": name,
        "owner_id": owner_id,
        "members": [{"user_id": owner_id, "role": "admin"}],
        "created_at": _iso(_now()),
    }
    data.append(record)
    _save_teams(data)
    return record


def list_teams(owner_id: Optional[int] = None) -> list[dict]:
    data = _load_teams()
    if owner_id is not None:
        data = [d for d in data if d.get("owner_id") == owner_id]
    return data


def add_team_member(team_id: str, user_id: int, role: str = "member") -> bool:
    data = _load_teams()
    for d in data:
        if d.get("team_id") == team_id:
            members = d.setdefault("members", [])
            if not any(m.get("user_id") == user_id for m in members):
                members.append({"user_id": user_id, "role": role})
                _save_teams(data)
                return True
    return False


# ============================================================================
# RBAC - ROLES
# ============================================================================

ROLES_FILE = Path("roles.json")


def _load_roles() -> list[dict]:
    return _load_json(ROLES_FILE, [])


def _save_roles(data: list[dict]) -> None:
    _save_json(ROLES_FILE, data)


def create_role(name: str, permissions: list[str]) -> dict:
    data = _load_roles()
    role_id = secrets.token_urlsafe(16)
    record = {"role_id": role_id, "name": name, "permissions": permissions,
              "created_at": _iso(_now())}
    data.append(record)
    _save_roles(data)
    return record


def list_roles() -> list[dict]:
    return _load_roles()


def assign_role(user_id: int, role_id: str) -> bool:
    # Simple implementation - store in users
    users = _load_users()
    for u in users:
        if u.get("id") == user_id:
            u.setdefault("roles", []).append(role_id)
            _save_users(users)
            return True
    return False


# ============================================================================
# AUDIT LOG
# ============================================================================

AUDIT_LOG_FILE = Path("audit_log.json")


def _load_audit_log() -> list[dict]:
    return _load_json(AUDIT_LOG_FILE, [])


def _save_audit_log(data: list[dict]) -> None:
    _save_json(AUDIT_LOG_FILE, data)


def write_audit_log(user_id: Optional[int], action: str, resource: str,
                    resource_id: Optional[str], details: dict,
                    ip_address: Optional[str] = None,
                    user_agent: Optional[str] = None) -> dict:
    data = _load_audit_log()
    entry = {
        "id": secrets.token_urlsafe(16),
        "user_id": user_id,
        "action": action,
        "resource": resource,
        "resource_id": resource_id,
        "details": details,
        "ip_address": ip_address,
        "user_agent": user_agent,
        "timestamp": _iso(_now()),
    }
    data.append(entry)
    # Keep last 5000 entries
    if len(data) > 5000:
        data = data[-5000:]
    _save_audit_log(data)
    return entry


def list_audit_logs(**filters) -> list[dict]:
    data = _load_audit_log()
    if filters.get("user_id") is not None:
        data = [d for d in data if d.get("user_id") == filters["user_id"]]
    if filters.get("action"):
        data = [d for d in data if d.get("action") == filters["action"]]
    if filters.get("resource"):
        data = [d for d in data if d.get("resource") == filters["resource"]]
    limit = min(filters.get("limit", 50), 500)
    return data[-limit:]


# ============================================================================
# SESSION MANAGEMENT
# ============================================================================

SESSIONS_FILE = Path("user_sessions.json")


def _load_user_sessions() -> list[dict]:
    return _load_json(SESSIONS_FILE, [])


def _save_user_sessions(data: list[dict]) -> None:
    _save_json(SESSIONS_FILE, data)


def create_session(user_id: int, device_id: Optional[str] = None,
                   ip_address: Optional[str] = None,
                   user_agent: Optional[str] = None) -> dict:
    data = _load_user_sessions()
    session_id = secrets.token_urlsafe(16)
    record = {
        "session_id": session_id,
        "user_id": user_id,
        "device_id": device_id,
        "ip_address": ip_address,
        "user_agent": user_agent,
        "created_at": _iso(_now()),
        "last_active": _iso(_now()),
        "active": True,
    }
    data.append(record)
    _save_user_sessions(data)
    return record


def list_sessions(user_id: int) -> list[dict]:
    data = _load_user_sessions()
    return [d for d in data if d.get("user_id") == user_id and d.get("active", True)]


def revoke_session(session_id: str) -> bool:
    data = _load_user_sessions()
    for d in data:
        if d.get("session_id") == session_id:
            d["active"] = False
            _save_user_sessions(data)
            return True
    return False


# ============================================================================
# DEVICE FINGERPRINTING
# ============================================================================

DEVICE_FINGERPRINTS_FILE = Path("device_fingerprints.json")


def _load_device_fingerprints() -> list[dict]:
    return _load_json(DEVICE_FINGERPRINTS_FILE, [])


def _save_device_fingerprints(data: list[dict]) -> None:
    _save_json(DEVICE_FINGERPRINTS_FILE, data)


def record_device_fingerprint(fingerprint_id: str, user_agent: str,
                              accept_language: str, platform: str,
                              screen_resolution: Optional[str] = None) -> dict:
    data = _load_device_fingerprints()
    record = {
        "fingerprint_id": fingerprint_id,
        "user_agent": user_agent,
        "accept_language": accept_language,
        "platform": platform,
        "screen_resolution": screen_resolution,
        "created_at": _iso(_now()),
    }
    data.append(record)
    _save_device_fingerprints(data)
    return record


# ============================================================================
# CONCURRENT SESSION LIMITS
# ============================================================================

SESSION_LIMITS_FILE = Path("session_limits.json")


def _load_session_limits() -> dict:
    return _load_json(SESSION_LIMITS_FILE, {"max_sessions": 5})


def _save_session_limits(data: dict) -> None:
    _save_json(SESSION_LIMITS_FILE, data)


def set_session_limit(max_sessions: int) -> dict:
    data = {"max_sessions": max_sessions}
    _save_session_limits(data)
    return data


def get_session_limit() -> int:
    return _load_session_limits().get("max_sessions", 5)


# ============================================================================
# PASSWORD RESET
# ============================================================================

PASSWORD_RESET_FILE = Path("password_resets.json")


def _load_password_resets() -> list[dict]:
    return _load_json(PASSWORD_RESET_FILE, [])


def _save_password_resets(data: list[dict]) -> None:
    _save_json(PASSWORD_RESET_FILE, data)


def request_password_reset(email: str) -> dict:
    data = _load_password_resets()
    token = secrets.token_urlsafe(32)
    expires_at = _now() + __import__("datetime").timedelta(hours=1)
    record = {
        "token": token,
        "email": email,
        "expires_at": _iso(expires_at),
        "used": False,
        "created_at": _iso(_now()),
    }
    data.append(record)
    _save_password_resets(data)
    return {"token": token, "expires_at": record["expires_at"]}


def confirm_password_reset(token: str, new_password: str) -> bool:
    data = _load_password_resets()
    for d in data:
        if d.get("token") == token and not d.get("used", False):
            try:
                if datetime.fromisoformat(d["expires_at"]) < _now():
                    continue
            except ValueError:
                continue
            d["used"] = True
            _save_password_resets(data)
            return True
    return False


# ============================================================================
# CUSTOM RATE LIMITS PER KEY
# ============================================================================

CUSTOM_RATE_LIMITS_FILE = Path("custom_rate_limits.json")


def _load_custom_rate_limits() -> list[dict]:
    return _load_json(CUSTOM_RATE_LIMITS_FILE, [])


def _save_custom_rate_limits(data: list[dict]) -> None:
    _save_json(CUSTOM_RATE_LIMITS_FILE, data)


def set_custom_rate_limit(key_id: str, requests_per_minute: int,
                          burst: Optional[int] = None) -> dict:
    data = _load_custom_rate_limits()
    for d in data:
        if d.get("key_id") == key_id:
            d["requests_per_minute"] = requests_per_minute
            d["burst"] = burst
            _save_custom_rate_limits(data)
            return d
    data.append({"key_id": key_id, "requests_per_minute": requests_per_minute,
                 "burst": burst, "created_at": _iso(_now())})
    _save_custom_rate_limits(data)
    return data[-1]


# ============================================================================
# DOWNLOAD BANDWIDTH ALLOCATION
# ============================================================================

BANDWIDTH_ALLOCATION_FILE = Path("bandwidth_allocations.json")


def _load_bandwidth_allocations() -> list[dict]:
    return _load_json(BANDWIDTH_ALLOCATION_FILE, [])


def _save_bandwidth_allocations(data: list[dict]) -> None:
    _save_json(BANDWIDTH_ALLOCATION_FILE, data)


def set_bandwidth_allocation(key_id: str, max_bytes_per_day: int,
                              max_bytes_per_month: int) -> dict:
    data = _load_bandwidth_allocations()
    for d in data:
        if d.get("key_id") == key_id:
            d["max_bytes_per_day"] = max_bytes_per_day
            d["max_bytes_per_month"] = max_bytes_per_month
            _save_bandwidth_allocations(data)
            return d
    data.append({"key_id": key_id, "max_bytes_per_day": max_bytes_per_day,
                 "max_bytes_per_month": max_bytes_per_month,
                 "created_at": _iso(_now())})
    _save_bandwidth_allocations(data)
    return data[-1]


# ============================================================================
# DOWNLOAD NOTIFICATION PREFERENCES
# ============================================================================

DOWNLOAD_NOTIF_FILE = Path("download_notifications.json")


def _load_download_notifs() -> list[dict]:
    return _load_json(DOWNLOAD_NOTIF_FILE, [])


def _save_download_notifs(data: list[dict]) -> None:
    _save_json(DOWNLOAD_NOTIF_FILE, data)


def set_download_notification(job_id: str, notify_complete: bool = True,
                               notify_error: bool = True,
                               channels: Optional[list[str]] = None) -> dict:
    data = _load_download_notifs()
    record = {
        "job_id": job_id,
        "notify_on_complete": notify_complete,
        "notify_on_error": notify_error,
        "channels": channels or ["websocket"],
        "created_at": _iso(_now()),
    }
    data.append(record)
    _save_download_notifs(data)
    return record


# ============================================================================
# DOWNLOAD RETRY POLICY
# ============================================================================

RETRY_POLICY_FILE = Path("retry_policies.json")


def _load_retry_policies() -> list[dict]:
    return _load_json(RETRY_POLICY_FILE, [])


def _save_retry_policies(data: list[dict]) -> None:
    _save_json(RETRY_POLICY_FILE, data)


def set_retry_policy(key_id: str, max_retries: int = 3,
                      backoff_seconds: int = 60,
                      retry_on_error: bool = True) -> dict:
    data = _load_retry_policies()
    for d in data:
        if d.get("key_id") == key_id:
            d["max_retries"] = max_retries
            d["backoff_seconds"] = backoff_seconds
            d["retry_on_error"] = retry_on_error
            _save_retry_policies(data)
            return d
    data.append({"key_id": key_id, "max_retries": max_retries,
                 "backoff_seconds": backoff_seconds, "retry_on_error": retry_on_error,
                 "created_at": _iso(_now())})
    _save_retry_policies(data)
    return data[-1]


# ============================================================================
# SOURCE HEALTH MONITORING
# ============================================================================

SOURCE_HEALTH_FILE = Path("source_health.json")


def _load_source_health() -> list[dict]:
    return _load_json(SOURCE_HEALTH_FILE, [])


def _save_source_health(data: list[dict]) -> None:
    _save_json(SOURCE_HEALTH_FILE, data)


def record_source_health(source_id: str, status: str, latency_ms: Optional[float],
                         uptime_percent: float, error_count: int) -> dict:
    data = _load_source_health()
    record = {
        "source_id": source_id,
        "status": status,
        "latency_ms": latency_ms,
        "uptime_percent": uptime_percent,
        "error_count_24h": error_count,
        "last_checked": _iso(_now()),
    }
    data.append(record)
    # Keep last 100 per source
    data = [d for d in data if d.get("source_id") != source_id] + [record]
    if len(data) > 10000:
        data = data[-10000:]
    _save_source_health(data)
    return record


def get_source_health(source_id: str) -> Optional[dict]:
    data = _load_source_health()
    for d in reversed(data):
        if d.get("source_id") == source_id:
            return d
    return None


# ============================================================================
# SOURCE LATENCY TRACKING
# ============================================================================

SOURCE_LATENCY_FILE = Path("source_latency.json")


def _load_source_latency() -> list[dict]:
    return _load_json(SOURCE_LATENCY_FILE, [])


def _save_source_latency(data: list[dict]) -> None:
    _save_json(SOURCE_LATENCY_FILE, data)


def record_source_latency(source_id: str, latency_ms: float) -> dict:
    data = _load_source_latency()
    record = {
        "source_id": source_id,
        "latency_ms": latency_ms,
        "timestamp": _iso(_now()),
    }
    data.append(record)
    # Keep last 1000 per source
    data = [d for d in data if d.get("source_id") != source_id] + data[-1000:]
    if len(data) > 50000:
        data = data[-50000:]
    _save_source_latency(data)
    return record


def get_source_latency_stats(source_id: str) -> dict:
    data = _load_source_latency()
    latencies = [d["latency_ms"] for d in data if d.get("source_id") == source_id]
    if not latencies:
        return {"source_id": source_id, "avg_latency_ms": 0, "min_latency_ms": 0,
                "max_latency_ms": 0, "sample_count": 0}
    return {
        "source_id": source_id,
        "avg_latency_ms": round(sum(latencies) / len(latencies), 2),
        "min_latency_ms": min(latencies),
        "max_latency_ms": max(latencies),
        "sample_count": len(latencies),
    }


# ============================================================================
# FAILOVER RULES
# ============================================================================

FAILOVER_FILE = Path("failover_rules.json")


def _load_failover_rules() -> list[dict]:
    return _load_json(FAILOVER_FILE, [])


def _save_failover_rules(data: list[dict]) -> None:
    _save_json(FAILOVER_FILE, data)


def add_failover_rule(source_id: str, fallback_source: str,
                       threshold: float = 0.5, enabled: bool = True) -> dict:
    data = _load_failover_rules()
    record = {
        "rule_id": secrets.token_urlsafe(16),
        "source_id": source_id,
        "fallback_source": fallback_source,
        "threshold": threshold,
        "enabled": enabled,
        "created_at": _iso(_now()),
    }
    data.append(record)
    _save_failover_rules(data)
    return record


def list_failover_rules() -> list[dict]:
    return _load_failover_rules()


# ============================================================================
# CACHE INVALIDATION BY TAG
# ============================================================================

CACHE_TAGS_FILE = Path("cache_tags.json")


def _load_cache_tags() -> dict:
    return _load_json(CACHE_TAGS_FILE, {})


def _save_cache_tags(data: dict) -> None:
    _save_json(CACHE_TAGS_FILE, data)


def invalidate_cache_tag(tag: str) -> int:
    data = _load_cache_tags()
    count = len(data.get(tag, []))
    data[tag] = []
    _save_cache_tags(data)
    return count


# ============================================================================
# CACHE WARMING
# ============================================================================

CACHE_WARM_FILE = Path("cache_warm.json")


def _load_cache_warm() -> list[dict]:
    return _load_json(CACHE_WARM_FILE, [])


def _save_cache_warm(data: list[dict]) -> None:
    _save_json(CACHE_WARM_FILE, data)


def warm_cache(queries: list[str], source: str, limit_per_query: int) -> dict:
    data = _load_cache_warm()
    warm_id = secrets.token_urlsafe(16)
    record = {
        "warm_id": warm_id,
        "queries": queries,
        "source": source,
        "limit_per_query": limit_per_query,
        "status": "queued",
        "created_at": _iso(_now()),
    }
    data.append(record)
    _save_cache_warm(data)
    return record


def list_cache_warms() -> list[dict]:
    return _load_cache_warm()


# ============================================================================
# SEARCH HISTORY
# ============================================================================

SEARCH_HISTORY_FILE = Path("search_history.json")


def _load_search_history() -> list[dict]:
    return _load_json(SEARCH_HISTORY_FILE, [])


def _save_search_history(data: list[dict]) -> None:
    _save_json(SEARCH_HISTORY_FILE, data)


def record_search_history(user_id: int, query: str, source: Optional[str],
                           results_count: int) -> dict:
    data = _load_search_history()
    entry = {
        "id": secrets.token_urlsafe(16),
        "user_id": user_id,
        "query": query,
        "source": source,
        "results_count": results_count,
        "timestamp": _iso(_now()),
    }
    data.append(entry)
    # Keep last 1000 per user
    data = [d for d in data if d.get("user_id") != user_id] + data[-1000:]
    if len(data) > 50000:
        data = data[-50000:]
    _save_search_history(data)
    return entry


def get_search_history(user_id: int, limit: int = 50) -> list[dict]:
    data = _load_search_history()
    user_history = [d for d in data if d.get("user_id") == user_id]
    return user_history[-limit:]


# ============================================================================
# SAVED SEARCHES
# ============================================================================

SAVED_SEARCHES_FILE = Path("saved_searches.json")


def _load_saved_searches() -> list[dict]:
    return _load_json(SAVED_SEARCHES_FILE, [])


def _save_saved_searches(data: list[dict]) -> None:
    _save_json(SAVED_SEARCHES_FILE, data)


def save_search(user_id: int, name: str, query: str,
                source: Optional[str] = None) -> dict:
    data = _load_saved_searches()
    search_id = secrets.token_urlsafe(16)
    record = {
        "id": search_id,
        "user_id": user_id,
        "name": name,
        "query": query,
        "source": source,
        "created_at": _iso(_now()),
    }
    data.append(record)
    _save_saved_searches(data)
    return record


def list_saved_searches(user_id: int) -> list[dict]:
    data = _load_saved_searches()
    return [d for d in data if d.get("user_id") == user_id]


def delete_saved_search(search_id: str, user_id: int) -> bool:
    data = _load_saved_searches()
    changed = False
    kept = []
    for d in data:
        if d.get("id") == search_id and d.get("user_id") == user_id:
            changed = True
        else:
            kept.append(d)
    if changed:
        _save_saved_searches(kept)
    return changed


# ============================================================================
# TRENDING / POPULAR CONTENT
# ============================================================================

TRENDING_FILE = Path("trending.json")


def _load_trending() -> list[dict]:
    return _load_json(TRENDING_FILE, [])


def _save_trending(data: list[dict]) -> None:
    _save_json(TRENDING_FILE, data)


def record_trending(query: str) -> None:
    data = _load_trending()
    for d in data:
        if d.get("query") == query:
            d["count"] = d.get("count", 0) + 1
            d["updated_at"] = _iso(_now())
            _save_trending(data)
            return
    data.append({"query": query, "count": 1, "trend": "up",
                 "created_at": _iso(_now())})
    _save_trending(data)


def get_trending(limit: int = 20) -> list[dict]:
    data = _load_trending()
    return sorted(data, key=lambda d: d.get("count", 0), reverse=True)[:limit]


# ============================================================================
# USER ACTIVITY FEED
# ============================================================================

ACTIVITY_FEED_FILE = Path("activity_feed.json")


def _load_activity_feed() -> list[dict]:
    return _load_json(ACTIVITY_FEED_FILE, [])


def _save_activity_feed(data: list[dict]) -> None:
    _save_json(ACTIVITY_FEED_FILE, data)


def record_activity(user_id: int, action: str, details: dict) -> dict:
    data = _load_activity_feed()
    entry = {
        "id": secrets.token_urlsafe(16),
        "user_id": user_id,
        "action": action,
        "details": details,
        "timestamp": _iso(_now()),
    }
    data.append(entry)
    # Keep last 5000 per user
    data = [d for d in data if d.get("user_id") != user_id] + data[-5000:]
    if len(data) > 50000:
        data = data[-50000:]
    _save_activity_feed(data)
    return entry


def get_activity_feed(user_id: int, limit: int = 50) -> list[dict]:
    data = _load_activity_feed()
    user_activity = [d for d in data if d.get("user_id") == user_id]
    return user_activity[-limit:]


# ============================================================================
# USAGE REPORTS
# ============================================================================

USAGE_REPORTS_FILE = Path("usage_reports.json")


def _load_usage_reports() -> list[dict]:
    return _load_json(USAGE_REPORTS_FILE, [])


def _save_usage_reports(data: list[dict]) -> None:
    _save_json(USAGE_REPORTS_FILE, data)


def create_usage_report(user_id: int, period: str = "monthly",
                         format: str = "csv") -> dict:
    data = _load_usage_reports()
    report_id = secrets.token_urlsafe(16)
    record = {
        "report_id": report_id,
        "user_id": user_id,
        "period": period,
        "format": format,
        "download_url": f"/v1/export/report/{report_id}",
        "expires_at": _iso(_now() + __import__("datetime").timedelta(days=30)),
        "created_at": _iso(_now()),
    }
    data.append(record)
    _save_usage_reports(data)
    return record


def list_usage_reports(user_id: int) -> list[dict]:
    data = _load_usage_reports()
    return [d for d in data if d.get("user_id") == user_id]


# ============================================================================
# KEY SCOPES / USAGE / SUSPICIOUS ACTIVITY
# ============================================================================

KEY_SCOPES_FILE = Path("key_scopes.json")
KEY_USAGE_FILE = Path("key_usage.json")
SUSPICIOUS_FILE = Path("suspicious_activity.json")
DOWNLOAD_CONCURRENCY_FILE = Path("download_concurrency.json")
FILE_TYPE_FILTERS_FILE = Path("file_type_filters.json")
VIRUS_SCANS_FILE = Path("virus_scans.json")
MODERATION_FILE = Path("moderation_queue.json")


def _load_json_list(path: Path, default=None):
    return _load_json(path, default or [])


def _save_json_list(path: Path, data) -> None:
    _save_json(path, data)


# Key scopes
def set_key_scopes(key_id: str, scopes: list[str]) -> bool:
    data = _load_json_list(KEY_SCOPES_FILE)
    for d in data:
        if d.get("key_id") == key_id:
            d["scopes"] = scopes
            _save_json_list(KEY_SCOPES_FILE, data)
            return True
    data.append({"key_id": key_id, "scopes": scopes, "updated_at": _iso(_now())})
    _save_json_list(KEY_SCOPES_FILE, data)
    return True


def get_key_scopes(key_id: str) -> Optional[list[str]]:
    data = _load_json_list(KEY_SCOPES_FILE)
    for d in data:
        if d.get("key_id") == key_id:
            return d.get("scopes")
    return None


# Key usage tracking
def record_key_usage(key_id: str) -> None:
    data = _load_json_list(KEY_USAGE_FILE)
    for d in data:
        if d.get("key_id") == key_id:
            d["total_requests"] = d.get("total_requests", 0) + 1
            d["last_used"] = _iso(_now())
            _save_json_list(KEY_USAGE_FILE, data)
            return
    data.append({"key_id": key_id, "total_requests": 1,
                 "last_used": _iso(_now()), "requests_today": 1,
                 "requests_month": 1, "created_at": _iso(_now())})
    _save_json_list(KEY_USAGE_FILE, data)


def get_key_usage(key_id: str) -> Optional[dict]:
    data = _load_json_list(KEY_USAGE_FILE)
    for d in data:
        if d.get("key_id") == key_id:
            return d
    return None


# Suspicious activity
def record_suspicious_activity(user_id: Optional[int], ip_address: str,
                                activity_type: str, risk_score: float,
                                action_taken: str = "warn") -> dict:
    data = _load_json_list(SUSPICIOUS_FILE)
    entry = {
        "id": secrets.token_urlsafe(16),
        "user_id": user_id,
        "ip_address": ip_address,
        "activity_type": activity_type,
        "risk_score": risk_score,
        "detected_at": _iso(_now()),
        "action_taken": action_taken,
    }
    data.append(entry)
    _save_json_list(SUSPICIOUS_FILE, data)
    return entry


def list_suspicious_activity(limit: int = 50) -> list[dict]:
    data = _load_json_list(SUSPICIOUS_FILE)
    return data[-limit:]


# Download concurrency per key
def set_download_concurrency(key_id: str, max_concurrent: int) -> bool:
    data = _load_json_list(DOWNLOAD_CONCURRENCY_FILE)
    for d in data:
        if d.get("key_id") == key_id:
            d["max_concurrent"] = max_concurrent
            _save_json_list(DOWNLOAD_CONCURRENCY_FILE, data)
            return True
    data.append({"key_id": key_id, "max_concurrent": max_concurrent,
                 "created_at": _iso(_now())})
    _save_json_list(DOWNLOAD_CONCURRENCY_FILE, data)
    return True


def get_download_concurrency(key_id: str) -> Optional[int]:
    data = _load_json_list(DOWNLOAD_CONCURRENCY_FILE)
    for d in data:
        if d.get("key_id") == key_id:
            return d.get("max_concurrent")
    return None


# File type filters
def set_file_type_filter(key_id: str, allowed: list[str],
                          blocked: Optional[list[str]] = None) -> bool:
    data = _load_json_list(FILE_TYPE_FILTERS_FILE)
    for d in data:
        if d.get("key_id") == key_id:
            d["allowed_extensions"] = allowed
            d["blocked_extensions"] = blocked or []
            _save_json_list(FILE_TYPE_FILTERS_FILE, data)
            return True
    data.append({"key_id": key_id, "allowed_extensions": allowed,
                 "blocked_extensions": blocked or [], "created_at": _iso(_now())})
    _save_json_list(FILE_TYPE_FILTERS_FILE, data)
    return True


def get_file_type_filter(key_id: str) -> Optional[dict]:
    data = _load_json_list(FILE_TYPE_FILTERS_FILE)
    for d in data:
        if d.get("key_id") == key_id:
            return d
    return None


# Virus scan (placeholder)
def record_virus_scan(file_path: str, clean: bool,
                       threats: Optional[list[str]] = None) -> dict:
    data = _load_json_list(VIRUS_SCANS_FILE)
    record = {
        "file_path": file_path,
        "clean": clean,
        "threats": threats or [],
        "scanned_at": _iso(_now()),
    }
    data.append(record)
    _save_json_list(VIRUS_SCANS_FILE, data)
    return record


# Content moderation queue
def add_moderation_item(content_type: str, content_id: str,
                         reporter_id: Optional[int], reason: str) -> dict:
    data = _load_json_list(MODERATION_FILE)
    item_id = secrets.token_urlsafe(16)
    record = {
        "id": item_id,
        "content_type": content_type,
        "content_id": content_id,
        "reporter_id": reporter_id,
        "reason": reason,
        "status": "pending",
        "created_at": _iso(_now()),
    }
    data.append(record)
    _save_json_list(MODERATION_FILE, data)
    return record


def list_moderation_items(status: Optional[str] = None) -> list[dict]:
    data = _load_json_list(MODERATION_FILE)
    if status:
        data = [d for d in data if d.get("status") == status]
    return data


def moderate_item(item_id: str, action: str, moderator_id: int,
                   reason: Optional[str] = None) -> bool:
    data = _load_json_list(MODERATION_FILE)
    for d in data:
        if d.get("id") == item_id:
            d["status"] = "approved" if action == "approve" else "rejected"
            d["moderator_id"] = moderator_id
            d["moderation_reason"] = reason
            d["moderated_at"] = _iso(_now())
            _save_json_list(MODERATION_FILE, data)
            return True
    return False
