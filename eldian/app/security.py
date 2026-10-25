# MIT License - Copyright (c) 2026 Videl Network

import secrets
from datetime import datetime, timezone

from fastapi import Header, HTTPException, status

from .db import api_keys_collection


def generate_api_key() -> str:
    return secrets.token_urlsafe(32)


async def create_api_key(owner_id: int) -> str:
    api_key = generate_api_key()
    await api_keys_collection.insert_one(
        {
            "key": api_key,
            "owner_id": owner_id,
            "active": True,
            "created_at": datetime.now(timezone.utc),
            "last_used_at": None,
        }
    )
    return api_key


async def list_api_keys(owner_id: int) -> list[dict]:
    cursor = api_keys_collection.find(
        {"owner_id": owner_id},
        {"_id": 0, "key": 1, "owner_id": 1, "active": 1, "created_at": 1, "last_used_at": 1},
    ).sort("created_at", -1)
    return [document async for document in cursor]


async def revoke_api_key(owner_id: int, api_key: str) -> bool:
    result = await api_keys_collection.update_one(
        {"owner_id": owner_id, "key": api_key},
        {"$set": {"active": False, "revoked_at": datetime.now(timezone.utc)}},
    )
    return result.modified_count > 0


async def validate_api_key(x_api_key: str = Header(default="", alias="X-API-Key")) -> dict:
    if not x_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing API key")

    record = await api_keys_collection.find_one({"key": x_api_key})
    if record is None or not record.get("active", True):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key")

    await api_keys_collection.update_one(
        {"_id": record["_id"]},
        {"$set": {"last_used_at": datetime.now(timezone.utc)}},
    )
    return record
