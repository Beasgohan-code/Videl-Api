"""
Videl-Api Telegram Bot
aiogram 3.x Dispatcher with Router pattern.
Multi-source media download bot: YouTube, SoundCloud, Spotify, Apple Music, Deezer, Bandcamp.
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
from typing import Any, Optional

from aiogram import Bot, Dispatcher, F, Router
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
# Aiogram Dispatcher + Router (aiogram 3.x pattern)
# ---------------------------------------------------------------------------

dp = Dispatcher()
router = Router()


# ---------------------------------------------------------------------------
# Bot instance (lazy init)
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
# Storage helpers (JSON fallback)
# ---------------------------------------------------------------------------

def _load_json(path: str, default: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _save_json(path: str, data: Any) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
    except OSError as exc:
        logger.error("Failed to save %s: %s", path, exc)


def _load_users() -> list[dict]:
    return _load_json(USERS_FILE, [])


def _save_users(users: list[dict]) -> None:
    _save_json(USERS_FILE, users)


def _get_or_create_user(telegram_id: int, username: str = "", first_name: str = "") -> dict:
    users = _load_users()
    for u in users:
        if u.get("telegram_id") == telegram_id:
            return u
    user = {
        "telegram_id": telegram_id,
        "username": username,
        "first_name": first_name,
        "tier": "free",
        "keys": [],
        "download_count": 0,
        "monthly_bytes": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    users.append(user)
    _save_users(users)
    return user


def _set_user_field(telegram_id: int, field: str, value: Any) -> None:
    users = _load_users()
    for u in users:
        if u.get("telegram_id") == telegram_id:
            u[field] = value
            break
    _save_users(users)


def _increment_counter(telegram_id: int, field: str, amount: int = 1) -> None:
    users = _load_users()
    for u in users:
        if u.get("telegram_id") == telegram_id:
            u[field] = u.get(field, 0) + amount
            break
    _save_users(users)


def _is_owner(telegram_id: int) -> bool:
    return telegram_id == settings.telegram_bot_owner_id


def _is_admin(telegram_id: int) -> bool:
    return _is_owner(telegram_id)


# ---------------------------------------------------------------------------
# URL detection
# ---------------------------------------------------------------------------

import re

URL_PATTERN = re.compile(
    r"https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/playlist\?list=|"
    r"soundcloud\.com/|open\.spotify\.com/|music\.apple\.com/|deezer\.com/|bandcamp\.com/)"
    r"[a-zA-Z0-9\-_?=&/%#.]+"
)

SUPPORTED_DOMAINS = {
    "youtube.com": "YouTube",
    "youtu.be": "YouTube",
    "soundcloud.com": "SoundCloud",
    "open.spotify.com": "Spotify",
    "music.apple.com": "Apple Music",
    "deezer.com": "Deezer",
    "bandcamp.com": "Bandcamp",
}


def detect_urls(text: str) -> list[str]:
    return URL_PATTERN.findall(text or "")


def detect_source_from_url(url: str) -> str:
    for domain, name in SUPPORTED_DOMAINS.items():
        if domain in url:
            return name
    return "Unknown"


def is_playlist_url(url: str) -> bool:
    return "playlist" in url or "list=" in url


# ---------------------------------------------------------------------------
# UI helpers (Richgram-style, no credits)
# ---------------------------------------------------------------------------

def _cb_button(text: str, callback_data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback_data)


def _url_button(text: str, url: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, url=url)


def _keyboard(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


def rich_esc(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def rich_heading(text: str, level: int = 1) -> str:
    return f"<b>{rich_esc(text)}</b>\n"


def rich_divider(char: str = "─", length: int = 24) -> str:
    return f"<code>{char * length}</code>\n"


def rich_kv_table(rows: list[tuple[str, str]]) -> str:
    lines = []
    for k, v in rows:
        lines.append(f"<b>{rich_esc(k)}:</b> <code>{rich_esc(str(v))}</code>")
    return "\n".join(lines) + "\n"


def rich_button(text: str, callback_data: str | None = None, url: str | None = None, style: str = "primary") -> InlineKeyboardButton:
    if url:
        return InlineKeyboardButton(text=text, url=url)
    return InlineKeyboardButton(text=text, callback_data=callback_data or "cb:noop")


def rich_section(title: str, body: str, icon: str = "🔸") -> str:
    return f"{icon} <b>{rich_esc(title)}</b>\n{rich_esc(body)}\n"


def main_menu_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [_cb_button("🔍 Search", "cb:search"), _cb_button("📥 Download", "cb:download")],
        [_cb_button("🎵 Info", "cb:info"), _cb_button("📝 Lyrics", "cb:lyrics")],
        [_cb_button("🔑 API Keys", "cb:keys"), _cb_button("📊 Tier", "cb:tier")],
        [_cb_button("💳 Upgrade", "cb:buy"), _cb_button("📋 Playlist", "cb:playlist")],
        [_cb_button("📊 Stats", "cb:stats"), _cb_button("⚙️ Settings", "cb:settings")],
        [_cb_button("📡 Sources", "cb:sources"), _cb_button("📢 Status", "cb:status")],
    ]
    if is_admin:
        rows.append([_cb_button("👑 Admin Panel", "cb:admin")])
    rows.append([_cb_button("❓ Help", "cb:help")])
    return _keyboard(rows)


def tier_keyboard() -> InlineKeyboardMarkup:
    return _keyboard([
        [_cb_button("Free Tier", "cb:tier:free"), _cb_button("Pro Tier", "cb:tier:pro")],
        [_cb_button("Owner Tier", "cb:tier:owner")],
        [_cb_button("⬅️ Back", "cb:menu")],
    ])


def keys_keyboard() -> InlineKeyboardMarkup:
    return _keyboard([
        [_cb_button("Create Key", "cb:key:create"), _cb_button("List Keys", "cb:key:list")],
        [_cb_button("Rotate Key", "cb:key:rotate"), _cb_button("Revoke Key", "cb:key:revoke")],
        [_cb_button("⬅️ Back", "cb:menu")],
    ])


def admin_keyboard() -> InlineKeyboardMarkup:
    return _keyboard([
        [_cb_button("Users", "cb:admin:users"), _cb_button("Stats", "cb:admin:stats")],
        [_cb_button("Broadcast", "cb:admin:broadcast"), _cb_button("All Keys", "cb:admin:keys")],
        [_cb_button("System", "cb:admin:system"), _cb_button("⬅️ Back", "cb:menu")],
    ])


def settings_keyboard() -> InlineKeyboardMarkup:
    return _keyboard([
        [_cb_button("Language", "cb:settings:lang"), _cb_button("Notifications", "cb:settings:notify")],
        [_cb_button("⬅️ Back", "cb:menu")],
    ])


def build_welcome_message(first_name: str, is_admin: bool = False, is_owner: bool = False) -> str:
    role = "Owner" if is_owner else ("Admin" if is_admin else "Free")
    lines = [
        f"<b>Welcome, {rich_esc(first_name)}!</b>",
        rich_divider(),
        f"Role: {role}",
        "Multi-source media download bot.",
        "Use the buttons below or send commands:",
        "/search <query> — search media",
        "/download <url> — download media",
        "/info <url> — track info",
        "/batch <url1> <url2> — batch download",
        "/recent — recent downloads",
        "/platforms — supported platforms",
    ]
    return "\n".join(lines)


def build_help_message(is_admin: bool = False, is_owner: bool = False) -> str:
    lines = [
        "<b>Videl-Api Bot Commands</b>",
        rich_divider(),
        "/start — Welcome & main menu",
        "/help — Show this help",
        "/search <query> — Search media across sources",
        "/download <url> — Download media file",
        "/info <url> — Get track/album info",
        "/lyrics <query> — Search lyrics",
        "/key — Manage your API keys",
        "/createkey — Create a new API key",
        "/buy — Upgrade your tier",
        "/status — Bot status",
        "/sources — Supported platforms",
        "/settings — Bot settings",
        "/playlist — Playlist download",
        "/history — Download history",
        "/notify — Notification settings",
        "/feedback — Send feedback",
        "/language — Change language",
        "/users — List users (owner)",
        "/stats — Bot statistics (owner)",
        "/batch <urls...> — Batch download",
        "/recent — Recent downloads",
        "/platforms — Supported platforms",
    ]
    if is_admin or is_owner:
        lines.extend([
            "",
            "<b>Owner Commands</b>",
            rich_divider(),
            "/admin — Admin panel",
            "/broadcast <text> — Broadcast to all users",
            "/users — List all users",
            "/stats — Bot statistics",
        ])
    return "\n".join(lines)


def build_tier_message(tier: str, is_admin: bool = False) -> str:
    return (
        f"<b>Your Tier: {tier.upper()}</b>\n"
        + rich_divider()
        + "Features:\n"
        + "• Multi-source search & download\n"
        + "• API key management\n"
        + "• Download history\n"
    )


# ---------------------------------------------------------------------------
# Message helpers
# ---------------------------------------------------------------------------

async def _send_message(bot: Bot, chat_id: int | str, text: str, reply_markup=None, parse_mode=ParseMode.HTML) -> None:
    try:
        await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception as exc:
        logger.error("send_message failed: %s", exc)


async def _edit_message(bot: Bot, chat_id: int | str, message_id: int, text: str, reply_markup=None) -> None:
    try:
        await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    except Exception as exc:
        logger.error("edit_message_text failed: %s", exc)


async def _send_invoice(bot: Bot, chat_id: int | str, **kwargs) -> None:
    try:
        await bot.send_invoice(chat_id=chat_id, **kwargs)
    except Exception as exc:
        logger.error("send_invoice failed: %s", exc)


async def _send_owner_message(bot: Bot, text: str) -> None:
    owner_id = settings.telegram_bot_owner_id
    if owner_id:
        await _send_message(bot, owner_id, text)


async def _send_owner_log(bot: Bot, text: str) -> None:
    await _send_owner_message(bot, f"<b>Bot Log:</b>\n{rich_esc(text)}")


async def _answer_callback_query(bot: Bot, callback_query_id: str, text: Optional[str] = None, show_alert: bool = False) -> None:
    try:
        await bot.answer_callback_query(callback_query_id=callback_query_id, text=text or "", show_alert=show_alert)
    except Exception as exc:
        logger.error("answer_callback_query failed: %s", exc)


async def _answer_inline_query(bot: Bot, inline_query_id: str, results: list, cache_time: int = 300) -> None:
    try:
        await bot.answer_inline_query(inline_query_id=inline_query_id, results=results, cache_time=cache_time)
    except Exception as exc:
        logger.error("answer_inline_query failed: %s", exc)


async def _answer_pre_checkout_query(bot: Bot, pre_checkout_query_id: str, ok: bool = True, error_message: Optional[str] = None) -> None:
    try:
        await bot.answer_pre_checkout_query(pre_checkout_query_id=pre_checkout_query_id, ok=ok, error_message=error_message)
    except Exception as exc:
        logger.error("answer_pre_checkout_query failed: %s", exc)


async def _safe(handler_name: str, coro) -> None:
    try:
        await coro
    except Exception as exc:
        logger.error("Handler %s failed: %s\n%s", handler_name, exc, traceback.format_exc())


# ---------------------------------------------------------------------------
# User extraction
# ---------------------------------------------------------------------------

def _extract_user_from_message(message: Message) -> dict:
    chat = message.chat
    from_user = message.from_user
    tg_id = from_user.id if from_user else 0
    username = from_user.username if from_user else ""
    first_name = from_user.first_name if from_user else ""
    chat_id = chat.id if chat else 0
    return {
        "telegram_id": tg_id,
        "username": username,
        "first_name": first_name,
        "chat_id": chat_id,
    }


def _extract_user_from_callback(callback: CallbackQuery) -> dict:
    from_user = callback.from_user
    chat = callback.message.chat if callback.message else None
    tg_id = from_user.id if from_user else 0
    username = from_user.username if from_user else ""
    first_name = from_user.first_name if from_user else ""
    chat_id = chat.id if chat else 0
    return {
        "telegram_id": tg_id,
        "username": username,
        "first_name": first_name,
        "chat_id": chat_id,
    }


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    user = _extract_user_from_message(message)
    _get_or_create_user(user["telegram_id"], user["username"], user["first_name"])
    is_admin = _is_admin(user["telegram_id"])
    is_owner = _is_owner(user["telegram_id"])
    bot = await get_bot()
    if not bot:
        return
    await _send_message(
        bot,
        user["chat_id"],
        build_welcome_message(user["first_name"], is_admin, is_owner),
        reply_markup=main_menu_keyboard(is_admin),
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    user = _extract_user_from_message(message)
    is_admin = _is_admin(user["telegram_id"])
    is_owner = _is_owner(user["telegram_id"])
    bot = await get_bot()
    if not bot:
        return
    await _send_message(
        bot,
        user["chat_id"],
        build_help_message(is_admin, is_owner),
        reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
    )


@router.message(Command("tier"))
async def cmd_tier(message: Message) -> None:
    user = _extract_user_from_message(message)
    u = _get_or_create_user(user["telegram_id"], user["username"], user["first_name"])
    bot = await get_bot()
    if not bot:
        return
    await _send_message(
        bot,
        user["chat_id"],
        build_tier_message(u.get("tier", "free"), _is_admin(user["telegram_id"])),
        reply_markup=tier_keyboard(),
    )


@router.message(Command("search"))
async def cmd_search(message: Message) -> None:
    user = _extract_user_from_message(message)
    text = message.text or ""
    parts = text.split(None, 1)
    query = parts[1] if len(parts) > 1 else ""
    if not query:
        bot = await get_bot()
        if bot:
            await _send_message(
                bot,
                user["chat_id"],
                "Usage: /search <query>\nExample: /search never gonna give you up",
                reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
            )
        return
    await _do_search(user, query, message.message_id, message.chat.id, message.bot)


@router.message(Command("download"))
async def cmd_download(message: Message) -> None:
    user = _extract_user_from_message(message)
    text = message.text or ""
    parts = text.split(None, 1)
    url = parts[1] if len(parts) > 1 else ""
    if not url:
        bot = await get_bot()
        if bot:
            await _send_message(
                bot,
                user["chat_id"],
                "Usage: /download <url>\nExample: /download https://youtu.be/xxx",
                reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
            )
        return
    await _do_download(user, url, message.chat.id, message.bot)


@router.message(Command("info"))
async def cmd_info(message: Message) -> None:
    user = _extract_user_from_message(message)
    text = message.text or ""
    parts = text.split(None, 1)
    query = parts[1] if len(parts) > 1 else ""
    if not query:
        bot = await get_bot()
        if bot:
            await _send_message(
                bot,
                user["chat_id"],
                "Usage: /info <url>\nExample: /info https://youtu.be/xxx",
                reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
            )
        return
    await _do_info(user, query, message.chat.id, message.bot)


@router.message(Command("lyrics"))
async def cmd_lyrics(message: Message) -> None:
    user = _extract_user_from_message(message)
    text = message.text or ""
    parts = text.split(None, 1)
    query = parts[1] if len(parts) > 1 else ""
    if not query:
        bot = await get_bot()
        if bot:
            await _send_message(
                bot,
                user["chat_id"],
                "Usage: /lyrics <query>\nExample: /lyrics never gonna give you up",
                reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
            )
        return
    await _do_lyrics(user, query, message.chat.id, message.bot)


@router.message(Command("key"))
async def cmd_key(message: Message) -> None:
    user = _extract_user_from_message(message)
    u = _get_or_create_user(user["telegram_id"], user["username"], user["first_name"])
    keys = u.get("keys", [])
    lines = [f"<b>Your API Keys ({len(keys)})</b>", rich_divider()]
    if not keys:
        lines.append("No keys yet. Create one with /createkey or the button below.")
    else:
        for k in keys[:5]:
            lines.append(f"• <code>{rich_esc(str(k.get('key', ''))[:12])}...</code> — {k.get('tier', 'free')}")
    lines.append("")
    lines.append("Use /createkey to generate a new key.")
    bot = await get_bot()
    if not bot:
        return
    await _send_message(
        bot,
        user["chat_id"],
        "\n".join(lines),
        reply_markup=keys_keyboard(),
    )


@router.message(Command("createkey"))
async def cmd_createkey(message: Message) -> None:
    user = _extract_user_from_message(message)
    u = _get_or_create_user(user["telegram_id"], user["username"], user["first_name"])
    try:
        key = auth_create_key(user["telegram_id"], tier=u.get("tier", "free"))
        _increment_counter(user["telegram_id"], "key_count", 1)
    except Exception as exc:
        logger.error("create_api_key failed: %s", exc)
        key = None
    bot = await get_bot()
    if not bot:
        return
    if key:
        await _send_message(
            bot,
            user["chat_id"],
            f"<b>API Key Created</b>\n{rich_divider()}\n<code>{rich_esc(str(key))}</code>\n\nSave it securely — it won't be shown again.",
            reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
        )
    else:
        await _send_message(
            bot,
            user["chat_id"],
            "Failed to create API key. Please try again later.",
            reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
        )


@router.message(Command("buy"))
async def cmd_buy(message: Message) -> None:
    user = _extract_user_from_message(message)
    bot = await get_bot()
    if not bot:
        return
    await _send_message(
        bot,
        user["chat_id"],
        "<b>Upgrade Tier</b>" + rich_divider() + "Contact the owner to upgrade your tier.",
        reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
    )


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    user = _extract_user_from_message(message)
    bot = await get_bot()
    if not bot:
        return
    await _send_message(
        bot,
        user["chat_id"],
        "<b>Bot Status</b>" + rich_divider() + "✅ Online\nSources: YouTube, SoundCloud, Spotify, Apple Music, Deezer, Bandcamp",
        reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
    )


@router.message(Command("sources"))
async def cmd_sources(message: Message) -> None:
    user = _extract_user_from_message(message)
    sources = list_all_sources()
    lines = ["<b>Supported Platforms</b>", rich_divider()]
    for s in sources:
        lines.append(f"• {s}")
    lines.append("")
    lines.append("Send any URL from these platforms to download.")
    bot = await get_bot()
    if not bot:
        return
    await _send_message(
        bot,
        user["chat_id"],
        "\n".join(lines),
        reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
    )


@router.message(Command("settings"))
async def cmd_settings(message: Message) -> None:
    user = _extract_user_from_message(message)
    bot = await get_bot()
    if not bot:
        return
    await _send_message(
        bot,
        user["chat_id"],
        "<b>Settings</b>" + rich_divider() + "Choose an option:",
        reply_markup=settings_keyboard(),
    )


@router.message(Command("playlist"))
async def cmd_playlist(message: Message) -> None:
    user = _extract_user_from_message(message)
    bot = await get_bot()
    if not bot:
        return
    await _send_message(
        bot,
        user["chat_id"],
        "<b>Playlist Download</b>" + rich_divider() + "Send a playlist URL to download all tracks.",
        reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
    )


@router.message(Command("history"))
async def cmd_history(message: Message) -> None:
    user = _extract_user_from_message(message)
    bot = await get_bot()
    if not bot:
        return
    jobs = dl_list_jobs(user["telegram_id"])
    lines = ["<b>Recent Downloads</b>", rich_divider()]
    if not jobs:
        lines.append("No downloads yet.")
    else:
        for j in jobs[:10]:
            lines.append(f"• {rich_esc(str(j.get('url', ''))[:60])} — {j.get('status', 'unknown')}")
    lines.append("")
    lines.append("Use /download <url> to start a new download.")
    await _send_message(
        bot,
        user["chat_id"],
        "\n".join(lines),
        reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
    )


@router.message(Command("notify"))
async def cmd_notify(message: Message) -> None:
    user = _extract_user_from_message(message)
    bot = await get_bot()
    if not bot:
        return
    await _send_message(
        bot,
        user["chat_id"],
        "<b>Notifications</b>" + rich_divider() + "Notification settings coming soon.",
        reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
    )


@router.message(Command("feedback"))
async def cmd_feedback(message: Message) -> None:
    user = _extract_user_from_message(message)
    text = message.text or ""
    parts = text.split(None, 1)
    feedback_text = parts[1] if len(parts) > 1 else ""
    bot = await get_bot()
    if not bot:
        return
    if feedback_text:
        await _send_owner_message(bot, f"<b>Feedback from {user['first_name']} ({user['telegram_id']}):</b>\n{rich_esc(feedback_text)}")
        await _send_message(
            bot,
            user["chat_id"],
            "Thank you for your feedback!",
            reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
        )
    else:
        await _send_message(
            bot,
            user["chat_id"],
            "Usage: /feedback <your message>",
            reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
        )


@router.message(Command("language"))
async def cmd_language(message: Message) -> None:
    user = _extract_user_from_message(message)
    bot = await get_bot()
    if not bot:
        return
    await _send_message(
        bot,
        user["chat_id"],
        "<b>Language</b>" + rich_divider() + "Select your language:",
        reply_markup=_keyboard([
            [_cb_button("English", "cb:lang:en"), _cb_button("Español", "cb:lang:es")],
            [_cb_button("Français", "cb:lang:fr"), _cb_button("中文", "cb:lang:zh")],
            [_cb_button("⬅️ Back", "cb:settings")],
        ]),
    )


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    user = _extract_user_from_message(message)
    if not _is_admin(user["telegram_id"]):
        bot = await get_bot()
        if bot:
            await _send_message(
                bot,
                user["chat_id"],
                "⛔ Owner-only command.",
                reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
            )
        return
    bot = await get_bot()
    if not bot:
        return
    await _send_message(
        bot,
        user["chat_id"],
        "<b>Admin Panel</b>" + rich_divider() + "Owner-only management:",
        reply_markup=admin_keyboard(),
    )


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message) -> None:
    user = _extract_user_from_message(message)
    if not _is_admin(user["telegram_id"]):
        return
    text = message.text or ""
    parts = text.split(None, 1)
    broadcast_text = parts[1] if len(parts) > 1 else ""
    bot = await get_bot()
    if not bot:
        return
    if not broadcast_text:
        await _send_message(
            bot,
            user["chat_id"],
            "Usage: /broadcast <message>",
            reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
        )
        return
    users = _load_users()
    count = 0
    for u in users:
        try:
            await bot.send_message(chat_id=u["telegram_id"], text=f"<b>Broadcast:</b>\n{rich_esc(broadcast_text)}", parse_mode=ParseMode.HTML)
            count += 1
        except Exception:
            pass
    await _send_message(
        bot,
        user["chat_id"],
        f"Broadcast sent to {count} users.",
        reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
    )


@router.message(Command("users"))
async def cmd_users(message: Message) -> None:
    user = _extract_user_from_message(message)
    if not _is_admin(user["telegram_id"]):
        bot = await get_bot()
        if bot:
            await _send_message(
                bot,
                user["chat_id"],
                "⛔ Owner-only command.",
                reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
            )
        return
    users = _load_users()
    lines = ["<b>All Users</b>", rich_divider(), f"Total: {len(users)}", ""]
    for u in users[:50]:
        lines.append(f"• {u.get('first_name', 'User')} ({u.get('telegram_id')}) — {u.get('tier', 'free')}")
    bot = await get_bot()
    if not bot:
        return
    await _send_message(
        bot,
        user["chat_id"],
        "\n".join(lines),
        reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
    )


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    user = _extract_user_from_message(message)
    if not _is_admin(user["telegram_id"]):
        bot = await get_bot()
        if bot:
            await _send_message(
                bot,
                user["chat_id"],
                "⛔ Owner-only command.",
                reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
            )
        return
    users = _load_users()
    total_downloads = sum(u.get("download_count", 0) for u in users)
    total_keys = sum(len(u.get("keys", [])) for u in users)
    total_bytes = sum(u.get("monthly_bytes", 0) for u in users)
    gb = total_bytes / (1024 ** 3)
    lines = [
        "<b>Bot Statistics</b>",
        rich_divider(),
        f"Total Users: {len(users)}",
        f"Total Downloads: {total_downloads}",
        f"Total API Keys: {total_keys}",
        f"Total Data: {gb:.2f} GB",
    ]
    bot = await get_bot()
    if not bot:
        return
    await _send_message(
        bot,
        user["chat_id"],
        "\n".join(lines),
        reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
    )


# ---------------------------------------------------------------------------
# Feature commands: /batch, /recent, /platforms, auto URL detection
# ---------------------------------------------------------------------------

@router.message(Command("batch"))
async def cmd_batch(message: Message) -> None:
    user = _extract_user_from_message(message)
    text = message.text or ""
    parts = text.split(None, 1)
    urls_text = parts[1] if len(parts) > 1 else ""
    urls = [u.strip() for u in urls_text.replace("\n", " ").split() if u.strip()]
    if not urls:
        bot = await get_bot()
        if not bot:
            return
        await _send_message(
            bot,
            user["chat_id"],
            "Usage: /batch <url1> <url2> ...\nExample: /batch https://youtu.be/xxx https://youtu.be/yyy",
            reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
        )
        return
    bot = await get_bot()
    if not bot:
        return
    _increment_counter(user["telegram_id"], "download_count", len(urls))
    lines = [f"<b>Batch Download</b>", rich_divider(), f"Queued {len(urls)} URL(s):", ""]
    for u in urls[:10]:
        src = detect_source_from_url(u)
        lines.append(f"• {rich_esc(u[:70])} ({src})")
    if len(urls) > 10:
        lines.append(f"... and {len(urls) - 10} more.")
    lines.append("")
    lines.append("Downloads are processing in the background.")
    await _send_message(
        bot,
        user["chat_id"],
        "\n".join(lines),
        reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
    )


@router.message(Command("recent"))
async def cmd_recent(message: Message) -> None:
    user = _extract_user_from_message(message)
    bot = await get_bot()
    if not bot:
        return
    jobs = dl_list_jobs(user["telegram_id"])
    lines = ["<b>Recent Downloads</b>", rich_divider()]
    if not jobs:
        lines.append("No recent downloads.")
    else:
        for j in jobs[:10]:
            lines.append(f"• {rich_esc(str(j.get('url', ''))[:60])} — {j.get('status', 'unknown')}")
    lines.append("")
    lines.append("Use /batch to download multiple URLs at once.")
    await _send_message(
        bot,
        user["chat_id"],
        "\n".join(lines),
        reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
    )


@router.message(Command("platforms"))
async def cmd_platforms(message: Message) -> None:
    user = _extract_user_from_message(message)
    sources = list_all_sources()
    lines = ["<b>Supported Platforms</b>", rich_divider()]
    for s in sources:
        lines.append(f"• {s}")
    lines.append("")
    lines.append("Auto-detection: paste any URL from these platforms in chat and I'll offer to download it.")
    bot = await get_bot()
    if not bot:
        return
    await _send_message(
        bot,
        user["chat_id"],
        "\n".join(lines),
        reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
    )


@router.message(F.text)
async def cmd_autodetect(message: Message) -> None:
    """Auto-detect media URLs in plain text messages."""
    text = message.text or ""
    if text.startswith("/"):
        return  # Let command handlers handle these

    urls = detect_urls(text)
    if not urls:
        return  # No URLs found, ignore

    user = _extract_user_from_message(message)
    source_name = detect_source_from_url(urls[0])
    is_playlist = is_playlist_url(urls[0])

    bot = await get_bot()
    if not bot:
        return

    lines = [
        f"<b>🔗 URL Detected</b>",
        rich_divider(),
        f"Found {len(urls)} link(s) from {source_name}:",
        "",
    ]
    for u in urls[:5]:
        lines.append(f"• {rich_esc(u[:80])}")
    if len(urls) > 5:
        lines.append(f"... and {len(urls) - 5} more.")
    lines.append("")
    if is_playlist:
        lines.append("📋 This looks like a playlist!")
    else:
        lines.append("📥 Download this link?")
    lines.append("")
    lines.append("Use /download <URL> to download, or /batch to download all at once.")

    buttons = []
    for u in urls[:3]:
        buttons.append([_cb_button("⬇️ Download", f"cb:dl:{u}")])
    buttons.append([_cb_button("⬅️ Menu", "cb:menu")])

    await _send_message(
        bot,
        message.chat.id,
        "\n".join(lines),
        reply_markup=_keyboard(buttons),
    )


# ---------------------------------------------------------------------------
# Background download flow
# ---------------------------------------------------------------------------

async def _do_search(user: dict, query: str, message_id: Optional[int], chat_id: int | str, bot: Bot) -> None:
    try:
        results = dl_search(query)
    except Exception as exc:
        logger.error("search failed: %s", exc)
        results = []
    lines = [f"<b>Search Results</b>", rich_divider(), f"Query: {rich_esc(query)}", ""]
    if not results:
        lines.append("No results found.")
    else:
        for r in results[:10]:
            lines.append(f"• {rich_esc(str(r.get('title', 'Unknown'))[:70])}")
    lines.append("")
    lines.append("Use /download <url> to download a result.")
    await _send_message(
        bot,
        chat_id,
        "\n".join(lines),
        reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
    )


async def _do_download(user: dict, url: str, chat_id: int | str, bot: Bot) -> None:
    try:
        job = DownloadJob(url=url, user_id=user["telegram_id"])
        dl_enqueue_download(job)
        _increment_counter(user["telegram_id"], "download_count", 1)
    except Exception as exc:
        logger.error("enqueue_download failed: %s", exc)
        await _send_message(
            bot,
            chat_id,
            f"Failed to start download: {rich_esc(str(exc))}",
            reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
        )
        return
    await _send_message(
        bot,
        chat_id,
        f"<b>Download Started</b>" + rich_divider() + f"URL: {rich_esc(url[:80])}\nStatus: Queued",
        reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
    )


async def _do_info(user: dict, query: str, chat_id: int | str, bot: Bot) -> None:
    try:
        info = dl_extract_info(query)
    except Exception as exc:
        logger.error("extract_info failed: %s", exc)
        info = {}
    lines = [f"<b>Track Info</b>", rich_divider(), f"URL: {rich_esc(query[:80])}", ""]
    if not info:
        lines.append("No info available.")
    else:
        for k, v in list(info.items())[:10]:
            lines.append(f"• {rich_esc(str(k))}: {rich_esc(str(v)[:80])}")
    lines.append("")
    lines.append("Use /download <url> to download this track.")
    await _send_message(
        bot,
        chat_id,
        "\n".join(lines),
        reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
    )


async def _do_lyrics(user: dict, query: str, chat_id: int | str, bot: Bot) -> None:
    try:
        lyrics = dl_extract_lyrics(query)
    except Exception as exc:
        logger.error("extract_lyrics failed: %s", exc)
        lyrics = ""
    lines = [f"<b>Lyrics</b>", rich_divider(), f"Query: {rich_esc(query[:80])}", ""]
    lines.append(lyrics or "No lyrics found.")
    lines.append("")
    await _send_message(
        bot,
        chat_id,
        "\n".join(lines),
        reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
    )


# ---------------------------------------------------------------------------
# Callback query handlers
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "cb:menu")
async def cb_menu(callback: CallbackQuery) -> None:
    user = _extract_user_from_callback(callback)
    is_admin = _is_admin(user["telegram_id"])
    is_owner = _is_owner(user["telegram_id"])
    bot = await get_bot()
    if not bot:
        return
    await _answer_callback_query(bot, callback.id)
    msg = callback.message
    if msg:
        await _edit_message(
            bot,
            msg.chat.id,
            msg.message_id,
            build_welcome_message(user["first_name"], is_admin, is_owner),
            reply_markup=main_menu_keyboard(is_admin),
        )


@router.callback_query(F.data == "cb:help")
async def cb_help(callback: CallbackQuery) -> None:
    user = _extract_user_from_callback(callback)
    is_admin = _is_admin(user["telegram_id"])
    is_owner = _is_owner(user["telegram_id"])
    bot = await get_bot()
    if not bot:
        return
    await _answer_callback_query(bot, callback.id)
    msg = callback.message
    if msg:
        await _edit_message(
            bot,
            msg.chat.id,
            msg.message_id,
            build_help_message(is_admin, is_owner),
            reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
        )


@router.callback_query(F.data == "cb:tier")
async def cb_tier(callback: CallbackQuery) -> None:
    user = _extract_user_from_callback(callback)
    u = _get_or_create_user(user["telegram_id"], user["username"], user["first_name"])
    bot = await get_bot()
    if not bot:
        return
    await _answer_callback_query(bot, callback.id)
    msg = callback.message
    if msg:
        await _edit_message(
            bot,
            msg.chat.id,
            msg.message_id,
            build_tier_message(u.get("tier", "free"), _is_admin(user["telegram_id"])),
            reply_markup=tier_keyboard(),
        )


@router.callback_query(F.data == "cb:keys")
async def cb_keys(callback: CallbackQuery) -> None:
    user = _extract_user_from_callback(callback)
    u = _get_or_create_user(user["telegram_id"], user["username"], user["first_name"])
    keys = u.get("keys", [])
    lines = [f"<b>Your API Keys ({len(keys)})</b>", rich_divider()]
    if not keys:
        lines.append("No keys yet.")
    else:
        for k in keys[:5]:
            lines.append(f"• <code>{rich_esc(str(k.get('key', ''))[:12])}...</code> — {k.get('tier', 'free')}")
    bot = await get_bot()
    if not bot:
        return
    await _answer_callback_query(bot, callback.id)
    msg = callback.message
    if msg:
        await _edit_message(
            bot,
            msg.chat.id,
            msg.message_id,
            "\n".join(lines),
            reply_markup=keys_keyboard(),
        )


@router.callback_query(F.data == "cb:key:create")
async def cb_key_create(callback: CallbackQuery) -> None:
    user = _extract_user_from_callback(callback)
    u = _get_or_create_user(user["telegram_id"], user["username"], user["first_name"])
    try:
        key = auth_create_key(user["telegram_id"], tier=u.get("tier", "free"))
    except Exception as exc:
        logger.error("create_api_key failed: %s", exc)
        key = None
    bot = await get_bot()
    if not bot:
        return
    await _answer_callback_query(bot, callback.id)
    msg = callback.message
    if msg:
        if key:
            await _edit_message(
                bot,
                msg.chat.id,
                msg.message_id,
                f"<b>API Key Created</b>" + rich_divider() + f"<code>{rich_esc(str(key))}</code>" + "\n\nSave it securely — it won't be shown again.",
                reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
            )
        else:
            await _edit_message(
                bot,
                msg.chat.id,
                msg.message_id,
                "Failed to create API key.",
                reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
            )


@router.callback_query(F.data == "cb:key:revoke")
async def cb_key_revoke(callback: CallbackQuery) -> None:
    user = _extract_user_from_callback(callback)
    u = _get_or_create_user(user["telegram_id"], user["username"], user["first_name"])
    keys = u.get("keys", [])
    if not keys:
        bot = await get_bot()
        if not bot:
            return
        await _answer_callback_query(bot, callback.id, "No keys to revoke", show_alert=True)
        return
    key_id = keys[0].get("key") or keys[0].get("key_id")
    try:
        auth_revoke_key(key_id)
    except Exception as exc:
        logger.error("revoke_api_key failed: %s", exc)
    bot = await get_bot()
    if not bot:
        return
    await _answer_callback_query(bot, callback.id, "Key revoked")
    msg = callback.message
    if msg:
        await cb_keys(callback)


@router.callback_query(F.data == "cb:key:rotate")
async def cb_key_rotate(callback: CallbackQuery) -> None:
    user = _extract_user_from_callback(callback)
    u = _get_or_create_user(user["telegram_id"], user["username"], user["first_name"])
    keys = u.get("keys", [])
    if not keys:
        bot = await get_bot()
        if not bot:
            return
        await _answer_callback_query(bot, callback.id, "No keys to rotate", show_alert=True)
        return
    key_id = keys[0].get("key") or keys[0].get("key_id")
    try:
        auth_rotate_key(key_id)
    except Exception as exc:
        logger.error("rotate_api_key failed: %s", exc)
    bot = await get_bot()
    if not bot:
        return
    await _answer_callback_query(bot, callback.id, "Key rotated")
    msg = callback.message
    if msg:
        await cb_keys(callback)


@router.callback_query(F.data == "cb:buy")
async def cb_buy(callback: CallbackQuery) -> None:
    user = _extract_user_from_callback(callback)
    bot = await get_bot()
    if not bot:
        return
    await _answer_callback_query(bot, callback.id)
    msg = callback.message
    if msg:
        await _edit_message(
            bot,
            msg.chat.id,
            msg.message_id,
            "<b>Upgrade Tier</b>" + rich_divider() + "Contact the owner to upgrade your tier.",
            reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
        )


@router.callback_query(F.data == "cb:search")
async def cb_search(callback: CallbackQuery) -> None:
    user = _extract_user_from_callback(callback)
    bot = await get_bot()
    if not bot:
        return
    await _answer_callback_query(bot, callback.id)
    msg = callback.message
    if msg:
        await _edit_message(
            bot,
            msg.chat.id,
            msg.message_id,
            "<b>Search</b>" + rich_divider() + "Use /search <query> to search media across sources.",
            reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
        )


@router.callback_query(F.data == "cb:download")
async def cb_download(callback: CallbackQuery) -> None:
    user = _extract_user_from_callback(callback)
    bot = await get_bot()
    if not bot:
        return
    await _answer_callback_query(bot, callback.id)
    msg = callback.message
    if msg:
        await _edit_message(
            bot,
            msg.chat.id,
            msg.message_id,
            "<b>Download</b>" + rich_divider() + "Use /download <url> to download media.",
            reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
        )


@router.callback_query(F.data == "cb:info")
async def cb_info(callback: CallbackQuery) -> None:
    user = _extract_user_from_callback(callback)
    bot = await get_bot()
    if not bot:
        return
    await _answer_callback_query(bot, callback.id)
    msg = callback.message
    if msg:
        await _edit_message(
            bot,
            msg.chat.id,
            msg.message_id,
            "<b>Info</b>" + rich_divider() + "Use /info <url> to get track/album info.",
            reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
        )


@router.callback_query(F.data == "cb:lyrics")
async def cb_lyrics(callback: CallbackQuery) -> None:
    user = _extract_user_from_callback(callback)
    bot = await get_bot()
    if not bot:
        return
    await _answer_callback_query(bot, callback.id)
    msg = callback.message
    if msg:
        await _edit_message(
            bot,
            msg.chat.id,
            msg.message_id,
            "<b>Lyrics</b>" + rich_divider() + "Use /lyrics <query> to search lyrics.",
            reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
        )


@router.callback_query(F.data == "cb:status")
async def cb_status(callback: CallbackQuery) -> None:
    user = _extract_user_from_callback(callback)
    bot = await get_bot()
    if not bot:
        return
    await _answer_callback_query(bot, callback.id)
    msg = callback.message
    if msg:
        await _edit_message(
            bot,
            msg.chat.id,
            msg.message_id,
            "<b>Bot Status</b>" + rich_divider() + "✅ Online\nSources: YouTube, SoundCloud, Spotify, Apple Music, Deezer, Bandcamp",
            reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
        )


@router.callback_query(F.data == "cb:sources")
async def cb_sources(callback: CallbackQuery) -> None:
    user = _extract_user_from_callback(callback)
    sources = list_all_sources()
    lines = ["<b>Supported Platforms</b>", rich_divider()]
    for s in sources:
        lines.append(f"• {s}")
    bot = await get_bot()
    if not bot:
        return
    await _answer_callback_query(bot, callback.id)
    msg = callback.message
    if msg:
        await _edit_message(
            bot,
            msg.chat.id,
            msg.message_id,
            "\n".join(lines),
            reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
        )


@router.callback_query(F.data == "cb:settings")
async def cb_settings(callback: CallbackQuery) -> None:
    user = _extract_user_from_callback(callback)
    bot = await get_bot()
    if not bot:
        return
    await _answer_callback_query(bot, callback.id)
    msg = callback.message
    if msg:
        await _edit_message(
            bot,
            msg.chat.id,
            msg.message_id,
            "<b>Settings</b>" + rich_divider() + "Choose an option:",
            reply_markup=settings_keyboard(),
        )


@router.callback_query(F.data == "cb:settings:notify")
async def cb_settings_notify(callback: CallbackQuery) -> None:
    user = _extract_user_from_callback(callback)
    bot = await get_bot()
    if not bot:
        return
    await _answer_callback_query(bot, callback.id, "Notifications coming soon")


@router.callback_query(F.data == "cb:settings:lang")
async def cb_settings_lang(callback: CallbackQuery) -> None:
    user = _extract_user_from_callback(callback)
    bot = await get_bot()
    if not bot:
        return
    await _answer_callback_query(bot, callback.id)
    msg = callback.message
    if msg:
        await _edit_message(
            bot,
            msg.chat.id,
            msg.message_id,
            "<b>Language</b>" + rich_divider() + "Select your language:",
            reply_markup=_keyboard([
                [_cb_button("English", "cb:lang:en"), _cb_button("Español", "cb:lang:es")],
                [_cb_button("Français", "cb:lang:fr"), _cb_button("中文", "cb:lang:zh")],
                [_cb_button("⬅️ Back", "cb:settings")],
            ]),
        )


@router.callback_query(F.data == "cb:playlist")
async def cb_playlist(callback: CallbackQuery) -> None:
    user = _extract_user_from_callback(callback)
    bot = await get_bot()
    if not bot:
        return
    await _answer_callback_query(bot, callback.id)
    msg = callback.message
    if msg:
        await _edit_message(
            bot,
            msg.chat.id,
            msg.message_id,
            "<b>Playlist Download</b>" + rich_divider() + "Send a playlist URL to download all tracks.",
            reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
        )


@router.callback_query(F.data == "cb:history")
async def cb_history(callback: CallbackQuery) -> None:
    user = _extract_user_from_callback(callback)
    bot = await get_bot()
    if not bot:
        return
    await _answer_callback_query(bot, callback.id)
    jobs = dl_list_jobs(user["telegram_id"])
    lines = ["<b>Recent Downloads</b>", rich_divider()]
    if not jobs:
        lines.append("No downloads yet.")
    else:
        for j in jobs[:10]:
            lines.append(f"• {rich_esc(str(j.get('url', ''))[:60])} — {j.get('status', 'unknown')}")
    msg = callback.message
    if msg:
        await _edit_message(
            bot,
            msg.chat.id,
            msg.message_id,
            "\n".join(lines),
            reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
        )


@router.callback_query(F.data == "cb:admin")
async def cb_admin(callback: CallbackQuery) -> None:
    user = _extract_user_from_callback(callback)
    if not _is_admin(user["telegram_id"]):
        bot = await get_bot()
        if not bot:
            return
        await _answer_callback_query(bot, callback.id, "⛔ Owner-only", show_alert=True)
        return
    bot = await get_bot()
    if not bot:
        return
    await _answer_callback_query(bot, callback.id)
    msg = callback.message
    if msg:
        await _edit_message(
            bot,
            msg.chat.id,
            msg.message_id,
            "<b>Admin Panel</b>" + rich_divider() + "Owner-only management:",
            reply_markup=admin_keyboard(),
        )


@router.callback_query(F.data == "cb:admin:users")
async def cb_admin_users(callback: CallbackQuery) -> None:
    user = _extract_user_from_callback(callback)
    if not _is_admin(user["telegram_id"]):
        bot = await get_bot()
        if not bot:
            return
        await _answer_callback_query(bot, callback.id, "⛔ Owner-only", show_alert=True)
        return
    users = _load_users()
    lines = ["<b>All Users</b>", rich_divider(), f"Total: {len(users)}", ""]
    for u in users[:50]:
        lines.append(f"• {u.get('first_name', 'User')} ({u.get('telegram_id')}) — {u.get('tier', 'free')}")
    bot = await get_bot()
    if not bot:
        return
    await _answer_callback_query(bot, callback.id)
    msg = callback.message
    if msg:
        await _edit_message(
            bot,
            msg.chat.id,
            msg.message_id,
            "\n".join(lines),
            reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
        )


@router.callback_query(F.data == "cb:admin:stats")
async def cb_admin_stats(callback: CallbackQuery) -> None:
    user = _extract_user_from_callback(callback)
    if not _is_admin(user["telegram_id"]):
        bot = await get_bot()
        if not bot:
            return
        await _answer_callback_query(bot, callback.id, "⛔ Owner-only", show_alert=True)
        return
    users = _load_users()
    total_downloads = sum(u.get("download_count", 0) for u in users)
    total_keys = sum(len(u.get("keys", [])) for u in users)
    total_bytes = sum(u.get("monthly_bytes", 0) for u in users)
    gb = total_bytes / (1024 ** 3)
    lines = [
        "<b>Bot Statistics</b>",
        rich_divider(),
        f"Total Users: {len(users)}",
        f"Total Downloads: {total_downloads}",
        f"Total API Keys: {total_keys}",
        f"Total Data: {gb:.2f} GB",
    ]
    bot = await get_bot()
    if not bot:
        return
    await _answer_callback_query(bot, callback.id)
    msg = callback.message
    if msg:
        await _edit_message(
            bot,
            msg.chat.id,
            msg.message_id,
            "\n".join(lines),
            reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
        )


@router.callback_query(F.data == "cb:admin:broadcast")
async def cb_admin_broadcast(callback: CallbackQuery) -> None:
    user = _extract_user_from_callback(callback)
    if not _is_admin(user["telegram_id"]):
        bot = await get_bot()
        if not bot:
            return
        await _answer_callback_query(bot, callback.id, "⛔ Owner-only", show_alert=True)
        return
    bot = await get_bot()
    if not bot:
        return
    await _answer_callback_query(bot, callback.id, "Use /broadcast <message>")


@router.callback_query(F.data == "cb:admin:keys")
async def cb_admin_keys(callback: CallbackQuery) -> None:
    user = _extract_user_from_callback(callback)
    if not _is_admin(user["telegram_id"]):
        bot = await get_bot()
        if not bot:
            return
        await _answer_callback_query(bot, callback.id, "⛔ Owner-only", show_alert=True)
        return
    bot = await get_bot()
    if not bot:
        return
    await _answer_callback_query(bot, callback.id, "Key management via /key")


@router.callback_query(F.data == "cb:admin:system")
async def cb_admin_system(callback: CallbackQuery) -> None:
    user = _extract_user_from_callback(callback)
    if not _is_admin(user["telegram_id"]):
        bot = await get_bot()
        if not bot:
            return
        await _answer_callback_query(bot, callback.id, "⛔ Owner-only", show_alert=True)
        return
    bot = await get_bot()
    if not bot:
        return
    await _answer_callback_query(bot, callback.id, "System info coming soon")


@router.callback_query(F.data.startswith("cb:dl:"))
async def cb_download_url(callback: CallbackQuery) -> None:
    user = _extract_user_from_callback(callback)
    url = callback.data[len("cb:dl:"):]
    bot = await get_bot()
    if not bot:
        return
    await _answer_callback_query(bot, callback.id, "Download started")
    await _do_download(user, url, user["chat_id"], bot)


@router.callback_query(F.data.startswith("cb:tier:"))
async def cb_tier_select(callback: CallbackQuery) -> None:
    user = _extract_user_from_callback(callback)
    tier = callback.data[len("cb:tier:"):]
    bot = await get_bot()
    if not bot:
        return
    await _answer_callback_query(bot, callback.id, f"Tier set to {tier}")
    msg = callback.message
    if msg:
        await _edit_message(
            bot,
            msg.chat.id,
            msg.message_id,
            f"<b>Tier: {tier}</b>" + rich_divider() + "Tier updated.",
            reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
        )


@router.callback_query(F.data.startswith("cb:lang:"))
async def cb_lang_select(callback: CallbackQuery) -> None:
    user = _extract_user_from_callback(callback)
    lang = callback.data[len("cb:lang:"):]
    bot = await get_bot()
    if not bot:
        return
    await _answer_callback_query(bot, callback.id, f"Language set to {lang}")
    msg = callback.message
    if msg:
        await _edit_message(
            bot,
            msg.chat.id,
            msg.message_id,
            f"<b>Language: {lang}</b>" + rich_divider() + "Language updated.",
            reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
        )


# ---------------------------------------------------------------------------
# Inline query
# ---------------------------------------------------------------------------

@router.inline_query()
async def handle_inline_query(inline_query: InlineQuery) -> None:
    query = inline_query.query or ""
    bot = await get_bot()
    if not bot:
        return
    if not query:
        await _answer_inline_query(bot, inline_query.id, [], cache_time=1)
        return
    try:
        results = dl_search(query)
    except Exception as exc:
        logger.error("inline search failed: %s", exc)
        results = []
    from aiogram.types import InlineQueryResultArticle, InputTextMessageContent
    inline_results = []
    for r in results[:10]:
        inline_results.append(
            InlineQueryResultArticle(
                id=str(uuid.uuid4()),
                title=str(r.get("title", "Unknown"))[:100],
                input_message_content=InputTextMessageContent(
                    message_text=f"/download {rich_esc(str(r.get('url', '')))}"
                ),
            )
        )
    await _answer_inline_query(bot, inline_query.id, inline_results, cache_time=300)


# ---------------------------------------------------------------------------
# Pre-checkout query
# ---------------------------------------------------------------------------

@router.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: PreCheckoutQuery) -> None:
    bot = await get_bot()
    if not bot:
        return
    await _answer_pre_checkout_query(bot, pre_checkout_query.id, ok=True)


# ---------------------------------------------------------------------------
# Successful payment
# ---------------------------------------------------------------------------

@router.message(F.successful_payment)
async def successful_payment_handler(message: Message) -> None:
    user = _extract_user_from_message(message)
    bot = await get_bot()
    if not bot:
        return
    await _send_message(
        bot,
        user["chat_id"],
        "✅ Payment received! Thank you for supporting Videl-Api.",
        reply_markup=_keyboard([[_cb_button("⬅️ Menu", "cb:menu")]]),
    )


# ---------------------------------------------------------------------------
# Handler registration
# ---------------------------------------------------------------------------

def _register_handlers() -> None:
    dp.include_router(router)
    logger.info("All Telegram bot handlers registered with Router")


_register_handlers()


# ---------------------------------------------------------------------------
# Webhook / polling helpers
# ---------------------------------------------------------------------------

async def set_webhook(base_url: str) -> None:
    bot = await get_bot()
    if not bot:
        return
    try:
        await bot.set_webhook(url=f"{base_url}/webhook/telegram", drop_pending_updates=True)
        logger.info("Webhook set: %s/webhook/telegram", base_url)
    except Exception as exc:
        logger.error("set_webhook failed: %s", exc)


async def delete_webhook() -> None:
    bot = await get_bot()
    if not bot:
        return
    for attempt in range(5):
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            logger.info("Cleared existing webhook before polling")
            return
        except Exception as exc:
            logger.warning("Could not clear webhook (attempt %d/5): %s", attempt + 1, exc)
            await asyncio.sleep(2)


async def set_bot_commands() -> None:
    bot = await get_bot()
    if not bot:
        return
    from aiogram.types import BotCommand
    commands = [
        BotCommand(command="start", description="Welcome & main menu"),
        BotCommand(command="help", description="Show help"),
        BotCommand(command="search", description="Search media"),
        BotCommand(command="download", description="Download media"),
        BotCommand(command="info", description="Track info"),
        BotCommand(command="lyrics", description="Search lyrics"),
        BotCommand(command="key", description="Manage API keys"),
        BotCommand(command="createkey", description="Create API key"),
        BotCommand(command="buy", description="Upgrade tier"),
        BotCommand(command="status", description="Bot status"),
        BotCommand(command="sources", description="Supported platforms"),
        BotCommand(command="settings", description="Bot settings"),
        BotCommand(command="playlist", description="Playlist download"),
        BotCommand(command="history", description="Download history"),
        BotCommand(command="notify", description="Notifications"),
        BotCommand(command="feedback", description="Send feedback"),
        BotCommand(command="language", description="Change language"),
        BotCommand(command="admin", description="Admin panel (owner)"),
        BotCommand(command="broadcast", description="Broadcast (owner)"),
        BotCommand(command="users", description="List users (owner)"),
        BotCommand(command="stats", description="Bot statistics (owner)"),
        BotCommand(command="batch", description="Batch download"),
        BotCommand(command="recent", description="Recent downloads"),
        BotCommand(command="platforms", description="Supported platforms"),
    ]
    try:
        await bot.set_my_commands(commands)
        logger.info("Bot commands set (%d commands)", len(commands))
    except Exception as exc:
        logger.error("set_my_commands failed: %s", exc)


# ---------------------------------------------------------------------------
# Update processing (FastAPI webhook entry point)
# ---------------------------------------------------------------------------

async def process_update(update: dict) -> None:
    bot = await get_bot()
    if not bot:
        return
    try:
        tg_update = Update(**update)
        await dp.feed_update(bot, tg_update)
    except Exception as exc:
        logger.error("process_update failed: %s", exc)


# ---------------------------------------------------------------------------
# Polling (long-polling entry point)
# ---------------------------------------------------------------------------

async def start_bot_polling() -> None:
    """Long-polling entry point using aiogram Dispatcher."""
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
    await delete_webhook()

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
    except Exception as exc:
        logger.error("Polling error: %s", exc)
        # Indefinite conflict backoff: 5s -> 600s cap
        backoff = 5
        while True:
            logger.warning("Polling crashed, retrying in %ds: %s", backoff, exc)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 600)
            try:
                await dp.start_polling(
                    bot,
                    allowed_updates=dp.resolve_used_update_types(),
                    drop_pending_updates=True,
                    polling_timeout=30,
                )
                break
            except asyncio.CancelledError:
                raise
            except Exception as exc2:
                exc = exc2
                continue
    finally:
        _polling_active = False
        logger.info("Telegram bot polling stopped")
