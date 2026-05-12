from __future__ import annotations

import argparse

from codex_tg_bot.codex_export import export_codex_inbox
from codex_tg_bot.config import load_config
from codex_tg_bot.extractor import extract_observations
from codex_tg_bot.models import Person
from codex_tg_bot.store import Store


def main() -> None:
    parser = argparse.ArgumentParser(description="Maintenance helpers for the Telegram bot.")
    parser.add_argument("command", choices=["backfill-observations"])
    args = parser.parse_args()

    if args.command == "backfill-observations":
        print(f"Created observations: {backfill_observations()}")


def backfill_observations() -> int:
    config = load_config()
    store = Store(config.database_path)
    created = 0
    try:
        rows = store.conn.execute(
            """
            select
                m.chat_id,
                m.message_id,
                m.sender_id,
                m.text,
                p.display_name,
                p.username,
                p.is_owner
            from messages m
            join people p on p.telegram_id = m.sender_id
            left join observations o
                on o.chat_id = m.chat_id
                and o.message_id = m.message_id
            where o.id is null
            order by m.created_at asc
            """
        ).fetchall()

        for row in rows:
            text = row["text"] or ""
            if _should_skip_backfill_text(text):
                continue

            person = Person(
                telegram_id=row["sender_id"],
                display_name=row["display_name"],
                username=row["username"],
                is_owner=bool(row["is_owner"]),
            )
            observations = extract_observations(text, person, config.owner_telegram_id)
            for observation in observations:
                store.save_observation(row["chat_id"], row["message_id"], observation)
                created += 1

        if created:
            export_codex_inbox(store, config.codex_inbox_markdown, config.codex_inbox_json)
        return created
    finally:
        store.close()


def _should_skip_backfill_text(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    if stripped.startswith("/"):
        return True
    if stripped.startswith(("Ответ Codex", "Ответ ИИ", "Принял запрос", "Принял голосовой запрос")):
        return True
    if stripped.startswith(("http://", "https://")):
        return True
    return False


if __name__ == "__main__":
    main()
