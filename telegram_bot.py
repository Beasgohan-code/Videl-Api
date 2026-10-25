"""
Videl-Api Telegram Bot

Full-featured Telegram Bot with:
- Rich messages (inline keyboards, media groups, formatted text)
- New Bot API features (inline queries, callback queries, invoices/Stars)
- Owner / Admin access control
- Telegram Stars payments
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
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import aiohttp

from config import settings, list_all_sources, MUSIC_SOURCES
from downloader import (
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
# Telegram Bot API client (raw HTTP - no external wrapper needed)
# ---------------------------------------------------------------------------

class TelegramBot:
    """Raw Telegram Bot API client using aiohttp."""

    def __init__(self, token: str):
        self.token = token
        self.base = f"https://api.telegram.org/bot{token}"
        self._session: Optional[aiohttp.ClientSession] = None

    async def _session_get(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _request(self, method: str, payload: dict) -> dict:
        session = await self._session_get()
        async with session.post(f"{self.base}/{method}", json=payload, timeout=30) as resp:
            data = await resp.json()
            if not data.get("ok"):
                raise RuntimeError(f"Telegram API error: {data.get('description', 'unknown')}")
            return data.get("result", {})

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    # --- Send methods ---

    async def send_message(
        self,
        chat_id: int | str,
        text: str,
        *,
        parse_mode: str = "HTML",
        reply_markup: Optional[dict] = None,
        reply_to_message_id: Optional[int] = None,
        disable_web_page_preview: bool = True,
    ) -> dict:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_web_page_preview,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        if reply_to_message_id:
            payload["reply_to_message_id"] = reply_to_message_id
        return await self._request("sendMessage", payload)

    async def send_photo(
        self,
        chat_id: int | str,
        photo: str,
        *,
        caption: Optional[str] = None,
        parse_mode: str = "HTML",
        reply_markup: Optional[dict] = None,
    ) -> dict:
        payload: dict[str, Any] = {"chat_id": chat_id, "photo": photo}
        if caption:
            payload["caption"] = caption
            payload["parse_mode"] = parse_mode
        if reply_markup:
            payload["reply_markup"] = reply_markup
        return await self._request("sendPhoto", payload)

    async def send_audio(
        self,
        chat_id: int | str,
        audio: str,
        *,
        caption: Optional[str] = None,
        title: Optional[str] = None,
        performer: Optional[str] = None,
        duration: Optional[int] = None,
        parse_mode: str = "HTML",
        reply_markup: Optional[dict] = None,
    ) -> dict:
        payload: dict[str, Any] = {"chat_id": chat_id, "audio": audio}
        if caption:
            payload["caption"] = caption
            payload["parse_mode"] = parse_mode
        if title:
            payload["title"] = title
        if performer:
            payload["performer"] = performer
        if duration:
            payload["duration"] = duration
        if reply_markup:
            payload["reply_markup"] = reply_markup
        return await self._request("sendAudio", payload)

    async def send_document(
        self,
        chat_id: int | str,
        document: str,
        *,
        caption: Optional[str] = None,
        parse_mode: str = "HTML",
        reply_markup: Optional[dict] = None,
    ) -> dict:
        payload: dict[str, Any] = {"chat_id": chat_id, "document": document}
        if caption:
            payload["caption"] = caption
            payload["parse_mode"] = parse_mode
        if reply_markup:
            payload["reply_markup"] = reply_markup
        return await self._request("sendDocument", payload)

    async def send_invoice(
        self,
        chat_id: int | str,
        title: str,
        description: str,
        payload_str: str,
        currency: str = "XTR",
        prices: list[dict] | None = None,
        provider_token: str = "",
        max_tip_amount: Optional[int] = None,
        suggested_tip_amounts: list[int] | None = None,
        start_parameter: str = "stars",
        reply_markup: Optional[dict] = None,
    ) -> dict:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "title": title,
            "description": description,
            "payload": payload_str,
            "currency": currency,
            "prices": prices or [{"label": "Pro Tier", "amount": 100}],
            "provider_token": provider_token,
            "start_parameter": start_parameter,
        }
        if max_tip_amount is not None:
            payload["max_tip_amount"] = max_tip_amount
        if suggested_tip_amounts:
            payload["suggested_tip_amounts"] = suggested_tip_amounts
        if reply_markup:
            payload["reply_markup"] = reply_markup
        return await self._request("sendInvoice", payload)

    async def answer_pre_checkout_query(
        self,
        pre_checkout_query_id: str,
        ok: bool,
        error_message: Optional[str] = None,
    ) -> dict:
        payload: dict[str, Any] = {
            "pre_checkout_query_id": pre_checkout_query_id,
            "ok": ok,
        }
        if error_message:
            payload["error_message"] = error_message
        return await self._request("answerPreCheckoutQuery", payload)

    async def answer_inline_query(
        self,
        inline_query_id: str,
        results: list[dict],
        *,
        cache_time: int = 300,
        is_personal: bool = True,
    ) -> dict:
        return await self._request(
            "answerInlineQuery",
            {
                "inline_query_id": inline_query_id,
                "results": results,
                "cache_time": cache_time,
                "is_personal": is_personal,
            },
        )

    async def answer_callback_query(
        self,
        callback_query_id: str,
        *,
        text: Optional[str] = None,
        show_alert: bool = False,
        url: Optional[str] = None,
        cache_time: Optional[int] = None,
    ) -> dict:
        payload: dict[str, Any] = {"callback_query_id": callback_query_id}
        if text is not None:
            payload["text"] = text
            payload["show_alert"] = show_alert
        if url:
            payload["url"] = url
        if cache_time is not None:
            payload["cache_time"] = cache_time
        return await self._request("answerCallbackQuery", payload)

    async def set_my_commands(self, commands: list[dict]) -> dict:
        return await self._request("setMyCommands", {"commands": commands})

    async def get_chat_member(self, chat_id: int | str, user_id: int) -> dict:
        return await self._request(
            "getChatMember", {"chat_id": chat_id, "user_id": user_id}
        )

    async def send_chat_action(self, chat_id: int | str, action: str) -> dict:
        return await self._request("sendChatAction", {"chat_id": chat_id, "action": action})

    # --- Inline keyboard helpers ---

    @staticmethod
    def keyboard(buttons: list[list[dict]]) -> dict:
        """Build an inline keyboard markup."""
        return {"inline_keyboard": [[b for b in row] for row in buttons]}

    @staticmethod
    def cb_button(text: str, callback_data: str) -> dict:
        return {"text": text, "callback_data": callback_data}

    @staticmethod
    def url_button(text: str, url: str) -> dict:
        return {"text": text, "url": url}


# ---------------------------------------------------------------------------
# Bot instance (lazy init)
# ---------------------------------------------------------------------------

_bot: Optional[TelegramBot] = None
_bot_lock = asyncio.Lock()
_bot_initialized = False


async def get_bot() -> Optional[TelegramBot]:
    global _bot, _bot_initialized
    async with _bot_lock:
        if _bot_initialized:
            return _bot
        token = settings.telegram_bot_token
        if not token:
            logger.warning("TELEGRAM_BOT_TOKEN not set; bot disabled")
            _bot_initialized = True
            return None
        _bot = TelegramBot(token)
        _bot_initialized = True
        return _bot


# ---------------------------------------------------------------------------
# User / tier / key storage helpers (JSON fallback)
# ---------------------------------------------------------------------------

USERS_FILE = os.path.join(os.path.dirname(KEYS_FILE), "users.json") if KEYS_FILE else "users.json"


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
        "id": str(uuid.uuid4()),
        "telegram_id": telegram_id,
        "username": username,
        "first_name": first_name,
        "tier": "free",
        "scopes": ["read", "search"],
        "is_admin": False,
        "is_owner": False,
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
# Rich message builders
# ---------------------------------------------------------------------------

def build_welcome_message(first_name: str, is_admin: bool = False) -> str:
    admin_line = "\n👑 <b>Owner/Admin mode enabled.</b>" if is_admin else ""
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
        f"Use /help to see all commands.{admin_line}"
    )


def build_help_message(is_admin: bool = False) -> str:
    cmds = [
        ("/start", "Welcome &amp; main menu"),
        ("/help", "Show this help message"),
        ("/search", "Search music &amp; media"),
        ("/download", "Download a track by URL"),
        ("/info", "Get track/album info"),
        ("/lyrics", "Get lyrics for a track"),
        ("/key", "Manage your API keys"),
        ("/tier", "View &amp; change subscription tier"),
        ("/buy", "Buy Pro tier with Telegram Stars"),
        ("/playlist", "Manage your playlists"),
        ("/history", "View download history"),
        ("/settings", "User settings &amp; language"),
        ("/notify", "Notification preferences"),
        ("/source", "List supported sources"),
        ("/status", "System status"),
        ("/feedback", "Send feedback"),
        ("/language", "Change interface language"),
    ]
    if is_admin:
        cmds += [
            ("/admin", "Admin panel (owner only)"),
            ("/broadcast", "Broadcast to all users (owner only)"),
            ("/users", "User management (owner only)"),
            ("/stats", "Bot statistics (owner only)"),
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
        f"📊 Monthly bytes: {limits['monthly_bytes'] / (1024*1024 / 1024):.0f} GB\n"
        f"⚡ Rate limit: {rate_str} req/min\n"
        f"🔑 Scopes: {', '.join(limits['scopes'])}\n\n"
        f"Upgrade to Pro with /buy or contact admin for Owner access."
    )


# ---------------------------------------------------------------------------
# Inline keyboard builders
# ---------------------------------------------------------------------------

def main_menu_keyboard(is_admin: bool = False) -> dict:
    rows = [
        [TelegramBot.cb_button("🔍 Search", "cb:search"), TelegramBot.cb_button("📥 Download", "cb:download")],
        [TelegramBot.cb_button("🎵 Info", "cb:info"), TelegramBot.cb_button("📝 Lyrics", "cb:lyrics")],
        [TelegramBot.cb_button("🔑 API Keys", "cb:keys"), TelegramBot.cb_button("💎 Tier", "cb:tier")],
        [TelegramBot.cb_button("💳 Buy Pro", "cb:buy"), TelegramBot.cb_button("📋 Playlist", "cb:playlist")],
        [TelegramBot.cb_button("📊 Stats", "cb:stats"), TelegramBot.cb_button("⚙️ Settings", "cb:settings")],
        [TelegramBot.cb_button("📡 Sources", "cb:sources"), TelegramBot.cb_button("📢 Status", "cb:status")],
    ]
    if is_admin:
        rows.append([TelegramBot.cb_button("👑 Admin Panel", "cb:admin")])
    rows.append([TelegramBot.cb_button("❓ Help", "cb:help")])
    return TelegramBot.keyboard(rows)


def tier_keyboard() -> dict:
    return TelegramBot.keyboard([
        [TelegramBot.cb_button("🆓 Free", "cb:tier:free"), TelegramBot.cb_button("💎 Pro (100 Stars)", "cb:tier:pro")],
        [TelegramBot.cb_button("👑 Owner (Contact Admin)", "cb:tier:owner")],
        [TelegramBot.cb_button("⬅️ Back", "cb:menu")],
    ])


def keys_keyboard() -> dict:
    return TelegramBot.keyboard([
        [TelegramBot.cb_button("➕ Create Key", "cb:key:create"),
         TelegramBot.cb_button("📋 List Keys", "cb:key:list")],
        [TelegramBot.cb_button("🔄 Rotate Key", "cb:key:rotate"),
         TelegramBot.cb_button("❌ Revoke Key", "cb:key:revoke")],
        [TelegramBot.cb_button("⬅️ Back", "cb:menu")],
    ])


def admin_keyboard() -> dict:
    return TelegramBot.keyboard([
        [TelegramBot.cb_button("👥 Users", "cb:admin:users"),
         TelegramBot.cb_button("📊 Stats", "cb:admin:stats")],
        [TelegramBot.cb_button("📢 Broadcast", "cb:admin:broadcast"),
         TelegramBot.cb_button("🔑 All Keys", "cb:admin:keys")],
        [TelegramBot.cb_button("⚙️ System", "cb:admin:system"),
         TelegramBot.cb_button("⬅️ Back", "cb:menu")],
    ])


def settings_keyboard() -> dict:
    return TelegramBot.keyboard([
        [TelegramBot.cb_button("🌐 Language", "cb:settings:lang"),
         TelegramBot.cb_button("𔔨 Notifications", "cb:settings:notify")],
        [TelegramBot.cb_button("⬅️ Back", "cb:menu")],
    ])


# ---------------------------------------------------------------------------
# Handler functions
# ---------------------------------------------------------------------------

async def handle_start(bot: TelegramBot, chat_id: int | str, user: dict, message_id: Optional[int] = None) -> None:
    is_admin = user.get("is_admin", False) or user.get("is_owner", False)
    text = build_welcome_message(user.get("first_name", "User"), is_admin)
    kb = main_menu_keyboard(is_admin)
    if message_id:
        await bot._request("editMessageText", {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML",
            "reply_markup": kb,
        })
    else:
        await bot.send_message(chat_id, text, reply_markup=kb)


async def handle_help(bot: TelegramBot, chat_id: int | str, user: dict) -> None:
    is_admin = user.get("is_admin", False) or user.get("is_owner", False)
    text = build_help_message(is_admin)
    kb = TelegramBot.keyboard([[TelegramBot.cb_button("⬅️ Back to Menu", "cb:menu")]])
    await bot.send_message(chat_id, text, reply_markup=kb)


async def handle_tier(bot: TelegramBot, chat_id: int | str, user: dict) -> None:
    tier = user.get("tier", "free")
    is_admin = user.get("is_admin", False) or user.get("is_owner", False)
    text = build_tier_message(tier, is_admin)
    await bot.send_message(chat_id, text, reply_markup=tier_keyboard())


async def handle_search(bot: TelegramBot, chat_id: int | str, user: dict, query: Optional[str] = None) -> None:
    if not query:
        text = (
            "🔍 <b>Search</b>\n\n"
            "Send me a search query or use inline mode.\n"
            "Example: /search imagine dragons"
        )
        kb = TelegramBot.keyboard([[TelegramBot.cb_button("⬅️ Back", "cb:menu")]])
        await bot.send_message(chat_id, text, reply_markup=kb)
        return

    _increment_counter(user["telegram_id"], "search_count")
    try:
        results = await dl_search(query, source="youtube", limit=5)
    except Exception as exc:
        await bot.send_message(chat_id, f"❌ Search failed: {exc}")
        return

    if not results:
        await bot.send_message(chat_id, "🔍 No results found.")
        return

    lines = [f"🔍 <b>Search results for:</b> {query}\n"]
    buttons = []
    for i, r in enumerate(results):
        title = r.get("title", "Unknown")
        uploader = r.get("uploader", "Unknown")
        dur = r.get("duration")
        dur_str = f" ({dur}s)" if dur else ""
        lines.append(f"{i+1}. <b>{title}</b> — {uploader}{dur_str}")
        buttons.append([TelegramBot.cb_button(f"⬇️ {title[:30]}", f"cb:dl:{r.get('url','')}")])

    buttons.append([TelegramBot.cb_button("⬅️ Back", "cb:menu")])
    await bot.send_message(chat_id, "\n".join(lines), reply_markup=TelegramBot.keyboard(buttons))


async def handle_keys(bot: TelegramBot, chat_id: int | str, user: dict) -> None:
    telegram_id = user["telegram_id"]
    keys = auth_list_keys(telegram_id)
    key_list = keys.get("keys", []) if isinstance(keys, dict) else []

    if not key_list:
        text = "🔑 <b>API Keys</b>\n\nYou don't have any API keys yet.\nCreate one to access the API."
        await bot.send_message(chat_id, text, reply_markup=keys_keyboard())
        return

    lines = ["🔑 <b>Your API Keys</b>\n"]
    for k in key_list[:5]:
        prefix = k.get("key_prefix", "videl_")
        tier = k.get("tier", "free")
        active = "✅" if k.get("active", True) else "❌"
        lines.append(f"{active} <code>{prefix}…</code> — {tier}")

    lines.append("\nUse the buttons below to manage keys.")
    await bot.send_message(chat_id, "\n".join(lines), reply_markup=keys_keyboard())


async def handle_create_key(bot: TelegramBot, chat_id: int | str, user: dict) -> None:
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

    await bot.send_message(chat_id, text, reply_markup=keys_keyboard())


async def handle_buy(bot: TelegramBot, chat_id: int | str, user: dict) -> None:
    """Send a Telegram Stars invoice for Pro tier upgrade."""
    payload_str = f"upgrade_pro_{user['telegram_id']}_{int(time.time())}"
    prices = [{"label": "Pro Tier Upgrade", "amount": 100}]  # 100 Stars

    try:
        await bot.send_invoice(
            chat_id=chat_id,
            title="Videl-Api Pro Tier",
            description="Upgrade to Pro tier — 1000 daily requests, 10GB monthly, download access",
            payload_str=payload_str,
            currency="XTR",
            prices=prices,
            provider_token="",
            start_parameter="pro_upgrade",
        )
        # Store pending payment
        users = _load_users()
        for u in users:
            if u.get("telegram_id") == user["telegram_id"]:
                u["pending_payment"] = payload_str
                u["pending_payment_tier"] = "pro"
                u["pending_payment_amount"] = 100
                break
        _save_users(users)
    except Exception as exc:
        await bot.send_message(chat_id, f"❌ Payment setup failed: {exc}")


async def handle_status(bot: TelegramBot, chat_id: int | str) -> None:
    try:
        # Try to hit the API health endpoint if a base URL is configured
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
    await bot.send_message(chat_id, "\n".join(lines))


async def handle_sources(bot: TelegramBot, chat_id: int | str) -> None:
    sources = list_all_sources()
    music = [s for s in sources if s["type"] == "music"][:10]
    lines = ["📡 <b>Supported Sources (Music)</b>\n"]
    for s in music:
        search_tag = "🔍" if s.get("supports_search") else ""
        lines.append(f"• {s['name']} {search_tag}")
    lines.append(f"\nTotal: {len(sources)} sources across music, anime, manga, media.")
    await bot.send_message(chat_id, "\n".join(lines))


async def handle_settings(bot: TelegramBot, chat_id: int | str, user: dict) -> None:
    lang = user.get("language", "en")
    notify = "✅ On" if user.get("notifications", True) else "❌ Off"
    text = (
        f"⚙️ <b>Settings</b>\n\n"
        f"Language: {lang}\n"
        f"Notifications: {notify}\n"
    )
    await bot.send_message(chat_id, text, reply_markup=settings_keyboard())


async def handle_playlist(bot: TelegramBot, chat_id: int | str, user: dict) -> None:
    text = (
        "📋 <b>Playlists</b>\n\n"
        "Manage your playlists via the API:\n"
        "POST /v1/playlists — Create\n"
        "GET /v1/playlists — List\n"
        "Use inline search to find tracks to add."
    )
    await bot.send_message(chat_id, text, reply_markup=TelegramBot.keyboard([[TelegramBot.cb_button("⬅️ Back", "cb:menu")]] ))


async def handle_history(bot: TelegramBot, chat_id: int | str, user: dict) -> None:
    jobs = await dl_list_jobs()
    user_jobs = [j for j in jobs if j.get("user_id") == user["telegram_id"]] if isinstance(jobs, list) else []
    if not user_jobs:
        await bot.send_message(chat_id, "📦 No download history yet.")
        return
    lines = ["📦 <b>Recent Downloads</b>\n"]
    for j in user_jobs[-5:]:
        status = j.get("status", "unknown")
        title = j.get("title", "Unknown")
        lines.append(f"• {title} — {status}")
    await bot.send_message(chat_id, "\n".join(lines))


async def handle_notify(bot: TelegramBot, chat_id: int | str, user: dict) -> None:
    current = "✅ On" if user.get("notifications", True) else "❌ Off"
    new_state = not user.get("notifications", True)
    _set_user_field(user["telegram_id"], "notifications", new_state)
    state_str = "✅ On" if new_state else "❌ Off"
    await bot.send_message(chat_id, f"𔔨 Notifications are now {state_str}.")


async def handle_feedback(bot: TelegramBot, chat_id: int | str, user: dict, text: Optional[str] = None) -> None:
    if not text:
        await bot.send_message(
            chat_id,
            "📝 <b>Feedback</b>\n\nSend your feedback after this message.\nExample: /feedback Great app!",
            reply_markup=TelegramBot.keyboard([[TelegramBot.cb_button("⬅️ Back", "cb:menu")]]),
        )
        return
    # Store feedback
    users = _load_users()
    for u in users:
        if u.get("telegram_id") == user["telegram_id"]:
            u.setdefault("feedback", []).append({
                "text": text,
                "at": datetime.now(timezone.utc).isoformat(),
            })
            break
    _save_users(users)
    await bot.send_message(chat_id, "✅ Thank you for your feedback!")


async def handle_language(bot: TelegramBot, chat_id: int | str, user: dict, lang: Optional[str] = None) -> None:
    if not lang:
        kb = TelegramBot.keyboard([
            [TelegramBot.cb_button("English", "cb:lang:en"), TelegramBot.cb_button("Español", "cb:lang:es")],
            [TelegramBot.cb_button("Français", "cb:lang:fr"), TelegramBot.cb_button("中文", "cb:lang:zh")],
            [TelegramBot.cb_button("⬅️ Back", "cb:settings")],
        ])
        await bot.send_message(chat_id, "🌐 <b>Choose Language</b>", reply_markup=kb)
        return
    _set_user_field(user["telegram_id"], "language", lang)
    await bot.send_message(chat_id, f"✅ Language set to {lang}.")


# ---------------------------------------------------------------------------
# Admin handlers
# ---------------------------------------------------------------------------

async def handle_admin(bot: TelegramBot, chat_id: int | str, user: dict) -> None:
    if not (user.get("is_admin") or user.get("is_owner")):
        await bot.send_message(chat_id, "❌ Owner access required.")
        return
    await bot.send_message(chat_id, "👑 <b>Admin Panel</b>", reply_markup=admin_keyboard())


async def handle_broadcast(bot: TelegramBot, chat_id: int | str, user: dict, text: Optional[str] = None) -> None:
    if not (user.get("is_admin") or user.get("is_owner")):
        await bot.send_message(chat_id, "❌ Owner access required.")
        return
    if not text:
        await bot.send_message(chat_id, "Send the broadcast message after /broadcast.")
        return
    users = _load_users()
    sent = 0
    failed = 0
    for u in users:
        try:
            await bot.send_message(u["telegram_id"], f"📢 <b>Broadcast:</b>\n{text}")
            sent += 1
        except Exception:
            failed += 1
    await bot.send_message(chat_id, f"✅ Broadcast sent: {sent} success, {failed} failed.")


# ---------------------------------------------------------------------------
# Inline query handler (search from anywhere)
# ---------------------------------------------------------------------------

async def handle_inline_query(bot: TelegramBot, inline_query_id: str, query: str, user_id: int) -> None:
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
    await bot.answer_inline_query(inline_query_id, results)


# ---------------------------------------------------------------------------
# Update dispatcher
# ---------------------------------------------------------------------------

async def process_update(update: dict) -> None:
    """Route a Telegram update to the appropriate handler."""
    bot = await get_bot()
    if not bot:
        return

    # --- Message ---
    if "message" in update:
        msg = update["message"]
        chat_id = msg["chat"]["id"]
        from_user = msg.get("from", {})
        tg_id = from_user.get("id")
        username = from_user.get("username", "")
        first_name = from_user.get("first_name", "")
        text = msg.get("text", "")
        command = text.split(" ")[0] if text else ""
        args = text[len(command):].strip() if text else ""

        user = _get_or_create_user(tg_id, username, first_name)

        if command == "/start":
            await handle_start(bot, chat_id, user)
        elif command == "/help":
            await handle_help(bot, chat_id, user)
        elif command == "/tier":
            await handle_tier(bot, chat_id, user)
        elif command == "/search":
            await handle_search(bot, chat_id, user, args or None)
        elif command == "/key":
            await handle_keys(bot, chat_id, user)
        elif command == "/createkey" or (command == "/key" and args == "create"):
            await handle_create_key(bot, chat_id, user)
        elif command == "/buy":
            await handle_buy(bot, chat_id, user)
        elif command == "/status":
            await handle_status(bot, chat_id)
        elif command == "/sources":
            await handle_sources(bot, chat_id)
        elif command == "/settings":
            await handle_settings(bot, chat_id, user)
        elif command == "/playlist":
            await handle_playlist(bot, chat_id, user)
        elif command == "/history":
            await handle_history(bot, chat_id, user)
        elif command == "/notify":
            await handle_notify(bot, chat_id, user)
        elif command == "/feedback":
            await handle_feedback(bot, chat_id, user, args or None)
        elif command == "/language":
            await handle_language(bot, chat_id, user, args or None)
        elif command == "/admin":
            await handle_admin(bot, chat_id, user)
        elif command == "/broadcast":
            await handle_broadcast(bot, chat_id, user, args or None)
        elif command in ("/download", "/info", "/lyrics"):
            await bot.send_message(
                chat_id,
                f"🔧 {command} — send a URL or use inline mode.",
                reply_markup=TelegramBot.keyboard([[TelegramBot.cb_button("⬅️ Menu", "cb:menu")]]),
            )
        else:
            # Unknown command — show menu
            await handle_start(bot, chat_id, user)

    # --- Callback query (inline keyboard) ---
    elif "callback_query" in update:
        cb = update["callback_query"]
        cb_id = cb["id"]
        data = cb.get("data", "")
        chat_id = cb["message"]["chat"]["id"]
        message_id = cb["message"]["message_id"]
        from_user = cb.get("from", {})
        tg_id = from_user.get("id")
        user = _get_or_create_user(tg_id, from_user.get("username", ""), from_user.get("first_name", ""))

        await bot.answer_callback_query(cb_id)

        if data == "cb:menu":
            await handle_start(bot, chat_id, user, message_id)
        elif data == "cb:help":
            await handle_help(bot, chat_id, user)
        elif data == "cb:tier":
            await handle_tier(bot, chat_id, user)
        elif data == "cb:keys":
            await handle_keys(bot, chat_id, user)
        elif data == "cb:key:create":
            await handle_create_key(bot, chat_id, user)
        elif data == "cb:buy":
            await handle_buy(bot, chat_id, user)
        elif data == "cb:search":
            await handle_search(bot, chat_id, user, None)
        elif data == "cb:status":
            await handle_status(bot, chat_id)
        elif data == "cb:sources":
            await handle_sources(bot, chat_id)
        elif data == "cb:settings":
            await handle_settings(bot, chat_id, user)
        elif data == "cb:settings:notify":
            await handle_notify(bot, chat_id, user)
        elif data == "cb:settings:lang":
            await handle_language(bot, chat_id, user)
        elif data == "cb:playlist":
            await handle_playlist(bot, chat_id, user)
        elif data == "cb:history":
            await handle_history(bot, chat_id, user)
        elif data == "cb:admin":
            await handle_admin(bot, chat_id, user)
        elif data == "cb:admin:users":
            await bot.send_message(chat_id, "👥 User management via API: GET /v1/users")
        elif data == "cb:admin:stats":
            await bot.send_message(chat_id, "📊 Stats via API: GET /v1/stats/global")
        elif data == "cb:admin:broadcast":
            await bot.send_message(chat_id, "📢 Use /broadcast <message>")
        elif data == "cb:admin:keys":
            await bot.send_message(chat_id, "🔑 All keys via API: GET /v1/web/owner/keys")
        elif data == "cb:admin:system":
            await bot.send_message(chat_id, "⚙️ System status via API: GET /health")
        elif data.startswith("cb:dl:"):
            url = data[5:]
            await handle_search(bot, chat_id, user, f"download {url}")
        elif data.startswith("cb:tier:"):
            tier = data.split(":")[2]
            await bot.send_message(chat_id, f"Tier {tier} — use /buy to upgrade to Pro.")
        elif data.startswith("cb:lang:"):
            lang = data.split(":")[2]
            await handle_language(bot, chat_id, user, lang)
        else:
            await handle_start(bot, chat_id, user, message_id)

    # --- Inline query ---
    elif "inline_query" in update:
        iq = update["inline_query"]
        await handle_inline_query(bot, iq["id"], iq.get("query", ""), iq.get("from", {}).get("id", 0))

    # --- Pre-checkout query (Stars payment) ---
    elif "pre_checkout_query" in update:
        pcq = update["pre_checkout_query"]
        await bot.answer_pre_checkout_query(pcq["id"], ok=True)

    # --- Successful payment ---
    elif "message" in update and update["message"].get("successful_payment"):
        msg = update["message"]
        chat_id = msg["chat"]["id"]
        tg_id = msg["from"]["id"]
        payment = msg["successful_payment"]
        amount = payment.get("total_amount", 0)
        currency = payment.get("currency", "XTR")
        payload_str = payment.get("invoice_payload", "")

        user = _get_or_create_user(tg_id)
        # Upgrade to Pro
        _set_user_field(tg_id, "tier", "pro")
        _set_user_field(tg_id, "stars_balance", user.get("stars_balance", 0) + amount)
        _set_user_field(tg_id, "lifetime_stars", user.get("lifetime_stars", 0) + amount)
        _set_user_field(tg_id, "scopes", ["read", "search", "download"])

        await bot.send_message(
            chat_id,
            f"🎉 <b>Payment Successful!</b>\n\n"
            f"Amount: {amount} {currency}\n"
            f"Tier upgraded to: <b>PRO</b>\n\n"
            f"Your API keys now have Pro limits.\n"
            f"Use /key to view your keys.",
        )

    # --- Chat member (bot added to group) ---
    elif "my_chat_member" in update:
        pass  # Could handle group additions here

    # --- Channel post ---
    elif "channel_post" in update:
        pass


# ---------------------------------------------------------------------------
# Webhook setup / teardown
# ---------------------------------------------------------------------------

async def set_webhook(base_url: str) -> None:
    bot = await get_bot()
    if not bot:
        return
    webhook_url = f"{base_url.rstrip('/')}/v1/telegram/webhook"
    await bot._request("setWebhook", {"url": webhook_url, "allowed_updates": ["message", "callback_query", "inline_query", "pre_checkout_query", "message"]})
    logger.info(f"Telegram webhook set: {webhook_url}")


async def delete_webhook() -> None:
    bot = await get_bot()
    if not bot:
        return
    await bot._request("deleteWebhook", {})
    logger.info("Telegram webhook deleted")


async def set_bot_commands() -> None:
    bot = await get_bot()
    if not bot:
        return
    commands = [
        {"command": "start", "description": "Welcome & main menu"},
        {"command": "help", "description": "Show all commands"},
        {"command": "search", "description": "Search music & media"},
        {"command": "download", "description": "Download a track"},
        {"command": "info", "description": "Get track info"},
        {"command": "lyrics", "description": "Get lyrics"},
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
    """Long-polling entry point (for standalone bot mode)."""
    bot = await get_bot()
    if not bot:
        return
    offset = 0
    logger.info("Telegram bot polling started")
    while True:
        try:
            updates = await bot._request("getUpdates", {"offset": offset, "timeout": 30, "limit": 100})
            for upd in updates:
                offset = upd["update_id"] + 1
                asyncio.create_task(process_update(upd))
        except Exception as exc:
            logger.error(f"Polling error: {exc}")
            await asyncio.sleep(5)