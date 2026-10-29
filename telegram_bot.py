"""
Videl-Api Telegram Bot

Full-featured Telegram Bot built on aiogram 3.x Dispatcher:
- Proper handler registration via Dispatcher
- Message handlers with Command filters
- Callback query handlers with F.data filters
- Inline query handlers
- Pre-checkout query handlers
- Successful payment handlers (F.successful_payment)
- Owner / Admin access control
- User management, tiers, subscriptions
- Search, download, lyrics, info from the API
- Broadcast, stats, admin panel
- Settings, language, notifications
- Webhook integration with the FastAPI backend
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    CallbackQuery,
    InlineQuery,
    PreCheckoutQuery,
    Update,
)

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
# Aiogram Dispatcher (original aiogram pattern)
# ---------------------------------------------------------------------------

dp = Dispatcher()

# ---------------------------------------------------------------------------
# Bot instance (lazy init) - aiogram
# ---------------------------------------------------------------------------

_bot: Optional[Bot] = None
_bot_lock = asyncio.Lock()
_bot_initialized = False
_polling_active = False


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
# Handler functions (core logic, called by aiogram adapters)
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
                u["pending_payment_payload"] = payload_str
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
# Aiogram adapter handlers (registered with Dispatcher)
# ---------------------------------------------------------------------------

def _extract_user_from_message(message: Message) -> dict:
    return _get_or_create_user(
        message.from_user.id,
        message.from_user.username or "",
        message.from_user.first_name or "",
    )


def _extract_user_from_callback(callback: CallbackQuery) -> dict:
    return _get_or_create_user(
        callback.from_user.id,
        callback.from_user.username or "",
        callback.from_user.first_name or "",
    )


# --- Command adapters ---

async def cmd_start(message: Message):
    await handle_start(message.bot, message.chat.id, _extract_user_from_message(message))


async def cmd_help(message: Message):
    await handle_help(message.bot, message.chat.id, _extract_user_from_message(message))


async def cmd_tier(message: Message):
    await handle_tier(message.bot, message.chat.id, _extract_user_from_message(message))


async def cmd_search(message: Message):
    args = message.text[len("/search"):].strip() if message.text and message.text.startswith("/search") else ""
    await handle_search(message.bot, message.chat.id, _extract_user_from_message(message), args or None)


async def cmd_download(message: Message):
    args = message.text[len("/download"):].strip() if message.text and message.text.startswith("/download") else ""
    if not args:
        await _send_message(
            message.bot, message.chat.id,
            "📥 <b>Download</b>\n\nSend me a URL to download.\nExample: /download https://youtu.be/...",
            reply_markup=_keyboard([[_cb_button("⬅️ Back", "cb:menu")]]),
        )
    else:
        await handle_download_url(message.bot, message.chat.id, _extract_user_from_message(message), args)


async def cmd_info(message: Message):
    args = message.text[len("/info"):].strip() if message.text and message.text.startswith("/info") else ""
    await handle_info(message.bot, message.chat.id, _extract_user_from_message(message), args or None)


async def cmd_lyrics(message: Message):
    args = message.text[len("/lyrics"):].strip() if message.text and message.text.startswith("/lyrics") else ""
    await handle_lyrics(message.bot, message.chat.id, _extract_user_from_message(message), args or None)


async def cmd_key(message: Message):
    await handle_keys(message.bot, message.chat.id, _extract_user_from_message(message))


async def cmd_createkey(message: Message):
    await handle_create_key(message.bot, message.chat.id, _extract_user_from_message(message))


async def cmd_buy(message: Message):
    await handle_buy(message.bot, message.chat.id, _extract_user_from_message(message))


async def cmd_status(message: Message):
    await handle_status(message.bot, message.chat.id)


async def cmd_sources(message: Message):
    await handle_sources(message.bot, message.chat.id)


async def cmd_settings(message: Message):
    await handle_settings(message.bot, message.chat.id, _extract_user_from_message(message))


async def cmd_playlist(message: Message):
    await handle_playlist(message.bot, message.chat.id, _extract_user_from_message(message))


async def cmd_history(message: Message):
    await handle_history(message.bot, message.chat.id, _extract_user_from_message(message))


async def cmd_notify(message: Message):
    await handle_notify(message.bot, message.chat.id, _extract_user_from_message(message))


async def cmd_feedback(message: Message):
    args = message.text[len("/feedback"):].strip() if message.text and message.text.startswith("/feedback") else ""
    await handle_feedback(message.bot, message.chat.id, _extract_user_from_message(message), args or None)


async def cmd_language(message: Message):
    args = message.text[len("/language"):].strip() if message.text and message.text.startswith("/language") else ""
    await handle_language(message.bot, message.chat.id, _extract_user_from_message(message), args or None)


async def cmd_admin(message: Message):
    await handle_admin(message.bot, message.chat.id, _extract_user_from_message(message))


async def cmd_broadcast(message: Message):
    args = message.text[len("/broadcast"):].strip() if message.text and message.text.startswith("/broadcast") else ""
    await handle_broadcast(message.bot, message.chat.id, _extract_user_from_message(message), args or None)


async def cmd_users(message: Message):
    await handle_users(message.bot, message.chat.id, _extract_user_from_message(message))


async def cmd_stats(message: Message):
    await handle_stats(message.bot, message.chat.id, _extract_user_from_message(message))


# --- Callback query adapters ---

async def cb_menu(callback: CallbackQuery):
    await callback.answer()
    await handle_start(callback.bot, callback.message.chat.id, _extract_user_from_callback(callback), callback.message.message_id)


async def cb_help(callback: CallbackQuery):
    await callback.answer()
    await handle_help(callback.bot, callback.message.chat.id, _extract_user_from_callback(callback))


async def cb_tier(callback: CallbackQuery):
    await callback.answer()
    await handle_tier(callback.bot, callback.message.chat.id, _extract_user_from_callback(callback))


async def cb_keys(callback: CallbackQuery):
    await callback.answer()
    await handle_keys(callback.bot, callback.message.chat.id, _extract_user_from_callback(callback))


async def cb_key_create(callback: CallbackQuery):
    await callback.answer()
    await handle_create_key(callback.bot, callback.message.chat.id, _extract_user_from_callback(callback))


async def cb_key_revoke(callback: CallbackQuery):
    await callback.answer()
    await handle_keys(callback.bot, callback.message.chat.id, _extract_user_from_callback(callback))
    await _send_message(
        callback.bot, callback.message.chat.id,
        "🗑️ <b>Revoke Key</b>\n\nUse the API to revoke a key:\nDELETE /v1/keys/{key_id}\nOr contact support.",
        reply_markup=keys_keyboard(),
    )


async def cb_key_rotate(callback: CallbackQuery):
    await callback.answer()
    await _send_message(
        callback.bot, callback.message.chat.id,
        "🔄 <b>Rotate Key</b>\n\nUse the API to rotate a key:\nPATCH /v1/keys/{key_id}?action=rotate\nOr contact support.",
        reply_markup=keys_keyboard(),
    )


async def cb_buy(callback: CallbackQuery):
    await callback.answer()
    await handle_buy(callback.bot, callback.message.chat.id, _extract_user_from_callback(callback))


async def cb_search(callback: CallbackQuery):
    await callback.answer()
    await handle_search(callback.bot, callback.message.chat.id, _extract_user_from_callback(callback), None)


async def cb_download(callback: CallbackQuery):
    await callback.answer()
    await _send_message(
        callback.bot, callback.message.chat.id,
        "📥 <b>Download</b>\n\nSend me a URL to download.\nExample: /download https://youtu.be/...",
        reply_markup=_keyboard([[_cb_button("⬅️ Back", "cb:menu")]]),
    )


async def cb_info(callback: CallbackQuery):
    await callback.answer()
    await _send_message(
        callback.bot, callback.message.chat.id,
        "🎵 <b>Info</b>\n\nSend me a URL or search query.\nExample: /info https://youtu.be/...",
        reply_markup=_keyboard([[_cb_button("⬅️ Back", "cb:menu")]]),
    )


async def cb_lyrics(callback: CallbackQuery):
    await callback.answer()
    await _send_message(
        callback.bot, callback.message.chat.id,
        "📝 <b>Lyrics</b>\n\nSend me a song title.\nExample: /lyrics imagine dragons believer",
        reply_markup=_keyboard([[_cb_button("⬅️ Back", "cb:menu")]]),
    )


async def cb_status(callback: CallbackQuery):
    await callback.answer()
    await handle_status(callback.bot, callback.message.chat.id)


async def cb_sources(callback: CallbackQuery):
    await callback.answer()
    await handle_sources(callback.bot, callback.message.chat.id)


async def cb_settings(callback: CallbackQuery):
    await callback.answer()
    await handle_settings(callback.bot, callback.message.chat.id, _extract_user_from_callback(callback))


async def cb_settings_notify(callback: CallbackQuery):
    await callback.answer()
    await handle_notify(callback.bot, callback.message.chat.id, _extract_user_from_callback(callback))


async def cb_settings_lang(callback: CallbackQuery):
    await callback.answer()
    await handle_language(callback.bot, callback.message.chat.id, _extract_user_from_callback(callback))


async def cb_playlist(callback: CallbackQuery):
    await callback.answer()
    await handle_playlist(callback.bot, callback.message.chat.id, _extract_user_from_callback(callback))


async def cb_history(callback: CallbackQuery):
    await callback.answer()
    await handle_history(callback.bot, callback.message.chat.id, _extract_user_from_callback(callback))


async def cb_admin(callback: CallbackQuery):
    await callback.answer()
    await handle_admin(callback.bot, callback.message.chat.id, _extract_user_from_callback(callback))


async def cb_admin_users(callback: CallbackQuery):
    await callback.answer()
    await _send_message(callback.bot, callback.message.chat.id, "👥 User management via API: GET /v1/users")


async def cb_admin_stats(callback: CallbackQuery):
    await callback.answer()
    await _send_message(callback.bot, callback.message.chat.id, "📊 Stats via API: GET /v1/stats/global")


async def cb_admin_broadcast(callback: CallbackQuery):
    await callback.answer()
    await _send_message(callback.bot, callback.message.chat.id, "📢 Use /broadcast <message>")


async def cb_admin_keys(callback: CallbackQuery):
    await callback.answer()
    await _send_message(callback.bot, callback.message.chat.id, "🔑 All keys via API: GET /v1/web/owner/keys")


async def cb_admin_system(callback: CallbackQuery):
    await callback.answer()
    await _send_message(callback.bot, callback.message.chat.id, "⚙️ System status via API: GET /health")


async def cb_download_url(callback: CallbackQuery):
    await callback.answer()
    url = callback.data[5:]  # strip "cb:dl:"
    await handle_download_url(callback.bot, callback.message.chat.id, _extract_user_from_callback(callback), url)


async def cb_tier_select(callback: CallbackQuery):
    await callback.answer()
    tier = callback.data.split(":")[2]
    await _send_message(callback.bot, callback.message.chat.id, f"Tier {tier} — use /buy to upgrade to Pro.")


async def cb_lang_select(callback: CallbackQuery):
    await callback.answer()
    lang = callback.data.split(":")[2]
    await handle_language(callback.bot, callback.message.chat.id, _extract_user_from_callback(callback), lang)


# --- Successful payment handler ---

async def successful_payment_handler(message: Message):
    payment = message.successful_payment
    amount = payment.total_amount
    currency = payment.currency
    user = _get_or_create_user(message.from_user.id, message.from_user.username or "", message.from_user.first_name or "")
    _set_user_field(message.from_user.id, "tier", "pro")
    _set_user_field(message.from_user.id, "stars_balance", user.get("stars_balance", 0) + amount)
    _set_user_field(message.from_user.id, "lifetime_stars", user.get("lifetime_stars", 0) + amount)
    _set_user_field(message.from_user.id, "scopes", ["read", "search", "download"])
    await _send_message(
        message.bot,
        message.chat.id,
        "🎉 <b>Payment Successful!</b>\n\n"
        f"Amount: {amount} {currency}\n"
        "Tier upgraded to: <b>PRO</b>\n\n"
        "Your API keys now have Pro limits.\n"
        "Use /key to view your keys.",
    )


# ---------------------------------------------------------------------------
# Register all handlers with Dispatcher
# ---------------------------------------------------------------------------

def _register_handlers() -> None:
    # Commands
    dp.message.register(cmd_start, Command("start"))
    dp.message.register(cmd_help, Command("help"))
    dp.message.register(cmd_tier, Command("tier"))
    dp.message.register(cmd_search, Command("search"))
    dp.message.register(cmd_download, Command("download"))
    dp.message.register(cmd_info, Command("info"))
    dp.message.register(cmd_lyrics, Command("lyrics"))
    dp.message.register(cmd_key, Command("key"))
    dp.message.register(cmd_createkey, Command("createkey"))
    dp.message.register(cmd_buy, Command("buy"))
    dp.message.register(cmd_status, Command("status"))
    dp.message.register(cmd_sources, Command("sources"))
    dp.message.register(cmd_settings, Command("settings"))
    dp.message.register(cmd_playlist, Command("playlist"))
    dp.message.register(cmd_history, Command("history"))
    dp.message.register(cmd_notify, Command("notify"))
    dp.message.register(cmd_feedback, Command("feedback"))
    dp.message.register(cmd_language, Command("language"))
    dp.message.register(cmd_admin, Command("admin"))
    dp.message.register(cmd_broadcast, Command("broadcast"))
    dp.message.register(cmd_users, Command("users"))
    dp.message.register(cmd_stats, Command("stats"))

    # Successful payment (must be registered to catch payment messages)
    dp.message.register(successful_payment_handler, F.successful_payment)

    # Callback queries
    dp.callback_query.register(cb_menu, F.data == "cb:menu")
    dp.callback_query.register(cb_help, F.data == "cb:help")
    dp.callback_query.register(cb_tier, F.data == "cb:tier")
    dp.callback_query.register(cb_keys, F.data == "cb:keys")
    dp.callback_query.register(cb_key_create, F.data == "cb:key:create")
    dp.callback_query.register(cb_key_revoke, F.data == "cb:key:revoke")
    dp.callback_query.register(cb_key_rotate, F.data == "cb:key:rotate")
    dp.callback_query.register(cb_buy, F.data == "cb:buy")
    dp.callback_query.register(cb_search, F.data == "cb:search")
    dp.callback_query.register(cb_download, F.data == "cb:download")
    dp.callback_query.register(cb_info, F.data == "cb:info")
    dp.callback_query.register(cb_lyrics, F.data == "cb:lyrics")
    dp.callback_query.register(cb_status, F.data == "cb:status")
    dp.callback_query.register(cb_sources, F.data == "cb:sources")
    dp.callback_query.register(cb_settings, F.data == "cb:settings")
    dp.callback_query.register(cb_settings_notify, F.data == "cb:settings:notify")
    dp.callback_query.register(cb_settings_lang, F.data == "cb:settings:lang")
    dp.callback_query.register(cb_playlist, F.data == "cb:playlist")
    dp.callback_query.register(cb_history, F.data == "cb:history")
    dp.callback_query.register(cb_admin, F.data == "cb:admin")
    dp.callback_query.register(cb_admin_users, F.data == "cb:admin:users")
    dp.callback_query.register(cb_admin_stats, F.data == "cb:admin:stats")
    dp.callback_query.register(cb_admin_broadcast, F.data == "cb:admin:broadcast")
    dp.callback_query.register(cb_admin_keys, F.data == "cb:admin:keys")
    dp.callback_query.register(cb_admin_system, F.data == "cb:admin:system")
    dp.callback_query.register(cb_download_url, F.data.startswith("cb:dl:"))
    dp.callback_query.register(cb_tier_select, F.data.startswith("cb:tier:"))
    dp.callback_query.register(cb_lang_select, F.data.startswith("cb:lang:"))

    # Inline query
    dp.inline_query.register(handle_inline_query)

    # Pre-checkout query
    dp.pre_checkout_query.register(lambda bot, pre_checkout_query: _answer_pre_checkout_query(bot, pre_checkout_query.id, ok=True))

    logger.info("All Telegram bot handlers registered with Dispatcher")


# Register on import
_register_handlers()


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


# ---------------------------------------------------------------------------
# Process single update (for webhook mode)
# ---------------------------------------------------------------------------

async def process_update(update: dict) -> None:
    """Route a single Telegram update via Dispatcher (webhook mode)."""
    bot = await get_bot()
    if not bot:
        return
    try:
        await dp.feed_update(bot, Update.model_validate(update))
    except Exception as exc:
        logger.exception(f"process_update error: {exc}")
        await _send_owner_log(
            bot,
            "ERROR",
            "process_update error",
            exc=exc,
        )


# ---------------------------------------------------------------------------
# Long-polling entry point (standalone bot mode)
# ---------------------------------------------------------------------------

async def start_bot_polling() -> None:
    """Long-polling entry point using aiogram Dispatcher.

    Telegram only allows ONE getUpdates connection per bot token.
    If another instance is already polling, aiogram's start_polling
    will retry internally.  We add a startup delay and webhook
    clearance to minimize conflicts on restart.
    """
    global _polling_active

    if _polling_active:
        logger.warning("Telegram polling already active; not starting duplicate loop")
        return

    _polling_active = True
    bot = await get_bot()
    if not bot:
        _polling_active = False
        return

    # Startup delay to let any previous process fully release Telegram's getUpdates
    await asyncio.sleep(5)

    # Clear any existing webhook so polling can work without conflicts
    for attempt in range(5):
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            logger.info("Cleared existing webhook before starting polling")
            break
        except Exception as exc:
            logger.warning(
                f"Could not clear webhook before polling (attempt {attempt + 1}/5): {exc}"
            )
            await asyncio.sleep(2)

    logger.info("Telegram bot polling started")
    try:
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
            drop_pending_updates=True,
            polling_timeout=30,
        )
    except asyncio.CancelledError:
        logger.info("Telegram bot polling cancelled (shutdown)")
        raise
    finally:
        _polling_active = False
        logger.info("Telegram bot polling stopped")
