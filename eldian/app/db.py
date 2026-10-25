# MIT License - Copyright (c) 2026 Videl Network

from motor.motor_asyncio import AsyncIOMotorClient

from .config import settings


client = AsyncIOMotorClient(settings.mongodb_uri)
database = client[settings.mongodb_db]
api_keys_collection = database["api_keys"]


async def ensure_indexes() -> None:
    await api_keys_collection.create_index("key", unique=True)
    await api_keys_collection.create_index("owner_id")
    await api_keys_collection.create_index("active")
    await api_keys_collection.create_index("created_at")
