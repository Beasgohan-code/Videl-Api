"""
Videl-Api Telegram Bot

Full-featured Telegram Bot built on aiogram 3.x:
- Rich messages (inline keyboards, formatted text)
- Inline queries, callback queries, inline keyboards
- Telegram Stars payments (Pro tier upgrade)
- Owner / Admin access control
- User management, tiers, subscriptions
- Search, download, lyrics, info from the API
- Broadcast, stats, admin panel
- Settings, language, notifications
- Webhook integration with the FastAPI backend
"""

from __future__ import annotations

import asyncio
import fcntl
import json
import logging
import os
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from aiogram import Bot
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import settings, list_all_sources, MUSIC_SOURCES
from downloader import (
    DownloadJob,
    search as dl_search,
    extract_info as dl_extract_info,
    extract_lyrics as dl_extract_lyrics,
    download_audio as dl_download_audio,
    embed_metadata as dl_embed_metadata,
    enqueue_download as dl_enqueue_download,
    get_job as dl_get_job,
    list_jobs as dl_list_jobs,
    JOBS,
)
from auth import (
    create_api_key as auth_create_key,
    list_api_keys as auth_list_keys,
    revoke_api_key as auth_revoke_key,
    patch_api_key as auth_patch_key,
    rotate_api_key as auth_rotate_key,
    _load_json,
    _save_json,
    KEYS_FILE,
    USERS_FILE,
)

logger = logging.getLogger("videl.telegram_bot")

# ---------------------------------------------------------------------------
# Bot instance (lazy init) - aiogram
# ---------------------------------------------------------------------------

_bot: Optional[Bot] = None
_bot_lock = asyncio.Lock()
_bot_initialized = False
_polling_active = False
_poll_lock_file: Optional[Any] = None


async def get_bot() -> Optional[Bot]:
    global _bot, _bot_initialized
    async with _bot_lock:
        if _bot_initialized:
            return _bot
        token = settings.telegram_bot_token
        if not token:
            logger.warning("TELEGRAM_BOT_TOKEN not set; bot disabled")
            _bot_initialized = True
            return None
        _bot = Bot(
            token=token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        _bot_initialized = True
        logger.info("Telegram Bot (aiogram) initialized")
        return _bot


# ---------------------------------------------------------------------------
# User / tier / key storage helpers (JSON fallback)
# ---------------------------------------------------------------------------

USERS_FILE = Path(os.path.join(os.path.dirname(str(KEYS_FILE)), "users.json")) if KEYS_FILE else Path("users.json")


def _load_users() -> list[dict]:
    return _load_json(USERS_FILE, [])


def _save_users(users: list[dict]) -> None:
    _save_json(USERS_FILE, users)


def _get_or_create_user(telegram_id: int, username: str = "", first_name: str = "") -> dict:
    users = _load_users()
    for u in users:
        if u.get("telegram_id") == telegram_id:
            return u
    # Owner detection: first user or matching owner id
    is_owner = bool(settings.telegram_bot_owner_id and telegram_id == settings.telegram_bot_owner_id)
    is_admin = is_owner or telegram_id in settings.telegram_bot_admins
    user = {
        "id": str(uuid.uuid4()),
        "telegram_id": telegram_id,
        "username": username,
        "first_name": first_name,
        "tier": "owner" if is_owner else "free",
        "scopes": ["read", "search", "download", "admin"] if is_owner else ["read", "search"],
        "is_admin": is_admin,
        "is_owner": is_owner,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
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
    users.append(user)
    _save_users(users)
    logger.info(f"New user registered: tg_id={telegram_id} owner={is_owner} admin={is_admin}")
    return user


def _set_user_field(telegram_id: int, field: str, value: Any) -> None:
    users = _load_users()
    for u in users:
        if u.get("telegram_id") == telegram_id:
            u[field] = value
            u["updated_at"] = datetime.now(timezone.utc).isoformat()
            break
    _save_users(users)


def _increment_counter(telegram_id: int, field: str, amount: int = 1) -> None:
    users = _load_users()
    for u in users:
        if u.get("telegram_id") == telegram_id:
            u[field] = u.get(field, 0) + amount
            u["updated_at"] = datetime.now(timezone.utc).isoformat()
            break
    _save_users(users)


# ---------------------------------------------------------------------------
# Key tier limits
# ---------------------------------------------------------------------------

TIER_LIMITS = {
    "free": {
        "daily": 100,
        "monthly": 1000,
        "daily_bytes": 100 * 1024 * 1024,
        "monthly_bytes": 1024 * 1024 * 1024,
        "rate": 100,
        "scopes": ["read", "search"],
    },
    "pro": {
        "daily": 1000,
        "monthly": 30000,
        "daily_bytes": 1024 * 1024 * 1024,
        "monthly_bytes": 10 * 1024 * 1024 * 1024,
        "rate": 1000,
        "scopes": ["read", "search", "download"],
    },
    "owner": {
        "daily": 0,
        "monthly": 0,
        "daily_bytes": 0,
        "monthly_bytes": 0,
        "rate": None,
        "scopes": ["read", "search", "download", "admin"],
    },
}


# ---------------------------------------------------------------------------
# Inline keyboard builders (aiogram types)
# ---------------------------------------------------------------------------

def _cb_button(text: str, callback_data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback_data)


def _url_button(text: str, url: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, url=url)


def _keyboard(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


def main_menu_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [_cb_button("🔍 Search", "cb:search"), _cb_button("📥 Download", "cb:download")],
        [_cb_button("🎵 Info", "cb:info"), _cb_button("📝 Lyrics", "cb:lyrics")],
        [_cb_button("🔑 API Keys", "cb:keys"), _cb_button("💎 Tier", "cb:tier")],
        [_cb_button("💳 Buy Pro", "cb:buy"), _cb_button("📋 Playlist", "cb:playlist")],
        [_cb_button("📊 Stats", "cb:stats"), _cb_button("⚙️ Settings", "cb:settings")],
        [_cb_button("📡 Sources", "cb:sources"), _cb_button("📢 Status", "cb:status")],
    ]
    if is_admin:
        rows.append([_cb_button("👑 Admin Panel", "cb:admin")])
    rows.append([_cb_button("❓ Help", "cb:help")])
    return _keyboard(rows)


def tier_keyboard() -> InlineKeyboardMarkup:
    return _keyboard([
        [_cb_button("🆓 Free", "cb:tier:free"), _cb_button("💎 Pro (100 Stars)", "cb:tier:pro")],
        [_cb_button("👑 Owner (Contact Admin)", "cb:tier:owner")],
        [_cb_button("⬅️ Back", "cb:menu")],
    ])


def keys_keyboard() -> InlineKeyboardMarkup:
    return _keyboard([
        [_cb_button("➕ Create Key", "cb:key:create"), _cb_button("📋 List Keys", "cb:key:list")],
        [_cb_button("🔄 Rotate Key", "cb:key:rotate"), _cb_button("❌ Revoke Key", "cb:key:revoke")],
        [_cb_button("⬅️ Back", "cb:menu")],
    ])


def admin_keyboard() -> InlineKeyboardMarkup:
    return _keyboard([
        [_cb_button("👥 Users", "cb:admin:users"), _cb_button("📊 Stats", "cb:admin:stats")],
        [_cb_button("📢 Broadcast", "cb:admin:broadcast"), _cb_button("🔑 All Keys", "cb:admin:keys")],
        [_cb_button("⚙️ System", "cb:admin:system"), _cb_button("⬅️ Back", "cb:menu")],
    ])


def settings_keyboard() -> InlineKeyboardMarkup:
    return _keyboard([
        [_cb_button("🌐 Language", "cb:settings:lang"), _cb_button("𔔨 Notifications", "cb:settings:notify")],
        [_cb_button("⬅️ Back", "cb:menu")],
    ])


# ---------------------------------------------------------------------------
# Rich message builders
# ---------------------------------------------------------------------------

def build_welcome_message(first_name: str, is_admin: bool = False, is_owner: bool = False) -> str:
    role_line = ""
    if is_owner:
        role_line = "\n👑 <b>Owner mode enabled.</b>"
    elif is_admin:
        role_line = "\n👮 <b>Admin mode enabled.</b>"
    return (
        f"🎵 <b>Welcome to Videl-Api Bot, {first_name}!</b>\n\n"
        f"A powerful multi-source media API right in your Telegram.\n\n"
        f"<b>What I can do:</b>\n"
        f"🔍 Search music &amp; media across 1000+ sources\n"
        f"📥 Download audio/video tracks\n"
        f"🎵 Get track info &amp; lyrics\n"
        f"🔑 Create &amp; manage API keys\n"
        f"💎 Upgrade tiers (Free / Pro / Owner)\n"
        f"💳 Pay with Telegram Stars\n"
        f"📋 Manage playlists &amp; downloads\n"
        f"📊 View stats &amp; notifications\n\n"
        f"Use /help to see all commands.{role_line}"
    )


def build_help_message(is_admin: bool = False, is_owner: bool = False) -> str:
    cmds = [
        ("/start", "Welcome & main menu"),
        ("/help", "Show this help message"),
        ("/search", "Search music & media"),
        ("/download", "Download a track by URL"),
        ("/info", "Get track/album info"),
        ("/lyrics", "Get lyrics for a track"),
        ("/key", "Manage your API keys"),
        ("/tier", "View & change subscription tier"),
        ("/buy", "Buy Pro tier with Telegram Stars"),
        ("/playlist", "Manage your playlists"),
        ("/history", "View download history"),
        ("/settings", "User settings & language"),
        ("/notify", "Notification preferences"),
        ("/source", "List supported sources"),
        ("/status", "System status"),
        ("/feedback", "Send feedback"),
        ("/language", "Change interface language"),
    ]
    if is_admin or is_owner:
        cmds += [
            ("/admin", "Admin panel"),
            ("/broadcast", "Broadcast to all users"),
            ("/users", "User management"),
            ("/stats", "Bot statistics"),
        ]

    lines = [f"<b>/{c}</b> — {d}" for c, d in cmds]
    return "📚 <b>Available Commands</b>\n\n" + "\n".join(lines) + "\n\n💡 Tip: Use inline mode @botname to search from any chat!"


def build_tier_message(tier: str, is_admin: bool = False) -> str:
    limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
    daily_str = "∞" if limits["daily"] == 0 else str(limits["daily"])
    monthly_str = "∞" if limits["monthly"] == 0 else str(limits["monthly"])
    rate_str = "∞" if limits["rate"] is None else str(limits["rate"])
    return (
        f"💎 <b>Your Tier: {tier.upper()}</b>\n\n"
        f"📊 Daily requests: {daily_str}\n"
        f"📊 Monthly requests: {monthly_str}\n"
        f"📊 Daily bytes: {limits['daily_bytes'] / (1024*1024):.0f} MB\n"
        f"📊 Monthly bytes: {limits['monthly_bytes'] / (1024*1024*1024):.0f} GB\n"
        f"⚡ Rate limit: {rate_str} req/min\n"
        f"🔑 Scopes: {', '.join(limits['scopes'])}\n\n"
        f"Upgrade to Pro with /buy or contact admin for Owner access."
    )


# ---------------------------------------------------------------------------
# Helper to send messages via aiogram Bot
# ---------------------------------------------------------------------------

async def _send_message(
    bot: Bot,
    chat_id: int | str,
    text: str,
    *,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    reply_to_message_id: Optional[int] = None,
    disable_web_page_preview: bool = True,
) -> None:
    await bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=reply_markup,
        reply_to_message_id=reply_to_message_id,
        disable_web_page_preview=disable_web_page_preview,
    )


async def _send_invoice(
    bot: Bot,
    chat_id: int | str,
    title: str,
    description: str,
    payload_str: str,
    currency: str = "XTR",
    prices: list[dict] | None = None,
    provider_token: str = "",
    start_parameter: str = "stars",
    reply_markup: Optional[InlineKeyboardMarkup] = None,
) -> None:
    await bot.send_invoice(
        chat_id=chat_id,
        title=title,
        description=description,
        payload=payload_str,
        currency=currency,
        prices=prices or [{"label": "Pro Tier", "amount": 100}],
        provider_token=provider_token,
        start_parameter=start_parameter,
        reply_markup=reply_markup,
    )


# ---------------------------------------------------------------------------
# Bot owner DM notifications (start / stop / errors / logs)
# ---------------------------------------------------------------------------

async def _send_owner_message(
    bot: Bot,
    text: str,
    *,
    parse_mode: str = "HTML",
) -> None:
    """Send a log/notification message to the bot owner's DM."""
    owner_id = settings.telegram_bot_owner_id
    if not owner_id:
        return
    try:
        await bot.send_message(
            chat_id=owner_id,
            text=text,
            parse_mode=parse_mode,
            disable_web_page_preview=True,
        )
    except Exception as exc:
        logger.warning(f"Failed to send owner DM: {exc}")


async def _send_owner_log(
    bot: Bot,
    level: str,
    message: str,
    *,
    exc: Optional[Exception] = None,
) -> None:
    """Send a formatted log entry to the bot owner's DM."""
    icon = {
        "INFO": "ℹ️",
        "WARNING": "⚠️",
        "ERROR": "❌",
        "CRITICAL": "🔥",
    }.get(level, "📝")

    parts = [f"{icon} <b>{level}</b>\n"]
    parts.append(f"<code>{message}</code>")
    if exc is not None:
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        # Trim traceback to fit Telegram message limits
        short_tb = tb[-1200:] if len(tb) > 1200 else tb
        parts.append(f"\n\n<b>Traceback:</b>\n<pre>{short_tb}</pre>")

    await _send_owner_message(bot, "".join(parts))


# ---------------------------------------------------------------------------
# Answer callback query
# ---------------------------------------------------------------------------

async def _answer_callback_query(
    bot: Bot,
    callback_query_id: str,
    *,
    text: Optional[str] = None,
    show_alert: bool = False,
    url: Optional[str] = None,
    cache_time: Optional[int] = None,
) -> None:
    await bot.answer_callback_query(
        callback_query_id=callback_query_id,
        text=text,
        show_alert=show_alert,
        url=url,
        cache_time=cache_time,
    )


async def _answer_inline_query(
    bot: Bot,
    inline_query_id: str,
    results: list[dict],
    *,
    cache_time: int = 300,
    is_personal: bool = True,
) -> None:
    await bot.answer_inline_query(
        inline_query_id=inline_query_id,
        results=results,
        cache_time=cache_time,
        is_personal=is_personal,
    )


async def _answer_pre_checkout_query(
    bot: Bot,
    pre_checkout_query_id: str,
    ok: bool,
    error_message: Optional[str] = None,
) -> None:
    await bot.answer_pre_checkout_query(
        pre_checkout_query_id=pre_checkout_query_id,
        ok=ok,
        error_message=error_message,
    )


# ---------------------------------------------------------------------------
# Safe handler wrapper (prevents one bad handler from killing the bot)
# ---------------------------------------------------------------------------

async def _safe(handler_name: str, coro) -> None:
    """Run a handler coroutine, logging any exception without crashing."""
    try:
        await coro
    except Exception as exc:
        logger.exception(f"Handler '{handler_name}' failed: {exc}")


# ---------------------------------------------------------------------------
# Handler functions
# ---------------------------------------------------------------------------

async def handle_start(bot: Bot, chat_id: int | str, user: dict, message_id: Optional[int] = None) -> None:
    is_admin = user.get("is_admin", False) or user.get("is_owner", False)
    is_owner = user.get("is_owner", False)
    text = build_welcome_message(user.get("first_name", "User"), is_admin, is_owner)
    kb = main_menu_keyboard(is_admin)
    if message_id:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=kb,
        )
    else:
        await _send_message(bot, chat_id, text, reply_markup=kb)


async def handle_help(bot: Bot, chat_id: int | str, user: dict) -> None:
    is_admin = user.get("is_admin", False) or user.get("is_owner", False)
    is_owner = user.get("is_owner", False)
    text = build_help_message(is_admin, is_owner)
    kb = _keyboard([[_cb_button("⬅️ Back to Menu", "cb:menu")]])
    await _send_message(bot, chat_id, text, reply_markup=kb)


async def handle_tier(bot: Bot, chat_id: int | str, user: dict) -> None:
    tier = user.get("tier", "free")
    is_admin = user.get("is_admin", False) or user.get("is_owner", False)
    text = build_tier_message(tier, is_admin)
    await _send_message(bot, chat_id, text, reply_markup=tier_keyboard())


async def handle_search(bot: Bot, chat_id: int | str, user: dict, query: Optional[str] = None) -> None:
    if not query:
        text = (
            "🔍 <b>Search</b>\n\n"
            "Send me a search query or use inline mode.\n"
            "Example: /search imagine dragons"
        )
        kb = _keyboard([[_cb_button("⬅️ Back", "cb:menu")]])
        await _send_message(bot, chat_id, text, reply_markup=kb)
        return

    _increment_counter(user["telegram_id"], "search_count")
    try:
        results = await dl_search(query, source="youtube", limit=5)
    except Exception as exc:
        await _send_message(bot, chat_id, f"❌ Search failed: {exc}")
        return

    if not results:
        await _send_message(bot, chat_id, "🔍 No results found.")
        return

    lines = [f"🔍 <b>Search results for:</b> {query}\n"]
    buttons = []
    for i, r in enumerate(results):
        title = r.get("title", "Unknown")
        uploader = r.get("uploader", "Unknown")
        dur = r.get("duration")
        dur_str = f" ({dur}s)" if dur else ""
        lines.append(f"{i+1}. <b>{title}</b> — {uploader}{dur_str}")
        buttons.append([_cb_button(f"⬇️ {title[:30]}", f"cb:dl:{r.get('url','')}")])

    buttons.append([_cb_button("⬅️ Back", "cb:menu")])
    await _send_message(bot, chat_id, "\n".join(lines), reply_markup=_keyboard(buttons))


async def handle_download_url(bot: Bot, chat_id: int | str, user: dict, url: str) -> None:
    """Enqueue a download for a given URL."""
    _increment_counter(user["telegram_id"], "download_count")
    try:
        job = DownloadJob(
            job_id=uuid.uuid4().hex,
            url=url,
            source="youtube",
            user_id=user["telegram_id"],
        )
        await dl_enqueue_download(job)
        await _send_message(
            bot,
            chat_id,
            f"📥 <b>Download queued!</b>\n\n"
            f"URL: {url}\n"
            f"Job ID: <code>{job.job_id}</code>\n"
            f"Use /history to track progress.",
        )
    except Exception as exc:
        await _send_message(bot, chat_id, f"❌ Download failed: {exc}")


async def handle_info(bot: Bot, chat_id: int | str, user: dict, query: Optional[str] = None) -> None:
    if not query:
        await _send_message(
            bot,
            chat_id,
            "🎵 <b>Info</b>\n\nSend me a URL or search query.\nExample: /info https://youtu.be/...",
            reply_markup=_keyboard([[_cb_button("⬅️ Back", "cb:menu")]]),
        )
        return
    try:
        info = await dl_extract_info(query)
        if not info:
            await _send_message(bot, chat_id, "❌ Could not extract info.")
            return
        title = info.get("title", "Unknown")
        uploader = info.get("uploader", info.get("channel", "Unknown"))
        dur = info.get("duration")
        dur_str = f"{dur}s" if dur else "?"
        views = info.get("view_count", 0)
        lines = [
            f"🎵 <b>{title}</b>\n",
            f"👤 {uploader}",
            f"⏱️ {dur_str}",
            f"👁️ {views:,} views",
        ]
        await _send_message(bot, chat_id, "\n".join(lines))
    except Exception as exc:
        await _send_message(bot, chat_id, f"❌ Info failed: {exc}")


async def handle_lyrics(bot: Bot, chat_id: int | str, user: dict, query: Optional[str] = None) -> None:
    if not query:
        await _send_message(
            bot,
            chat_id,
            "📝 <b>Lyrics</b>\n\nSend me a song title or URL.\nExample: /lyrics imagine dragons believer",
            reply_markup=_keyboard([[_cb_button("⬅️ Back", "cb:menu")]]),
        )
        return
    try:
        lyrics = await dl_extract_lyrics(query)
        if not lyrics:
            await _send_message(bot, chat_id, "🔍 No lyrics found.")
            return
        # Telegram message limit is 4096 chars
        if len(lyrics) > 3800:
            lyrics = lyrics[:3800] + "\n…"
        await _send_message(bot, chat_id, f"📝 <b>Lyrics:</b>\n\n{lyrics}")
    except Exception as exc:
        await _send_message(bot, chat_id, f"❌ Lyrics failed: {exc}")


async def handle_keys(bot: Bot, chat_id: int | str, user: dict) -> None:
    telegram_id = user["telegram_id"]
    try:
        keys = auth_list_keys(telegram_id)
    except Exception as exc:
        await _send_message(bot, chat_id, f"❌ Failed to list keys: {exc}")
        return
    key_list = keys if isinstance(keys, list) else []

    if not key_list:
        text = "🔑 <b>API Keys</b>\n\nYou don't have any API keys yet.\nCreate one to access the API."
        await _send_message(bot, chat_id, text, reply_markup=keys_keyboard())
        return

    lines = ["🔑 <b>Your API Keys</b>\n"]
    for k in key_list[:5]:
        prefix = k.get("key_prefix", "videl_")
        tier = k.get("tier", "free")
        active = "✅" if k.get("active", True) else "❌"
        lines.append(f"{active} <code>{prefix}…</code> — {tier}")

    lines.append("\nUse the buttons below to manage keys.")
    await _send_message(bot, chat_id, "\n".join(lines), reply_markup=keys_keyboard())


async def handle_create_key(bot: Bot, chat_id: int | str, user: dict) -> None:
    tier = user.get("tier", "free")
    limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
    try:
        record = await auth_create_key(
            owner_id=user["telegram_id"],
            scopes=limits["scopes"],
            rate_limit=limits["rate"],
            label=f"Telegram Bot: {user.get('first_name','')}",
        )
        key_val = record.get("key", "") if isinstance(record, dict) else getattr(record, "key", "")
        key_id = record.get("key_id", "") if isinstance(record, dict) else getattr(record, "key_id", "")
        text = (
            f"🔑 <b>New API Key Created</b>\n\n"
            f"<code>{key_val}</code>\n\n"
            f"Key ID: <code>{key_id}</code>\n"
            f"Tier: {tier}\n"
            f"Scopes: {', '.join(limits['scopes'])}\n"
            f"Rate limit: {limits['rate']} req/min\n\n"
            f"⚠️ Save this key — it won't be shown again."
        )
    except Exception as exc:
        text = f"❌ Failed to create key: {exc}"

    await _send_message(bot, chat_id, text, reply_markup=keys_keyboard())


async def handle_buy(bot: Bot, chat_id: int | str, user: dict) -> None:
    """Send a Telegram Stars invoice for Pro tier upgrade."""
    payload_str = f"upgrade_pro_{user['telegram_id']}_{int(time.time())}"
    prices = [{"label": "Pro Tier Upgrade", "amount": 100}]  # 100 Stars

    try:
        await _send_invoice(
            bot=bot,
            chat_id=chat_id,
            title="Videl-Api Pro Tier",
            description="Upgrade to Pro tier — 1000 daily requests, 10GB monthly, download access",
            payload_str=payload_str,
            currency="XTR",
            prices=prices,
            provider_token="",
            start_parameter="pro_upgrade",
        )
        users = _load_users()
        for u in users:
            if u.get("telegram_id") == user["telegram_id"]:
                u["pending_payment"] = payload_str
                u["pending_payment_tier"] = "pro"
                u["pending_payment_amount"] = 100
                break
        _save_users(users)
    except Exception as exc:
        await _send_message(bot, chat_id, f"❌ Payment setup failed: {exc}")


async def handle_status(bot: Bot, chat_id: int | str) -> None:
    try:
        import aiohttp
        base = settings.api_base_url.rstrip("/")
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{base}/health", timeout=10) as resp:
                health = await resp.json()
    except Exception:
        health = {"status": "unknown", "sources": 0, "features": {}}

    uptime = health.get("uptime_seconds", 0)
    uptime_str = f"{int(uptime // 3600)}h {int((uptime % 3600) // 60)}m"
    features = health.get("features", {})

    lines = [
        "📡 <b>System Status</b>\n",
        f"Status: <b>{health.get('status', 'unknown').upper()}</b>",
        f"Uptime: {uptime_str}",
        f"Sources: {health.get('sources', 0)}",
        "",
        "<b>Features:</b>",
        f"• Search: {'✅' if features.get('search') else '❌'}",
        f"• Lyrics: {'✅' if features.get('lyrics') else '❌'}",
        f"• Metadata embed: {'✅' if features.get('metadata_embed') else '❌'}",
        f"• SponsorBlock: {'✅' if features.get('sponsorblock') else '❌'}",
    ]
    await _send_message(bot, chat_id, "\n".join(lines))


async def handle_sources(bot: Bot, chat_id: int | str) -> None:
    sources = list_all_sources()
    music = [s for s in sources if s["type"] == "music"][:10]
    lines = ["📡 <b>Supported Sources (Music)</b>\n"]
    for s in music:
        search_tag = "🔍" if s.get("supports_search") else ""
        lines.append(f"• {s['name']} {search_tag}")
    lines.append(f"\nTotal: {len(sources)} sources across music, anime, manga, media.")
    await _send_message(bot, chat_id, "\n".join(lines))


async def handle_settings(bot: Bot, chat_id: int | str, user: dict) -> None:
    lang = user.get("language", "en")
    notify = "✅ On" if user.get("notifications", True) else "❌ Off"
    text = (
        f"⚙️ <b>Settings</b>\n\n"
        f"Language: {lang}\n"
        f"Notifications: {notify}\n"
    )
    await _send_message(bot, chat_id, text, reply_markup=settings_keyboard())


async def handle_playlist(bot: Bot, chat_id: int | str, user: dict) -> None:
    text = (
        "📋 <b>Playlists</b>\n\n"
        "Manage your playlists via the API:\n"
        "POST /v1/playlists — Create\n"
        "GET /v1/playlists — List\n"
        "Use inline search to find tracks to add."
    )
    await _send_message(bot, chat_id, text, reply_markup=_keyboard([[_cb_button("⬅️ Back", "cb:menu")]] ))


async def handle_history(bot: Bot, chat_id: int | str, user: dict) -> None:
    try:
        jobs = await dl_list_jobs()
    except Exception as exc:
        await _send_message(bot, chat_id, f"❌ Failed to load history: {exc}")
        return
    user_jobs = [j for j in jobs if j.get("user_id") == user["telegram_id"]] if isinstance(jobs, list) else []
    if not user_jobs:
        await _send_message(bot, chat_id, "📦 No download history yet.")
        return
    lines = ["📦 <b>Recent Downloads</b>\n"]
    for j in user_jobs[-5:]:
        status = j.get("status", "unknown")
        title = j.get("title", "Unknown")
        progress = j.get("progress", 0)
        lines.append(f"• {title} — {status} ({progress:.0f}%)")
    await _send_message(bot, chat_id, "\n".join(lines))


async def handle_notify(bot: Bot, chat_id: int | str, user: dict) -> None:
    current = "✅ On" if user.get("notifications", True) else "❌ Off"
    new_state = not user.get("notifications", True)
    _set_user_field(user["telegram_id"], "notifications", new_state)
    state_str = "✅ On" if new_state else "❌ Off"
    await _send_message(bot, chat_id, f"𔔨 Notifications are now {state_str}.")


async def handle_feedback(bot: Bot, chat_id: int | str, user: dict, text: Optional[str] = None) -> None:
    if not text:
        await _send_message(
            bot,
            chat_id,
            "📝 <b>Feedback</b>\n\nSend your feedback after this message.\nExample: /feedback Great app!",
            reply_markup=_keyboard([[_cb_button("⬅️ Back", "cb:menu")]]),
        )
        return
    users = _load_users()
    for u in users:
        if u.get("telegram_id") == user["telegram_id"]:
            u.setdefault("feedback", []).append({
                "text": text,
                "at": datetime.now(timezone.utc).isoformat(),
            })
            break
    _save_users(users)
    await _send_message(bot, chat_id, "✅ Thank you for your feedback!")


async def handle_language(bot: Bot, chat_id: int | str, user: dict, lang: Optional[str] = None) -> None:
    if not lang:
        kb = _keyboard([
            [_cb_button("English", "cb:lang:en"), _cb_button("Español", "cb:lang:es")],
            [_cb_button("Français", "cb:lang:fr"), _cb_button("中文", "cb:lang:zh")],
            [_cb_button("⬅️ Back", "cb:settings")],
        ])
        await _send_message(bot, chat_id, "🌐 <b>Choose Language</b>", reply_markup=kb)
        return
    _set_user_field(user["telegram_id"], "language", lang)
    await _send_message(bot, chat_id, f"✅ Language set to {lang}.")


# ---------------------------------------------------------------------------
# Admin handlers
# ---------------------------------------------------------------------------

async def handle_admin(bot: Bot, chat_id: int | str, user: dict) -> None:
    if not (user.get("is_admin") or user.get("is_owner")):
        await _send_message(bot, chat_id, "❌ Owner access required.")
        return
    await _send_message(bot, chat_id, "👑 <b>Admin Panel</b>", reply_markup=admin_keyboard())


async def handle_broadcast(bot: Bot, chat_id: int | str, user: dict, text: Optional[str] = None) -> None:
    if not (user.get("is_admin") or user.get("is_owner")):
        await _send_message(bot, chat_id, "❌ Owner access required.")
        return
    if not text:
        await _send_message(bot, chat_id, "Send the broadcast message after /broadcast.")
        return
    users = _load_users()
    sent = 0
    failed = 0
    for u in users:
        try:
            await _send_message(bot, u["telegram_id"], f"📢 <b>Broadcast:</b>\n{text}")
            sent += 1
        except Exception:
            failed += 1
    await _send_message(bot, chat_id, f"✅ Broadcast sent: {sent} success, {failed} failed.")


async def handle_users(bot: Bot, chat_id: int | str, user: dict) -> None:
    """List all registered users (owner/admin only)."""
    if not (user.get("is_admin") or user.get("is_owner")):
        await _send_message(bot, chat_id, "❌ Owner access required.")
        return
    users = _load_users()
    if not users:
        await _send_message(bot, chat_id, "👥 No users registered.")
        return
    total = len(users)
    owners = sum(1 for u in users if u.get("is_owner"))
    admins = sum(1 for u in users if u.get("is_admin") and not u.get("is_owner"))
    free = sum(1 for u in users if not u.get("is_admin") and not u.get("is_owner"))
    lines = [f"👥 <b>Users</b>\nTotal: {total} | Owner: {owners} | Admin: {admins} | Free: {free}\n"]
    for u in users[:10]:
        name = u.get("first_name") or u.get("username") or f"tg:{u.get('telegram_id')}"
        tier = u.get("tier", "free")
        lines.append(f"• {name} — <b>{tier}</b> (tg_id: <code>{u.get('telegram_id')}</code>)")
    if len(users) > 10:
        lines.append(f"... and {len(users) - 10} more.")
    await _send_message(bot, chat_id, "\n".join(lines))


async def handle_stats(bot: Bot, chat_id: int | str, user: dict) -> None:
    """Show bot statistics (owner/admin only)."""
    if not (user.get("is_admin") or user.get("is_owner")):
        await _send_message(bot, chat_id, "❌ Owner access required.")
        return
    users = _load_users()
    keys = _load_json(KEYS_FILE, [])
    total_users = len(users)
    total_keys = len(keys)
    active_keys = sum(1 for k in keys if k.get("active", True))
    total_downloads = sum(u.get("download_count", 0) for u in users)
    total_searches = sum(u.get("search_count", 0) for u in users)
    total_bytes = sum(u.get("monthly_bytes", 0) for u in users)
    gb = total_bytes / (1024 * 1024 * 1024)
    lines = [
        "📊 <b>Bot Statistics</b>\n",
        f"👥 Total users: {total_users}",
        f"🔑 Total API keys: {total_keys} (active: {active_keys})",
        f"⬇️ Total downloads: {total_downloads}",
        f"🔍 Total searches: {total_searches}",
        f"📦 Total bytes downloaded: {gb:.2f} GB",
    ]
    await _send_message(bot, chat_id, "\n".join(lines))


# ---------------------------------------------------------------------------
# Inline query handler (search from anywhere)
# ---------------------------------------------------------------------------

async def handle_inline_query(bot: Bot, inline_query_id: str, query: str, user_id: int) -> None:
    if not query.strip():
        results = [{
            "type": "article",
            "id": "welcome",
            "title": "Videl-Api — Search Media",
            "description": "Type a search query to search music & media",
            "input_message_content": {"message_text": "🔍 Videl-Api Search\nType what you're looking for."},
        }]
    else:
        try:
            results_raw = await dl_search(query, source="youtube", limit=5)
        except Exception:
            results_raw = []
        results = []
        for i, r in enumerate(results_raw):
            results.append({
                "type": "audio",
                "id": f"inline_{i}",
                "audio_url": r.get("url", ""),
                "title": r.get("title", "Unknown"),
                "performer": r.get("uploader", "Unknown"),
                "caption": f"🎵 {r.get('title','Unknown')}\n👤 {r.get('uploader','Unknown')}",
            })
    await _answer_inline_query(bot, inline_query_id, results)


# ---------------------------------------------------------------------------
# Update dispatcher (robust with per-handler error handling)
# ---------------------------------------------------------------------------

async def process_update(update: dict) -> None:
    """Route a Telegram update to the appropriate handler.
    
    All handler exceptions are caught and logged so one bad update
    cannot kill the polling loop.
    """
    bot = await get_bot()
    if not bot:
        return

    try:
        # --- Message ---
        if "message" in update:
            msg = update["message"]
            if not msg:
                logger.warning("Received message update with None message")
                return
            chat = msg.get("chat")
            if not chat:
                logger.warning("Received message without chat field")
                return
            chat_id = chat["id"]
            from_user = msg.get("from", {})
            if not from_user:
                from_user = {}
            tg_id = from_user.get("id")
            if not tg_id:
                logger.warning("Received message without user ID")
                return
            username = from_user.get("username", "")
            first_name = from_user.get("first_name", "")
            text = msg.get("text", "")
            command = text.split(" ")[0] if text else ""
            args = text[len(command):].strip() if text else ""

            # --- Successful payment (must be checked before command routing) ---
            if msg.get("successful_payment"):
                payment = msg["successful_payment"]
                amount = payment.get("total_amount", 0)
                currency = payment.get("currency", "XTR")
                user = _get_or_create_user(tg_id, username, first_name)
                _set_user_field(tg_id, "tier", "pro")
                _set_user_field(tg_id, "stars_balance", user.get("stars_balance", 0) + amount)
                _set_user_field(tg_id, "lifetime_stars", user.get("lifetime_stars", 0) + amount)
                _set_user_field(tg_id, "scopes", ["read", "search", "download"])
                await _send_message(
                    bot,
                    chat_id,
                    "🎉 <b>Payment Successful!</b>\n\n"
                    f"Amount: {amount} {currency}\n"
                    "Tier upgraded to: <b>PRO</b>\n\n"
                    "Your API keys now have Pro limits.\n"
                    "Use /key to view your keys.",
                )
                return

            user = _get_or_create_user(tg_id, username, first_name)

            if command == "/start":
                await _safe("handle_start", handle_start(bot, chat_id, user))
            elif command == "/help":
                await _safe("handle_help", handle_help(bot, chat_id, user))
            elif command == "/tier":
                await _safe("handle_tier", handle_tier(bot, chat_id, user))
            elif command == "/search":
                await _safe("handle_search", handle_search(bot, chat_id, user, args or None))
            elif command == "/download":
                if not args:
                    await _send_message(
                        bot, chat_id,
                        "📥 <b>Download</b>\n\nSend me a URL to download.\nExample: /download https://youtu.be/...",
                        reply_markup=_keyboard([[_cb_button("⬅️ Back", "cb:menu")]]),
                    )
                else:
                    await _safe("handle_download_url", handle_download_url(bot, chat_id, user, args))
            elif command == "/info":
                await _safe("handle_info", handle_info(bot, chat_id, user, args or None))
            elif command == "/lyrics":
                await _safe("handle_lyrics", handle_lyrics(bot, chat_id, user, args or None))
            elif command == "/key":
                await _safe("handle_keys", handle_keys(bot, chat_id, user))
            elif command == "/createkey" or (command == "/key" and args == "create"):
                await _safe("handle_create_key", handle_create_key(bot, chat_id, user))
            elif command == "/buy":
                await _safe("handle_buy", handle_buy(bot, chat_id, user))
            elif command == "/status":
                await _safe("handle_status", handle_status(bot, chat_id))
            elif command == "/sources":
                await _safe("handle_sources", handle_sources(bot, chat_id))
            elif command == "/settings":
                await _safe("handle_settings", handle_settings(bot, chat_id, user))
            elif command == "/playlist":
                await _safe("handle_playlist", handle_playlist(bot, chat_id, user))
            elif command == "/history":
                await _safe("handle_history", handle_history(bot, chat_id, user))
            elif command == "/notify":
                await _safe("handle_notify", handle_notify(bot, chat_id, user))
            elif command == "/feedback":
                await _safe("handle_feedback", handle_feedback(bot, chat_id, user, args or None))
            elif command == "/language":
                await _safe("handle_language", handle_language(bot, chat_id, user, args or None))
            elif command == "/admin":
                await _safe("handle_admin", handle_admin(bot, chat_id, user))
            elif command == "/broadcast":
                await _safe("handle_broadcast", handle_broadcast(bot, chat_id, user, args or None))
            elif command == "/users":
                await _safe("handle_users", handle_users(bot, chat_id, user))
            elif command == "/stats":
                await _safe("handle_stats", handle_stats(bot, chat_id, user))
            else:
                await _safe("handle_start", handle_start(bot, chat_id, user))

        # --- Callback query (inline keyboard) ---
        elif "callback_query" in update:
            cb = update["callback_query"]
            cb_id = cb["id"]
            data = cb.get("data", "")
            cb_message = cb.get("message")
            if not cb_message:
                logger.warning("Received callback_query without message field")
                await _answer_callback_query(bot, cb_id)
                return
            cb_chat = cb_message.get("chat")
            if not cb_chat:
                logger.warning("Received callback_query without chat field")
                await _answer_callback_query(bot, cb_id)
                return
            chat_id = cb_chat["id"]
            message_id = cb_message["message_id"]
            from_user = cb.get("from", {})
            if not from_user:
                from_user = {}
            tg_id = from_user.get("id")
            if not tg_id:
                logger.warning("Received callback_query without user ID")
                await _answer_callback_query(bot, cb_id)
                return
            user = _get_or_create_user(tg_id, from_user.get("username", ""), from_user.get("first_name", ""))

            await _answer_callback_query(bot, cb_id)

            if data == "cb:menu":
                await _safe("handle_start", handle_start(bot, chat_id, user, message_id))
            elif data == "cb:help":
                await _safe("handle_help", handle_help(bot, chat_id, user))
            elif data == "cb:tier":
                await _safe("handle_tier", handle_tier(bot, chat_id, user))
            elif data == "cb:keys":
                await _safe("handle_keys", handle_keys(bot, chat_id, user))
            elif data == "cb:key:create":
                await _safe("handle_create_key", handle_create_key(bot, chat_id, user))
            elif data == "cb:key:list":
                await _safe("handle_keys", handle_keys(bot, chat_id, user))
            elif data == "cb:key:revoke":
                # List keys first so user can see what to revoke
                await _safe("handle_keys", handle_keys(bot, chat_id, user))
                await _send_message(
                    bot, chat_id,
                    "🗑️ <b>Revoke Key</b>\n\nUse the API to revoke a key:\nDELETE /v1/keys/{key_id}\nOr contact support.",
                    reply_markup=keys_keyboard(),
                )
            elif data == "cb:key:rotate":
                await _send_message(
                    bot, chat_id,
                    "🔄 <b>Rotate Key</b>\n\nUse the API to rotate a key:\nPATCH /v1/keys/{key_id}?action=rotate\nOr contact support.",
                    reply_markup=keys_keyboard(),
                )
            elif data == "cb:buy":
                await _safe("handle_buy", handle_buy(bot, chat_id, user))
            elif data == "cb:search":
                await _safe("handle_search", handle_search(bot, chat_id, user, None))
            elif data == "cb:download":
                await _send_message(
                    bot, chat_id,
                    "📥 <b>Download</b>\n\nSend me a URL to download.\nExample: /download https://youtu.be/...",
                    reply_markup=_keyboard([[_cb_button("⬅️ Back", "cb:menu")]]),
                )
            elif data == "cb:info":
                await _send_message(
                    bot, chat_id,
                    "🎵 <b>Info</b>\n\nSend me a URL or search query.\nExample: /info https://youtu.be/...",
                    reply_markup=_keyboard([[_cb_button("⬅️ Back", "cb:menu")]]),
                )
            elif data == "cb:lyrics":
                await _send_message(
                    bot, chat_id,
                    "📝 <b>Lyrics</b>\n\nSend me a song title.\nExample: /lyrics imagine dragons believer",
                    reply_markup=_keyboard([[_cb_button("⬅️ Back", "cb:menu")]]),
                )
            elif data == "cb:status":
                await _safe("handle_status", handle_status(bot, chat_id))
            elif data == "cb:sources":
                await _safe("handle_sources", handle_sources(bot, chat_id))
            elif data == "cb:settings":
                await _safe("handle_settings", handle_settings(bot, chat_id, user))
            elif data == "cb:settings:notify":
                await _safe("handle_notify", handle_notify(bot, chat_id, user))
            elif data == "cb:settings:lang":
                await _safe("handle_language", handle_language(bot, chat_id, user))
            elif data == "cb:playlist":
                await _safe("handle_playlist", handle_playlist(bot, chat_id, user))
            elif data == "cb:history":
                await _safe("handle_history", handle_history(bot, chat_id, user))
            elif data == "cb:admin":
                await _safe("handle_admin", handle_admin(bot, chat_id, user))
            elif data == "cb:admin:users":
                await _send_message(bot, chat_id, "👥 User management via API: GET /v1/users")
            elif data == "cb:admin:stats":
                await _send_message(bot, chat_id, "📊 Stats via API: GET /v1/stats/global")
            elif data == "cb:admin:broadcast":
                await _send_message(bot, chat_id, "📢 Use /broadcast <message>")
            elif data == "cb:admin:keys":
                await _send_message(bot, chat_id, "🔑 All keys via API: GET /v1/web/owner/keys")
            elif data == "cb:admin:system":
                await _send_message(bot, chat_id, "⚙️ System status via API: GET /health")
            elif data.startswith("cb:dl:"):
                url = data[5:]
                await _safe("handle_download_url", handle_download_url(bot, chat_id, user, url))
            elif data.startswith("cb:tier:"):
                tier = data.split(":")[2]
                await _send_message(bot, chat_id, f"Tier {tier} — use /buy to upgrade to Pro.")
            elif data.startswith("cb:lang:"):
                lang = data.split(":")[2]
                await _safe("handle_language", handle_language(bot, chat_id, user, lang))
            else:
                await _safe("handle_start", handle_start(bot, chat_id, user, message_id))

        # --- Inline query ---
        elif "inline_query" in update:
            iq = update["inline_query"]
            await _safe("handle_inline_query", handle_inline_query(bot, iq["id"], iq.get("query", ""), iq.get("from", {}).get("id", 0)))

        # --- Pre-checkout query (Stars payment) ---
        elif "pre_checkout_query" in update:
            pcq = update["pre_checkout_query"]
            await _answer_pre_checkout_query(bot, pcq["id"], ok=True)

        # --- Chat member (bot added to group) ---
        elif "my_chat_member" in update:
            pass

        # --- Channel post ---
        elif "channel_post" in update:
            pass

    except Exception as exc:
        logger.exception(f"process_update top-level error: {exc}")
        await _send_owner_log(
            bot,
            "ERROR",
            "process_update top-level error",
            exc=exc,
        )


# ---------------------------------------------------------------------------
# Webhook setup / teardown
# ---------------------------------------------------------------------------

async def set_webhook(base_url: str) -> None:
    bot = await get_bot()
    if not bot:
        return
    webhook_url = f"{base_url.rstrip('/')}/v1/telegram/webhook"
    await bot.set_webhook(
        url=webhook_url,
        allowed_updates=["message", "callback_query", "inline_query", "pre_checkout_query"],
    )
    logger.info(f"Telegram webhook set: {webhook_url}")


async def delete_webhook() -> None:
    bot = await get_bot()
    if not bot:
        return
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Telegram webhook deleted")


async def set_bot_commands() -> None:
    bot = await get_bot()
    if not bot:
        return
    commands = [
        {"command": "start", "description": "Welcome & main menu"},
        {"command": "help", "description": "Show all commands"},
        {"command": "search", "description": "Search music & media"},
        {"command": "download", "description": "Download a track by URL"},
        {"command": "info", "description": "Get track/album info"},
        {"command": "lyrics", "description": "Get lyrics for a track"},
        {"command": "key", "description": "Manage API keys"},
        {"command": "createkey", "description": "Create a new API key"},
        {"command": "tier", "description": "View subscription tier"},
        {"command": "buy", "description": "Buy Pro with Telegram Stars"},
        {"command": "playlist", "description": "Manage playlists"},
        {"command": "history", "description": "Download history"},
        {"command": "settings", "description": "User settings"},
        {"command": "notify", "description": "Notification preferences"},
        {"command": "sources", "description": "List supported sources"},
        {"command": "status", "description": "System status"},
        {"command": "feedback", "description": "Send feedback"},
        {"command": "language", "description": "Change language"},
        {"command": "admin", "description": "Admin panel (owner)"},
        {"command": "broadcast", "description": "Broadcast (owner)"},
        {"command": "users", "description": "User management (owner)"},
        {"command": "stats", "description": "Bot statistics (owner)"},
    ]
    await bot.set_my_commands(commands)
    logger.info("Bot commands set")


async def start_bot_polling() -> None:
    """Long-polling entry point (for standalone bot mode).

    Uses a cross-process file lock so only ONE process at a time can
    call Telegram's getUpdates.  If another instance already holds the
    lock, this process skips polling entirely rather than conflicting.
    """
    global _polling_active, _poll_lock_file

    if _polling_active:
        logger.warning("Telegram polling already active; not starting duplicate loop")
        return

    # Cross-process file lock: only one process may poll at a time.
    lock_path = os.path.join(os.getenv("TMPDIR", "/tmp"), "videl_telegram_poll.lock")
    try:
        _poll_lock_file = open(lock_path, "w")
        fcntl.flock(_poll_lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (IOError, OSError):
        # Another process already holds the lock — skip polling.
        try:
            _poll_lock_file.close()
        except Exception:
            pass
        _poll_lock_file = None
        logger.info(
            "Telegram polling lock held by another process; "
            "skipping polling in this instance."
        )
        return

    _polling_active = True
    bot = await get_bot()
    if not bot:
        _polling_active = False
        try:
            fcntl.flock(_poll_lock_file.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        _poll_lock_file.close()
        _poll_lock_file = None
        return

    # Small startup delay to let any previous process release Telegram's getUpdates
    await asyncio.sleep(3)

    # Clear any existing webhook so polling can work without conflicts
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Cleared existing webhook before starting polling")
    except Exception as exc:
        logger.warning(f"Could not clear webhook before polling: {exc}")

    offset = 0
    logger.info("Telegram bot polling started")
    conflict_backoff = 30
    try:
        while True:
            try:
                updates = await bot.get_updates(offset=offset, timeout=30, limit=100)
                conflict_backoff = 30  # reset on success
                for upd in updates:
                    offset = upd.update_id + 1
                    await process_update(upd.model_dump())
            except Exception as exc:
                msg = str(exc)
                if "Conflict" in msg or "terminated by other getUpdates" in msg:
                    logger.warning(
                        "Telegram polling conflict: another bot instance is running. "
                        f"Backing off {conflict_backoff}s.",
                    )
                    # Try to clear webhook again in case a stale instance set one
                    try:
                        await bot.delete_webhook(drop_pending_updates=True)
                    except Exception:
                        pass
                    await asyncio.sleep(conflict_backoff)
                    conflict_backoff = min(conflict_backoff * 2, 300)
                else:
                    logger.error(f"Polling error: {exc}")
                    await asyncio.sleep(5)
    finally:
        _polling_active = False
        logger.info("Telegram bot polling stopped")
        # Release the cross-process lock
        try:
            fcntl.flock(_poll_lock_file.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        try:
            _poll_lock_file.close()
        except Exception:
            pass
        _poll_lock_file = None
