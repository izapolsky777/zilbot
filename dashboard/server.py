from __future__ import annotations

import json
import os
import re
import sqlite3
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_ROOT = ROOT / "dashboard"
GAME_ROOT = DASHBOARD_ROOT / "game"
METRICS_ROOT = DASHBOARD_ROOT / "metrics"
PORTAL_FILE = DASHBOARD_ROOT / "portal.html"
DATABASE_PATH = ROOT / os.getenv("DATABASE_PATH", "data/bot.sqlite3")
METRICS_SOURCES_PATH = ROOT / os.getenv("METRICS_SOURCES_PATH", "data/metrics_sources.json")
METRICS_CACHE_PATH = ROOT / os.getenv("METRICS_CACHE_PATH", "data/metrics_cache.json")
GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
HOST = os.getenv("DASHBOARD_HOST", "127.0.0.1")
PORT = int(os.getenv("DASHBOARD_PORT", "8765"))
GAME_LEADERBOARD_LIMIT = 20
DEFAULT_METRICS_SOURCES = [
    {
        "name": "Беларусь Supply",
        "spreadsheet_id": "1pMp4W1W4bz1b3QLq-HID-LzlLgm8KsD7S5Kl6fgAW2Q",
        "sheets": [
            {"name": "Актуальный план", "kind": "wide", "range": "A1:AR1003"},
            {"name": "Прогнозы", "kind": "table", "range": "A1:AE1000"},
            {"name": "Контрагенты", "kind": "table", "range": "A1:AC1002"},
            {"name": "Прозвон таксопарков", "kind": "notes", "range": "A1:AA1000"},
        ],
    }
]
MENTION_RE = re.compile(r"(?<!\w)@([A-Za-z0-9_]{3,32})")
DUE_PATTERNS = [
    re.compile(r"\b(сегодня|завтра|послезавтра)\b", re.I),
    re.compile(r"\b(до|к)\s+([0-3]?\d[./-][01]?\d(?:[./-]\d{2,4})?)\b", re.I),
    re.compile(r"\b(до|к)\s+([0-2]?\d:[0-5]\d)\b", re.I),
    re.compile(r"\b(до|к)\s+(понедельника|вторника|среды|четверга|пятницы|субботы|воскресенья)\b", re.I),
]


class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DASHBOARD_ROOT), **kwargs)

    def do_GET(self) -> None:
        self._dispatch_request(head_only=False)

    def do_HEAD(self) -> None:
        self._dispatch_request(head_only=True)

    def _dispatch_request(self, head_only: bool) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/api/inbox", "/dashboard/api/inbox"}:
            self._send_json(load_items(), head_only=head_only)
            return
        if parsed.path == "/game/api/leaderboard":
            self._send_json({"entries": load_game_leaderboard()}, head_only=head_only)
            return
        if parsed.path == "/metrics/api/status":
            self._send_json(load_metrics_status(), head_only=head_only)
            return

        if parsed.path in {"", "/", "/index.html"}:
            self._serve_file(PORTAL_FILE, head_only=head_only)
            return

        if parsed.path == "/dashboard":
            self._redirect("/dashboard/", head_only=head_only)
            return

        if parsed.path == "/game":
            self._redirect("/game/", head_only=head_only)
            return
        if parsed.path == "/metrics":
            self._redirect("/metrics/", head_only=head_only)
            return

        if parsed.path == "/dashboard/":
            self._serve_file(DASHBOARD_ROOT / "index.html", head_only=head_only)
            return

        if parsed.path.startswith("/dashboard/"):
            self._serve_from_root(DASHBOARD_ROOT, parsed.path.removeprefix("/dashboard/"), head_only=head_only)
            return

        if parsed.path == "/game/":
            self._serve_file(GAME_ROOT / "index.html", head_only=head_only)
            return

        if parsed.path.startswith("/game/"):
            self._serve_from_root(GAME_ROOT, parsed.path.removeprefix("/game/"), head_only=head_only)
            return

        if parsed.path == "/metrics/":
            self._serve_file(METRICS_ROOT / "index.html", head_only=head_only)
            return

        if parsed.path.startswith("/metrics/"):
            self._serve_from_root(METRICS_ROOT, parsed.path.removeprefix("/metrics/"), head_only=head_only)
            return

        self.send_error(404, "Page not found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        payload = self._read_json()

        if parsed.path in {"/api/person-label", "/dashboard/api/person-label"}:
            save_person_label(str(payload.get("person_key", "")), str(payload.get("label", "")))
            self._send_json({"ok": True})
            return

        if parsed.path in {"/api/person-aliases", "/dashboard/api/person-aliases"}:
            save_person_aliases(str(payload.get("person_key", "")), str(payload.get("aliases", "")))
            self._send_json({"ok": True})
            return

        if parsed.path in {"/api/item-edit", "/dashboard/api/item-edit"}:
            save_item_edit(
                item_key=str(payload.get("item_key", "")),
                summary=str(payload.get("summary", "")),
                target_label=str(payload.get("target_label", "")),
                due_text=str(payload.get("due_text", "")),
            )
            self._send_json({"ok": True})
            return

        if parsed.path in {"/api/item-archive", "/dashboard/api/item-archive"}:
            archive_item(str(payload.get("item_key", "")))
            self._send_json({"ok": True})
            return

        if parsed.path in {"/api/item-unarchive", "/dashboard/api/item-unarchive"}:
            unarchive_item(str(payload.get("item_key", "")))
            self._send_json({"ok": True})
            return

        if parsed.path in {"/api/item-move", "/dashboard/api/item-move"}:
            move_item(str(payload.get("item_key", "")), str(payload.get("target_label", "")))
            self._send_json({"ok": True})
            return

        if parsed.path == "/game/api/leaderboard":
            name = sanitize_player_name(str(payload.get("name", "")))
            score = parse_score(payload.get("score"))
            source = str(payload.get("source", "")).strip()[:32]
            if name and score > 0:
                save_game_score(name=name, score=score, source=source)
            self._send_json({"ok": True, "entries": load_game_leaderboard()})
            return

        self.send_error(404, "API endpoint not found")

    def _redirect(self, location: str, head_only: bool = False) -> None:
        self.send_response(302)
        self.send_header("Location", location)
        self.end_headers()

    def _serve_from_root(self, root: Path, relative_path: str, head_only: bool = False) -> None:
        clean = unquote(relative_path).lstrip("/")
        target = (root / clean).resolve()
        root_resolved = root.resolve()
        if root_resolved not in {target, *target.parents}:
            self.send_error(403, "Forbidden")
            return
        if target.is_dir():
            target = target / "index.html"
        self._serve_file(target, head_only=head_only)

    def _serve_file(self, path: Path, head_only: bool = False) -> None:
        if not path.exists() or not path.is_file():
            self.send_error(404, "File not found")
            return

        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", f"{self.guess_type(str(path))}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _send_json(self, payload: dict, head_only: bool = False) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if not head_only:
            self.wfile.write(body)


def load_items(limit: int = 100) -> dict:
    if not DATABASE_PATH.exists():
        return {"open_items": [], "archived_items": [], "people": []}

    with connect() as conn:
        rows = conn.execute(
            """
            select
                o.id,
                o.kind,
                o.summary,
                o.evidence,
                o.due_text,
                o.created_at,
                c.title as chat_title,
                c.telegram_id as chat_telegram_id,
                p.telegram_id as actor_telegram_id,
                p.display_name as actor_name,
                p.username as actor_username,
                p.is_owner as actor_is_owner,
                tp.telegram_id as target_telegram_id,
                tp.display_name as target_name,
                tp.username as target_username,
                tp.is_owner as target_is_owner,
                o.target_label
            from observations o
            join chats c on c.telegram_id = o.chat_id
            join people p on p.telegram_id = o.actor_id
            left join people tp on tp.telegram_id = o.target_id
            where o.status = 'open'
            order by o.created_at desc
            limit ?
            """,
            (limit,),
        ).fetchall()
        labels = load_labels(conn)
        aliases = load_aliases(conn)
        people = load_people(conn)
        edits = load_edits(conn)
        states = load_states(conn)

    items = []
    for row in rows:
        for item in expand_row(row, labels, aliases, people, edits, states):
            items.append(item)

    open_items = [item for item in items if not item["archived_at"]]
    archived_items = [item for item in items if item["archived_at"]]
    return {
        "open_items": open_items,
        "archived_items": archived_items,
        "people": people_from_items(items, aliases),
    }


def load_metrics_status() -> dict:
    sources = load_metrics_sources()
    service_account_path = ROOT / GOOGLE_SERVICE_ACCOUNT_FILE if GOOGLE_SERVICE_ACCOUNT_FILE else None
    return {
        "sources": sources,
        "sources_path": str(METRICS_SOURCES_PATH),
        "sources_file_exists": METRICS_SOURCES_PATH.exists(),
        "cache_path": str(METRICS_CACHE_PATH),
        "cache_file_exists": METRICS_CACHE_PATH.exists(),
        "cache_file_age_seconds": cache_file_age_seconds(METRICS_CACHE_PATH),
        "service_account_configured": bool(GOOGLE_SERVICE_ACCOUNT_FILE),
        "service_account_file_exists": bool(service_account_path and service_account_path.exists()),
        "cache_ttl_seconds": int(os.getenv("METRICS_CACHE_TTL_SECONDS", "300").strip() or "300"),
        "chart_dir": str(ROOT / os.getenv("METRICS_CHART_DIR", "data/metric_charts")),
    }


def load_metrics_sources() -> list[dict[str, Any]]:
    if not METRICS_SOURCES_PATH.exists():
        return DEFAULT_METRICS_SOURCES
    try:
        data = json.loads(METRICS_SOURCES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return DEFAULT_METRICS_SOURCES
    if isinstance(data, dict):
        data = data.get("sources", [])
    return data if isinstance(data, list) and data else DEFAULT_METRICS_SOURCES


def cache_file_age_seconds(path: Path) -> int | None:
    if not path.exists():
        return None
    return round(__import__("time").time() - path.stat().st_mtime)


def load_game_leaderboard(limit: int = GAME_LEADERBOARD_LIMIT) -> list[dict[str, Any]]:
    if not DATABASE_PATH.exists():
        return []

    with connect() as conn:
        rows = conn.execute(
            """
            select name, score, created_at
            from game_leaderboard_entries
            order by score desc, created_at asc, id asc
            limit ?
            """,
            (limit,),
        ).fetchall()

    return [
        {
            "name": row["name"],
            "score": int(row["score"]),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def save_game_score(name: str, score: int, source: str = "") -> None:
    clean_name = sanitize_player_name(name)
    if not clean_name or score <= 0:
        return

    with connect() as conn:
        conn.execute(
            """
            insert into game_leaderboard_entries (name, score, source)
            values (?, ?, ?)
            """,
            (clean_name, int(score), source),
        )
        conn.execute(
            """
            delete from game_leaderboard_entries
            where id not in (
                select id
                from game_leaderboard_entries
                order by score desc, created_at asc, id asc
                limit 200
            )
            """
        )
        conn.commit()


def expand_row(
    row: sqlite3.Row,
    labels: dict[str, str],
    aliases: dict[str, list[str]],
    people: dict[str, dict[str, Any]],
    edits: dict[str, sqlite3.Row],
    states: dict[str, sqlite3.Row],
) -> list[dict[str, Any]]:
    base = row_to_dict(row)
    parts = split_assignment(base) if base["kind"] == "assignment" else [(0, base.get("target_label"), base["summary"])]

    items = []
    for index, target_label, summary in parts:
        item_key = f"{base['id']}:{index}"
        edit = edits.get(item_key)
        state = states.get(item_key)
        edited_summary = clean_optional(edit["summary"] if edit else None) or summary
        edited_target = (
            clean_optional(edit["target_label"] if edit else None)
            or target_label
            or infer_target_label(base, summary, people, labels, aliases)
        )
        edited_due = clean_optional(edit["due_text"] if edit else None) or base.get("due_text") or extract_due_text(edited_summary)
        original_person_key = label_person_key(edited_target)
        person_key = person_key_for(base, edited_target, people, labels, aliases)
        resolved_person = people.get(person_key, {})
        person_label = labels.get(person_key, "") or labels.get(original_person_key, "")
        person_aliases = aliases.get(person_key, [])
        if original_person_key != person_key:
            person_aliases = [*person_aliases, *aliases.get(original_person_key, [])]

        item = {
            **base,
            "id": item_key,
            "observation_id": base["id"],
            "split_index": index,
            "summary": edited_summary,
            "points": task_points(edited_summary),
            "target_label": edited_target,
            "assignee_key": person_key if base["kind"] == "assignment" else "",
            "assignee_name": person_label or resolved_person.get("display_name") or edited_target or base.get("target_name") or "Без исполнителя",
            "assignee_raw": person_raw_name(resolved_person) or edited_target or base.get("target_name") or "",
            "person_label": person_label,
            "person_aliases": ", ".join(unique_values(person_aliases)),
            "due_text": edited_due,
            "actor_key": f"tg:{base['actor_telegram_id']}",
            "actor_label": labels.get(f"tg:{base['actor_telegram_id']}", ""),
            "actor_aliases": ", ".join(aliases.get(f"tg:{base['actor_telegram_id']}", [])),
            "archived_at": state["archived_at"] if state else None,
        }
        items.append(item)

    return items


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "kind": row["kind"],
        "summary": row["summary"],
        "evidence": row["evidence"],
        "due_text": row["due_text"],
        "created_at": row["created_at"],
        "chat_title": row["chat_title"],
        "chat_telegram_id": row["chat_telegram_id"],
        "actor_telegram_id": row["actor_telegram_id"],
        "actor_name": row["actor_name"],
        "actor_username": row["actor_username"],
        "actor_is_owner": bool(row["actor_is_owner"]),
        "target_telegram_id": row["target_telegram_id"],
        "target_name": row["target_name"],
        "target_username": row["target_username"],
        "target_is_owner": bool(row["target_is_owner"]) if row["target_is_owner"] is not None else None,
        "target_label": row["target_label"],
    }


def split_assignment(item: dict[str, Any]) -> list[tuple[int, str | None, str]]:
    if item.get("target_label") or item.get("target_name"):
        return [(0, item.get("target_label") or item.get("target_name"), item["summary"])]

    matches = list(MENTION_RE.finditer(item["summary"]))
    if len(matches) <= 1:
        return [(0, matches[0].group(0) if matches else None, clean_task_text(item["summary"]))]

    parts = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(item["summary"])
        text = clean_task_text(item["summary"][match.end() : end])
        if text:
            parts.append((index, match.group(0), text))

    return parts or [(0, None, item["summary"])]


def clean_task_text(text: str) -> str:
    cleaned = text.strip(" ,.;:-")
    cleaned = re.sub(r"^(а\s+ты|ты|тебя|прошу\s+тебя|прошу|пожалуйста)\s+", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def person_key_for(
    item: dict[str, Any],
    target_label: str | None,
    people: dict[str, dict[str, Any]],
    labels: dict[str, str],
    aliases: dict[str, list[str]],
) -> str:
    if item.get("target_telegram_id"):
        return f"tg:{item['target_telegram_id']}"
    if target_label:
        return resolve_person_key(target_label, people, labels, aliases) or f"label:{target_label.lower()}"
    return "unassigned"


def resolve_person_key(
    label: str,
    people: dict[str, dict[str, Any]],
    labels: dict[str, str],
    aliases: dict[str, list[str]],
) -> str | None:
    raw = str(label or "").strip()
    if not raw:
        return None

    username = raw[1:].lower() if raw.startswith("@") else ""
    best_key = ""
    best_score = 0

    if username:
        for key, person in people.items():
            candidate = str(person.get("username") or "").lower()
            if candidate and candidate == username:
                return key

    for key in people:
        score = person_match_score(raw, person_search_values(key, people, labels, aliases))
        if score > best_score:
            best_key = key
            best_score = score

    return best_key if best_score >= 72 else None


def infer_target_label(
    item: dict[str, Any],
    summary: str,
    people: dict[str, dict[str, Any]],
    labels: dict[str, str],
    aliases: dict[str, list[str]],
) -> str | None:
    if item.get("kind") != "assignment":
        return None

    text = " ".join(
        part
        for part in [
            item.get("target_name"),
            item.get("target_username"),
            summary,
            item.get("evidence"),
        ]
        if part
    )
    if not text:
        return None

    best_label = ""
    best_score = 0
    for key, person in people.items():
        for value in person_search_values(key, people, labels, aliases):
            if not value or len(compact_person_text(value)) < 4:
                continue
            score = text_contains_person_score(text, value)
            if score > best_score:
                best_label = labels.get(key) or person_raw_name(person) or value
                best_score = score

    return best_label if best_score >= 78 else None


def person_search_values(
    person_key: str,
    people: dict[str, dict[str, Any]],
    labels: dict[str, str],
    aliases: dict[str, list[str]],
) -> list[str]:
    person = people.get(person_key, {})
    username = str(person.get("username") or "").strip()
    values = [
        str(person.get("display_name") or ""),
        username,
        f"@{username}" if username else "",
        labels.get(person_key, ""),
        *aliases.get(person_key, []),
    ]
    return unique_values(values)


def person_match_score(source: str, candidates: list[str]) -> int:
    normalized_source = normalize_person_alias(source)
    compact_source = compact_person_text(source)
    source_tokens = normalized_source.split()
    best = 0

    for candidate in candidates:
        normalized_candidate = normalize_person_alias(candidate)
        compact_candidate = compact_person_text(candidate)
        if not normalized_candidate or not compact_candidate:
            continue
        if normalized_source == normalized_candidate or compact_source == compact_candidate:
            best = max(best, 100)
        if len(compact_source) >= 5 and len(compact_candidate) >= 5:
            if compact_source in compact_candidate or compact_candidate in compact_source:
                best = max(best, 88)
            distance = levenshtein(compact_source, compact_candidate)
            threshold = max(2, round(max(len(compact_source), len(compact_candidate)) * 0.24))
            if distance <= threshold:
                best = max(best, 84 - distance)

        candidate_tokens = normalized_candidate.split()
        matched_tokens = sum(
            1
            for source_token in source_tokens
            if any(words_match(source_token, candidate_token) for candidate_token in candidate_tokens)
        )
        if matched_tokens >= 2:
            best = max(best, 82 + min(matched_tokens, 3))

    return best


def text_contains_person_score(text: str, person_value: str) -> int:
    normalized_text = normalize_person_alias(text)
    normalized_value = normalize_person_alias(person_value)
    if not normalized_text or not normalized_value:
        return 0

    compact_text = compact_person_text(text)
    compact_value = compact_person_text(person_value)
    if len(compact_value) >= 5 and compact_value in compact_text:
        return 100
    if re.search(rf"(?<!\w){re.escape(normalized_value)}(?!\w)", normalized_text):
        return 100

    text_tokens = normalized_text.split()
    value_tokens = normalized_value.split()
    if len(value_tokens) == 1:
        token = value_tokens[0]
        return 86 if len(token) >= 5 and any(words_match(token, text_token) for text_token in text_tokens) else 0

    best_run = 0
    for index in range(0, max(1, len(text_tokens) - len(value_tokens) + 1)):
        window = text_tokens[index : index + len(value_tokens)]
        matched = sum(
            1
            for value_token in value_tokens
            if any(words_match(value_token, text_token) for text_token in window)
        )
        best_run = max(best_run, matched)

    return 82 + best_run if best_run >= min(2, len(value_tokens)) else 0


def label_person_key(label: str | None) -> str:
    if label:
        return f"label:{label.lower()}"
    return "unassigned"


def person_raw_name(person: dict[str, Any]) -> str:
    username = person.get("username")
    if username:
        return f"@{username}"
    return str(person.get("display_name") or "")


def compact_person_text(value: str) -> str:
    text = normalize_person_alias(value)
    text = text.replace("iy", "y")
    return re.sub(r"[^0-9a-zа-я_]+", "", text)


def words_match(left: str, right: str) -> bool:
    if left == right:
        return True
    if len(left) < 4 or len(right) < 4:
        return False
    if left.startswith(right) or right.startswith(left):
        return True
    distance = levenshtein(left, right)
    threshold = 1 if max(len(left), len(right)) <= 6 else 2
    return distance <= threshold


def levenshtein(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, start=1):
        current = [i]
        for j, right_char in enumerate(right, start=1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[-1]


def unique_values(values: list[str]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        clean = str(value or "").strip()
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            result.append(clean)
    return result


def people_from_items(items: list[dict[str, Any]], aliases: dict[str, list[str]]) -> list[dict[str, str]]:
    people: dict[str, dict[str, str]] = {}
    for item in items:
        if item["kind"] == "assignment" and item["assignee_key"] and item["assignee_key"] != "unassigned":
            people[item["assignee_key"]] = {
                "person_key": item["assignee_key"],
                "raw_name": item["assignee_raw"] or item["assignee_name"],
                "label": item["person_label"],
                "aliases": ", ".join(aliases.get(item["assignee_key"], [])),
            }
        actor_key = item.get("actor_key")
        if actor_key:
            raw = "@" + item["actor_username"] if item.get("actor_username") else item.get("actor_name") or actor_key
            people[actor_key] = {
                "person_key": actor_key,
                "raw_name": raw,
                "label": item.get("actor_label", ""),
                "aliases": ", ".join(aliases.get(actor_key, [])),
            }
    return sorted(people.values(), key=lambda person: person["raw_name"].lower())


def task_points(text: str) -> list[str]:
    chunks = re.split(r"(?:\n+|(?:^|\s)(?:\d+[.)]|[-*])\s+)", text)
    points = [clean_task_text(chunk) for chunk in chunks if clean_task_text(chunk)]
    if len(points) > 1:
        return points
    return [text]


def extract_due_text(text: str) -> str:
    for pattern in DUE_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(0)
    return ""


def save_person_label(person_key: str, label: str) -> None:
    if not person_key:
        return
    with connect() as conn:
        conn.execute(
            """
            insert into dashboard_person_labels (person_key, label, updated_at)
            values (?, ?, current_timestamp)
            on conflict(person_key) do update set
                label = excluded.label,
                updated_at = current_timestamp
            """,
            (person_key, label.strip()),
        )
        conn.commit()


def save_person_aliases(person_key: str, aliases: str) -> None:
    if not person_key:
        return

    values = []
    seen = set()
    for alias in re.split(r"[,;\n]+", aliases):
        clean = alias.strip()
        norm = normalize_person_alias(clean)
        if not clean or not norm or norm in seen:
            continue
        seen.add(norm)
        values.append((norm, person_key, clean))

    with connect() as conn:
        conn.execute("delete from person_aliases where person_key = ?", (person_key,))
        conn.executemany(
            """
            insert into person_aliases (alias_norm, person_key, alias)
            values (?, ?, ?)
            on conflict(alias_norm) do update set
                person_key = excluded.person_key,
                alias = excluded.alias
            """,
            values,
        )
        conn.commit()


def save_item_edit(item_key: str, summary: str, target_label: str, due_text: str) -> None:
    if not item_key:
        return
    with connect() as conn:
        conn.execute(
            """
            insert into dashboard_item_edits (item_key, summary, target_label, due_text, updated_at)
            values (?, ?, ?, ?, current_timestamp)
            on conflict(item_key) do update set
                summary = excluded.summary,
                target_label = excluded.target_label,
                due_text = excluded.due_text,
                updated_at = current_timestamp
            """,
            (item_key, summary.strip(), target_label.strip(), due_text.strip()),
        )
        conn.commit()


def archive_item(item_key: str) -> None:
    if not item_key:
        return
    with connect() as conn:
        conn.execute(
            """
            insert into dashboard_item_state (item_key, archived_at, updated_at)
            values (?, current_timestamp, current_timestamp)
            on conflict(item_key) do update set
                archived_at = current_timestamp,
                updated_at = current_timestamp
            """,
            (item_key,),
        )
        conn.commit()


def unarchive_item(item_key: str) -> None:
    if not item_key:
        return
    with connect() as conn:
        conn.execute(
            """
            insert into dashboard_item_state (item_key, archived_at, updated_at)
            values (?, null, current_timestamp)
            on conflict(item_key) do update set
                archived_at = null,
                updated_at = current_timestamp
            """,
            (item_key,),
        )
        conn.commit()


def move_item(item_key: str, target_label: str) -> None:
    if not item_key:
        return
    with connect() as conn:
        conn.execute(
            """
            insert into dashboard_item_edits (item_key, summary, target_label, due_text, updated_at)
            values (?, '', ?, '', current_timestamp)
            on conflict(item_key) do update set
                target_label = excluded.target_label,
                updated_at = current_timestamp
            """,
            (item_key, target_label.strip()),
        )
        conn.commit()


def load_labels(conn: sqlite3.Connection) -> dict[str, str]:
    return {
        row["person_key"]: row["label"]
        for row in conn.execute("select person_key, label from dashboard_person_labels")
    }


def load_aliases(conn: sqlite3.Connection) -> dict[str, list[str]]:
    aliases: dict[str, list[str]] = {}
    for row in conn.execute("select person_key, alias from person_aliases order by alias"):
        aliases.setdefault(row["person_key"], []).append(row["alias"])
    return aliases


def load_people(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    return {
        f"tg:{row['telegram_id']}": {
            "telegram_id": row["telegram_id"],
            "display_name": row["display_name"],
            "username": row["username"],
            "is_owner": bool(row["is_owner"]),
        }
        for row in conn.execute("select telegram_id, display_name, username, is_owner from people")
    }


def load_edits(conn: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    return {
        row["item_key"]: row
        for row in conn.execute("select item_key, summary, target_label, due_text from dashboard_item_edits")
    }


def load_states(conn: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    return {
        row["item_key"]: row
        for row in conn.execute("select item_key, archived_at from dashboard_item_state")
    }


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    ensure_dashboard_tables(conn)
    return conn


def ensure_dashboard_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        create table if not exists dashboard_person_labels (
            person_key text primary key,
            label text not null default '',
            updated_at text not null default current_timestamp
        );

        create table if not exists dashboard_item_edits (
            item_key text primary key,
            summary text not null default '',
            target_label text not null default '',
            due_text text not null default '',
            updated_at text not null default current_timestamp
        );

        create table if not exists person_aliases (
            alias_norm text primary key,
            person_key text not null,
            alias text not null,
            created_at text not null default current_timestamp
        );

        create table if not exists dashboard_item_state (
            item_key text primary key,
            archived_at text,
            updated_at text not null default current_timestamp
        );

        create table if not exists game_leaderboard_entries (
            id integer primary key autoincrement,
            name text not null,
            score integer not null,
            source text not null default '',
            created_at text not null default current_timestamp
        );
        """
    )
    ensure_column(conn, "observations", "target_label", "text")
    ensure_column(conn, "observations", "due_text", "text")
    conn.commit()


def ensure_column(conn: sqlite3.Connection, table: str, column: str, declaration: str) -> None:
    columns = {row["name"] for row in conn.execute(f"pragma table_info({table})")}
    if column not in columns:
        conn.execute(f"alter table {table} add column {column} {declaration}")


def clean_optional(value: Any) -> str:
    return str(value or "").strip()


def normalize_person_alias(value: str) -> str:
    text = str(value or "").strip().lower().replace("ё", "е")
    if text.startswith("@"):
        text = text[1:]
    text = re.sub(r"[^0-9a-zа-я_ -]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    words = [normalize_name_word(word) for word in text.split()]
    return " ".join(word for word in words if word)


def normalize_name_word(word: str) -> str:
    for suffix in ("ому", "ему", "ыми", "ими", "ого", "его", "ой", "ый", "ий", "ая", "яя"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[: -len(suffix)]
    if len(word) > 3 and word[-1] in {"а", "у", "ю", "е", "ы", "и"}:
        return word[:-1]
    return word


def sanitize_player_name(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    return text[:18] or "Боец"


def parse_score(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def main() -> None:
    with connect():
        pass
    server = ThreadingHTTPServer((HOST, PORT), DashboardHandler)
    print(f"Dashboard: http://{HOST}:{PORT}/")
    server.serve_forever()


if __name__ == "__main__":
    main()
