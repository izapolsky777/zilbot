from __future__ import annotations

import asyncio
import logging

from aiogram import Bot

from codex_tg_bot.bridge import _send_chunks
from codex_tg_bot.codex_export import export_codex_requests
from codex_tg_bot.config import load_config
from codex_tg_bot.openai_responder import OpenAIResponderError, generate_openai_answer
from codex_tg_bot.routing import is_project_request
from codex_tg_bot.store import Store


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    asyncio.run(run())


async def run() -> None:
    config = load_config()
    if not config.telegram_bot_token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is required.")
    if not config.openai_api_key:
        raise SystemExit("OPENAI_API_KEY is required.")

    bot = Bot(config.telegram_bot_token)
    try:
        while True:
            await process_pending_once(bot)
            await asyncio.sleep(config.openai_worker_interval_seconds)
    finally:
        await bot.session.close()


async def process_pending_once(bot: Bot) -> int:
    config = load_config()
    store = Store(config.database_path)
    processed = 0
    try:
        rows = store.list_pending_codex_requests(limit=5)
        for row in rows:
            if is_project_request(row["text"]):
                logger.info("Skipping project request %s for Codex bridge", row["id"])
                continue
            try:
                answer = await generate_openai_answer(config, store, row["text"])
            except OpenAIResponderError:
                logger.exception("OpenAI worker failed for request %s", row["id"])
                continue

            text = f"Ответ ИИ по запросу #{row['id']}:\n\n{answer}"
            await _send_chunks(bot, row["chat_id"], text, row["message_id"])
            store.mark_codex_request_answered(row["id"], answer)
            processed += 1

        if processed:
            export_codex_requests(store, config.codex_requests_markdown, config.codex_requests_json)
        return processed
    finally:
        store.close()


if __name__ == "__main__":
    main()
