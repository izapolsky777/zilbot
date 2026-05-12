from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from codex_tg_bot.store import Store


def export_codex_inbox(store: Store, markdown_path: Path, json_path: Path) -> None:
    payload = store.digest_payload(limit=50)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)

    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    markdown_path.write_text(_render_markdown(payload), encoding="utf-8")


def export_codex_requests(store: Store, markdown_path: Path, json_path: Path) -> None:
    rows = store.list_pending_codex_requests(limit=20)
    payload = {
        "pending_requests": [
            {
                "id": row["id"],
                "chat_id": row["chat_id"],
                "message_id": row["message_id"],
                "sender_id": row["sender_id"],
                "sender_name": row["sender_name"],
                "text": row["text"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]
    }

    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(_render_requests_markdown(payload), encoding="utf-8")


def _render_markdown(payload: Dict) -> str:
    items = payload.get("open_items", [])
    lines = ["# Codex Telegram Inbox", ""]

    if not items:
        lines.append("No open work-chat observations yet.")
        return "\n".join(lines) + "\n"

    for item in items:
        kind = "Promise" if item["kind"] == "promise" else "Assignment"
        actor = item["actor_name"] or str(item["chat_telegram_id"])
        target_name = item.get("target_name") or item.get("target_label")
        target = f" -> {target_name}" if target_name else ""
        lines.extend(
            [
                f"## #{item['id']} {kind}: {actor}{target}",
                "",
                f"- Chat: {item['chat_title']}",
                f"- Created: {item['created_at']}",
                f"- Assignee: {target_name or 'unknown'}" if item["kind"] == "assignment" else f"- Promised by: {actor}",
                f"- Due: {item['due_text'] or 'not specified'}",
                f"- Summary: {item['summary']}",
                f"- Evidence: {item['evidence']}",
                "",
            ]
        )

    return "\n".join(lines)


def _render_requests_markdown(payload: Dict) -> str:
    requests = payload.get("pending_requests", [])
    lines = ["# Codex Telegram Requests", ""]

    if not requests:
        lines.append("No pending Telegram requests for Codex.")
        return "\n".join(lines) + "\n"

    for request in requests:
        sender = request.get("sender_name") or str(request["sender_id"])
        lines.extend(
            [
                f"## Request #{request['id']} from {sender}",
                "",
                f"- Created: {request['created_at']}",
                f"- Reply command: `codex-tg-reply {request['id']} \"...answer...\"`",
                "",
                request["text"],
                "",
            ]
        )

    return "\n".join(lines)
