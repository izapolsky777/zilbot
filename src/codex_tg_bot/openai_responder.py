from __future__ import annotations

import json
from typing import Iterable

import aiohttp

from codex_tg_bot.config import Config
from codex_tg_bot.store import Store


class OpenAIResponderError(RuntimeError):
    pass


async def generate_openai_answer(config: Config, store: Store, request_text: str) -> str:
    if not config.openai_api_key:
        raise OpenAIResponderError("OPENAI_API_KEY is not configured.")

    payload = {
        "model": config.openai_chat_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Ты помощник Ивана в Telegram-боте для рабочих задач. "
                    "Отвечай по-русски, кратко и полезно. "
                    "Формат: короткая первая строка, затем нумерованные или маркированные пункты. "
                    "Если речь о задачах, обещаниях или людях, группируй по исполнителям. "
                    "Не выдумывай факты: если в контексте чего-то нет, так и скажи."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Текущий контекст задач и обещаний:\n"
                    f"{_context_from_store(store)}\n\n"
                    "Запрос Ивана:\n"
                    f"{request_text}"
                ),
            },
        ],
        "temperature": 0.2,
    }

    headers = {"Authorization": f"Bearer {config.openai_api_key}", "Content-Type": "application/json"}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.post("https://api.openai.com/v1/chat/completions", json=payload) as response:
            data = await response.json(content_type=None)
            if response.status >= 400:
                detail = data.get("error", {}).get("message") if isinstance(data, dict) else None
                raise OpenAIResponderError(detail or f"OpenAI request failed with HTTP {response.status}")

    try:
        answer = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise OpenAIResponderError("OpenAI response did not contain an answer.") from exc

    return " ".join(answer.split()) if _is_tiny(answer) else answer.strip()


def _context_from_store(store: Store) -> str:
    rows = store.list_open_observations(limit=80)
    if not rows:
        return "Открытых задач и обещаний пока нет."

    assignments = [row for row in rows if row["kind"] == "assignment"]
    promises = [row for row in rows if row["kind"] == "promise"]
    lines: list[str] = []

    if assignments:
        lines.append("Задачи:")
        for assignee, group in _group_by_assignee(assignments):
            lines.append(f"- {assignee}:")
            for row in group:
                due = f" Срок: {row['due_text']}." if row["due_text"] else ""
                lines.append(f"  - #{row['id']} {row['summary']}.{due}")

    if promises:
        lines.append("Обещания:")
        for row in promises:
            actor = row["actor_label"] or row["actor_name"] or "Неизвестно кто"
            due = f" Срок: {row['due_text']}." if row["due_text"] else ""
            lines.append(f"- #{row['id']} {actor}: {row['summary']}.{due}")

    return "\n".join(lines)


def _group_by_assignee(rows: Iterable) -> list[tuple[str, list]]:
    groups: dict[str, list] = {}
    for row in rows:
        assignee = (
            row["target_label_custom"]
            or row["target_text_label_custom"]
            or row["target_label"]
            or (("@" + row["target_username"]) if row["target_username"] else None)
            or row["target_name"]
            or "Исполнитель не распознан"
        )
        groups.setdefault(assignee, []).append(row)
    return sorted(groups.items(), key=lambda item: item[0].lower())


def _is_tiny(text: str) -> bool:
    return len(text) < 140 and "\n" not in text
