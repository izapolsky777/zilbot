from __future__ import annotations

import argparse
import asyncio
from typing import List

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from codex_tg_bot.codex_export import export_codex_requests
from codex_tg_bot.config import load_config
from codex_tg_bot.store import Store


def pending_main() -> None:
    config = load_config()
    store = Store(config.database_path)
    try:
        if config.owner_telegram_id is not None:
            store.backfill_codex_requests_from_private_messages(config.owner_telegram_id)
        export_codex_requests(store, config.codex_requests_markdown, config.codex_requests_json)
        rows = store.list_pending_codex_requests(limit=20)
        if not rows:
            print("No pending Telegram requests for Codex.")
            return

        for row in rows:
            sender = row["sender_name"] or str(row["sender_id"])
            print(f"#{row['id']} from {sender} at {row['created_at']}")
            print(row["text"])
            print()
    finally:
        store.close()


def reply_main() -> None:
    parser = argparse.ArgumentParser(description="Send a Codex answer back to Telegram.")
    parser.add_argument("request_id", type=int)
    parser.add_argument("answer", nargs="+")
    args = parser.parse_args()
    answer = " ".join(args.answer).strip()
    asyncio.run(_reply(args.request_id, answer))


def main() -> None:
    parser = argparse.ArgumentParser(description="Telegram bridge commands for Codex.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("pending")
    reply_parser = subparsers.add_parser("reply")
    reply_parser.add_argument("request_id", type=int)
    reply_parser.add_argument("answer", nargs="+")
    args = parser.parse_args()

    if args.command == "pending":
        pending_main()
        return

    answer = " ".join(args.answer).strip()
    asyncio.run(_reply(args.request_id, answer))


async def _reply(request_id: int, answer: str) -> None:
    config = load_config()
    store = Store(config.database_path)
    bot = Bot(config.telegram_bot_token)
    try:
        row = store.get_codex_request(request_id)
        if row is None:
            raise SystemExit(f"Request #{request_id} was not found.")
        if row["status"] != "pending":
            raise SystemExit(f"Request #{request_id} is already {row['status']}.")

        text = f"Ответ Codex по запросу #{request_id}:\n\n{answer}"
        await _send_chunks(bot, row["chat_id"], text, row["message_id"])
        store.mark_codex_request_answered(request_id, answer)
        export_codex_requests(store, config.codex_requests_markdown, config.codex_requests_json)
        print(f"Sent answer for request #{request_id}.")
    finally:
        store.close()
        await bot.session.close()


async def _send_chunks(bot: Bot, chat_id: int, text: str, reply_to_message_id: int) -> None:
    chunks = _chunk_text(text)
    for index, chunk in enumerate(chunks):
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=chunk,
                reply_to_message_id=reply_to_message_id if index == 0 else None,
            )
        except TelegramBadRequest as exc:
            if "message thread not found" not in str(exc):
                raise
            await bot.send_message(chat_id=chat_id, text=chunk)


def _chunk_text(text: str, limit: int = 3900) -> List[str]:
    if len(text) <= limit:
        return [text]

    chunks: List[str] = []
    current = text
    while len(current) > limit:
        split_at = current.rfind("\n\n", 0, limit)
        if split_at < limit // 2:
            split_at = current.rfind("\n", 0, limit)
        if split_at < limit // 2:
            split_at = limit
        chunks.append(current[:split_at].strip())
        current = current[split_at:].strip()
    if current:
        chunks.append(current)
    return chunks


if __name__ == "__main__":
    main()
