"""telegram bot entry. only talks to ro's chat id (configured in keychain)."""

from __future__ import annotations

import asyncio
import logging
import uuid

from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

from api.config import secrets

log = logging.getLogger("ro.telegram")


async def _on_message(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    owner = secrets.get("telegram_owner_id")
    if owner and str(update.effective_chat.id) != owner:
        return
    text = (update.message.text or "").strip()
    if not text:
        return

    from api.supervisor import run_supervisor

    result = await run_supervisor(session_id=uuid.uuid4(), user_text=text)
    await update.message.reply_text(result.get("text", "") or "(empty)")


def main() -> None:
    token = secrets.get("telegram_bot_token")
    if not token:
        log.warning("telegram_bot_token missing, exiting")
        return

    app = ApplicationBuilder().token(token).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _on_message))
    app.run_polling()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
