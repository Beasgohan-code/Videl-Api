# MIT License - Copyright (c) 2026 Videl Network

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from app.config import settings
from app.security import create_api_key, list_api_keys, revoke_api_key


def owner_only(user_id: int | None) -> bool:
    return user_id is not None and user_id == settings.owner_id


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not owner_only(update.effective_user.id if update.effective_user else None):
        await update.message.reply_text("Access denied.")
        return
    await update.message.reply_text(
        "Videl Network music API bot\n\nCommands:\n/start\n/getapi\n/listkey",
    )


async def getapi(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not owner_only(update.effective_user.id if update.effective_user else None):
        await update.message.reply_text("Access denied.")
        return

    api_key = await create_api_key(settings.owner_id)
    await update.message.reply_text(
        f"API Base: {settings.api_base_url}\nAPI Key: {api_key}",
    )


async def listkey(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not owner_only(update.effective_user.id if update.effective_user else None):
        await update.message.reply_text("Access denied.")
        return

    keys = await list_api_keys(settings.owner_id)
    if not keys:
        await update.message.reply_text("No keys found.")
        return

    lines = ["Stored keys:"]
    for item in keys:
        status = "active" if item.get("active", True) else "revoked"
        lines.append(f"- {item['key']} ({status})")
    await update.message.reply_text("\n".join(lines))


async def revoke(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not owner_only(update.effective_user.id if update.effective_user else None):
        await update.message.reply_text("Access denied.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /revoke <api_key>")
        return

    api_key = context.args[0].strip()
    if not api_key:
        await update.message.reply_text("Usage: /revoke <api_key>")
        return

    revoked = await revoke_api_key(settings.owner_id, api_key)
    if revoked:
        await update.message.reply_text("Key revoked.")
        return

    await update.message.reply_text("Key not found.")


def main() -> None:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")
    if settings.owner_id == 0:
        raise RuntimeError("OWNER_ID is required")

    application = Application.builder().token(settings.telegram_bot_token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("getapi", getapi))
    application.add_handler(CommandHandler("listkey", listkey))
    application.add_handler(CommandHandler("revoke", revoke))
    application.run_polling()

if __name__ == "__main__":
    main()
