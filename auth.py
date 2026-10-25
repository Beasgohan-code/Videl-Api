"""API key authentication with MongoDB backend and JSON file fallback."""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import Header, HTTPException, status

from config import settings
from models import ApiKeyRecord

KEYS_FILE = Path("api_keys.json")
_MONGO_CLIENT = None
_MONGO_COLL = None
_MONGO_OK = False


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _mongo_coll():
    global _MONGO_CLIENT, _MONGO_COLL, _MONGO_OK
    if _MONGO_OK is False:
        return None
    if _MONGO_COLL is not None:
        return _MONGO_COLL
    if not settings.api_keys_enabled:
        return None
    try:
        # Quick reachability check with the sync client (1s timeout).
        from pymongo import MongoClient

        sync_client = MongoClient(
            settings.mongodb_uri,
            serverSelectionTimeoutMS=1000,
            connectTimeoutMS=1000,
        )
        sync_client.admin.command("ping")
        sync_client.close()

        # MongoDB is up — create the async motor client for real ops.
        from motor.motor_asyncio import AsyncIOMotorClient

        _MONGO_CLIENT = AsyncIOMotorClient(
            settings.mongodb_uri,
            serverSelectionTimeoutMS=1500,
            connectTimeoutMS=1500,
        )
        _MONGO_COLL = _MONGO_CLIENT[settings.mongodb_db]["api_keys"]
        _MONGO_OK = True
        return _MONGO_COLL
    except Exception:
        _MONGO_OK = False
        _MONGO_COLL = None
        return None


def _load_file_keys() -> list:
    if not KEYS_FILE.exists():
        return []
    try:
        return json.loads(KEYS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save_file_keys(keys: list) -> None:
    KEYS_FILE.write_text(json.dumps(keys, indent=2, default=str), encoding="utf-8")


def _find_file_key(key: str) -> Optional[dict]:
    for record in _load_file_keys():
        if record.get("key") == key:
            return record
    return None


def generate_api_key() -> str:
    return secrets.token_urlsafe(32)


def is_admin_key(key: str) -> bool:
    return bool(settings.admin_keys and key in settings.admin_keys)


async def validate_api_key(x_api_key: str = Header(default="", alias="X-API-Key")) -> dict:
    """Validate an API key. Returns the key record (dict)."""
    if not settings.api_keys_enabled:
        return {"key": "open", "owner_id": 0, "active": True}

    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing API key"
        )

    if is_admin_key(x_api_key):
        return {"key": x_api_key, "owner_id": 0, "active": True, "admin": True}

    coll = _mongo_coll()
    if coll is not None:
        try:
            record = await coll.find_one({"key": x_api_key})
            if record is None or not record.get("active", True):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key"
                )
            await coll.update_one(
                {"_id": record["_id"]},
                {"$set": {"last_used_at": _now()}},
            )
            record.pop("_id", None)
            return record
        except HTTPException:
            raise
        except Exception:
            coll = None

    record = _find_file_key(x_api_key)
    if record is None or not record.get("active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key"
        )
    record["last_used_at"] = _now().isoformat()
    return record


async def create_api_key(owner_id: int) -> ApiKeyRecord:
    api_key = generate_api_key()
    now = _now()
    record = ApiKeyRecord(
        key=api_key,
        owner_id=owner_id,
        active=True,
        created_at=now,
        last_used_at=None,
    )

    coll = _mongo_coll()
    if coll is not None:
        try:
            await coll.create_index("key", unique=True)
            await coll.create_index("owner_id")
            await coll.create_index("active")
            await coll.create_index("created_at")
            await coll.insert_one(
                {
                    "key": api_key,
                    "owner_id": owner_id,
                    "active": True,
                    "created_at": now,
                    "last_used_at": None,
                }
            )
            return record
        except Exception:
            pass

    keys = _load_file_keys()
    keys.append(record.model_dump())
    _save_file_keys(keys)
    return record


async def list_api_keys(owner_id: int) -> list:
    out: list = []

    coll = _mongo_coll()
    if coll is not None:
        try:
            cursor = coll.find({"owner_id": owner_id}).sort("created_at", -1)
            async for doc in cursor:
                doc.pop("_id", None)
                out.append(doc)
            return out
        except Exception:
            pass

    for rec in _load_file_keys():
        if rec.get("owner_id") == owner_id:
            out.append(rec)
    return out


async def revoke_api_key(owner_id: int, api_key: str) -> bool:
    coll = _mongo_coll()
    if coll is not None:
        try:
            result = await coll.update_one(
                {"owner_id": owner_id, "key": api_key},
                {"$set": {"active": False, "revoked_at": _now()}},
            )
            return result.modified_count > 0
        except Exception:
            pass

    keys = _load_file_keys()
    changed = False
    for rec in keys:
        if rec.get("owner_id") == owner_id and rec.get("key") == api_key:
            rec["active"] = False
            rec["revoked_at"] = _now().isoformat()
            changed = True
    if changed:
        _save_file_keys(keys)
    return changed
