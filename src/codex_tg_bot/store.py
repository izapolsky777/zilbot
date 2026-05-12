from __future__ import annotations

import sqlite3
from pathlib import Path
import re
from dataclasses import replace
from typing import Any, Dict, List, Optional

from codex_tg_bot.models import Chat, Observation, Person


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self._migrate()

    def close(self) -> None:
        self.conn.close()

    def upsert_person(self, person: Person) -> None:
        self.conn.execute(
            """
            insert into people (telegram_id, display_name, username, is_owner)
            values (?, ?, ?, ?)
            on conflict(telegram_id) do update set
                display_name = excluded.display_name,
                username = excluded.username,
                is_owner = excluded.is_owner
            """,
            (person.telegram_id, person.display_name, person.username, int(person.is_owner)),
        )
        self.conn.commit()

    def upsert_chat(self, chat: Chat) -> None:
        self.conn.execute(
            """
            insert into chats (telegram_id, title, type)
            values (?, ?, ?)
            on conflict(telegram_id) do update set
                title = excluded.title,
                type = excluded.type
            """,
            (chat.telegram_id, chat.title, chat.type),
        )
        self.conn.commit()

    def save_message(self, chat_id: int, message_id: int, sender_id: int, text: str) -> None:
        self.conn.execute(
            """
            insert or ignore into messages (chat_id, message_id, sender_id, text)
            values (?, ?, ?, ?)
            """,
            (chat_id, message_id, sender_id, text),
        )
        self.conn.commit()

    def save_observation(self, chat_id: int, message_id: int, observation: Observation) -> int:
        observation = self.resolve_observation_target(observation)
        cursor = self.conn.execute(
            """
            insert into observations (
                chat_id, message_id, kind, actor_id, target_id, target_label, summary, evidence, confidence, due_text
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chat_id,
                message_id,
                observation.kind,
                observation.actor_id,
                observation.target_id,
                observation.target_label,
                observation.summary,
                observation.evidence,
                observation.confidence,
                observation.due_text,
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def resolve_observation_target(self, observation: Observation) -> Observation:
        if observation.kind != "assignment" or not observation.target_label or observation.target_id:
            return observation

        match = self.resolve_person_reference(observation.target_label)
        if not match:
            return observation

        target_id = match["telegram_id"]
        target_label = match["canonical_label"]
        return replace(observation, target_id=target_id, target_label=target_label)

    def resolve_person_reference(self, value: str) -> Optional[Dict[str, Any]]:
        normalized = normalize_person_alias(value)
        if not normalized:
            return None
        normalized_compact = _compact_alias(normalized)

        candidates = self._person_candidates()
        for candidate in candidates:
            aliases = candidate["aliases"]
            compact_aliases = {_compact_alias(alias) for alias in aliases}
            if candidate["telegram_id"] and (normalized in aliases or normalized_compact in compact_aliases):
                return candidate

        best_candidate = None
        best_score = 0
        for candidate in candidates:
            if not candidate["telegram_id"]:
                continue
            aliases = candidate["aliases"]
            compact_aliases = {_compact_alias(alias) for alias in aliases}
            if any(normalized in alias or alias in normalized for alias in aliases if len(alias) >= 5):
                best_candidate = candidate
                best_score = max(best_score, 88)
            if any(
                normalized_compact in alias or alias in normalized_compact
                for alias in compact_aliases
                if len(alias) >= 5
            ):
                best_candidate = candidate
                best_score = max(best_score, 88)
            score = max(_alias_match_score(normalized, alias) for alias in aliases) if aliases else 0
            if score > best_score:
                best_candidate = candidate
                best_score = score

        return best_candidate if best_score >= 72 else None

    def _person_candidates(self) -> List[Dict[str, Any]]:
        candidates: Dict[str, Dict[str, Any]] = {}

        for row in self.conn.execute("select telegram_id, display_name, username from people"):
            person_key = f"tg:{row['telegram_id']}"
            raw = "@" + row["username"] if row["username"] else row["display_name"]
            candidates[person_key] = {
                "person_key": person_key,
                "telegram_id": row["telegram_id"],
                "canonical_label": raw,
                "aliases": {
                    normalize_person_alias(row["display_name"]),
                    normalize_person_alias(row["username"] or ""),
                    normalize_person_alias(raw),
                },
            }

        for row in self.conn.execute("select person_key, label from dashboard_person_labels"):
            person_key = row["person_key"]
            candidate = candidates.setdefault(
                person_key,
                {
                    "person_key": person_key,
                    "telegram_id": _telegram_id_from_person_key(person_key),
                    "canonical_label": _label_from_person_key(person_key),
                    "aliases": set(),
                },
            )
            candidate["aliases"].add(normalize_person_alias(row["label"]))
            candidate["aliases"].add(normalize_person_alias(_label_from_person_key(person_key)))

        for row in self.conn.execute("select person_key, alias from person_aliases"):
            person_key = row["person_key"]
            candidate = candidates.setdefault(
                person_key,
                {
                    "person_key": person_key,
                    "telegram_id": _telegram_id_from_person_key(person_key),
                    "canonical_label": _label_from_person_key(person_key),
                    "aliases": set(),
                },
            )
            candidate["aliases"].add(normalize_person_alias(row["alias"]))

        clean = []
        for candidate in candidates.values():
            candidate["aliases"] = {alias for alias in candidate["aliases"] if alias}
            clean.append(candidate)
        return clean

    def list_open_observations(self, limit: int = 20) -> List[sqlite3.Row]:
        return list(
            self.conn.execute(
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
                    o.target_label,
                    apl.label as actor_label,
                    tpl.label as target_label_custom,
                    tlpl.label as target_text_label_custom
                from observations o
                join chats c on c.telegram_id = o.chat_id
                join people p on p.telegram_id = o.actor_id
                left join people tp on tp.telegram_id = o.target_id
                left join dashboard_person_labels apl on apl.person_key = 'tg:' || p.telegram_id
                left join dashboard_person_labels tpl on tpl.person_key = 'tg:' || tp.telegram_id
                left join dashboard_person_labels tlpl on tlpl.person_key = 'label:' || lower(o.target_label)
                where o.status = 'open'
                order by o.created_at desc
                limit ?
                """,
                (limit,),
            )
        )

    def list_open_assignments_for_person(self, telegram_id: int, limit: int = 20) -> List[sqlite3.Row]:
        return list(
            self.conn.execute(
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
                    o.target_label,
                    apl.label as actor_label,
                    tpl.label as target_label_custom,
                    tlpl.label as target_text_label_custom
                from observations o
                join chats c on c.telegram_id = o.chat_id
                join people p on p.telegram_id = o.actor_id
                left join people tp on tp.telegram_id = o.target_id
                left join dashboard_person_labels apl on apl.person_key = 'tg:' || p.telegram_id
                left join dashboard_person_labels tpl on tpl.person_key = 'tg:' || tp.telegram_id
                left join dashboard_person_labels tlpl on tlpl.person_key = 'label:' || lower(o.target_label)
                where o.status = 'open'
                    and o.kind = 'assignment'
                    and o.target_id = ?
                order by o.created_at desc
                limit ?
                """,
                (telegram_id, limit),
            )
        )

    def get_observation(self, observation_id: int) -> Optional[sqlite3.Row]:
        row = self.conn.execute(
            """
            select o.*, c.title as chat_title
            from observations o
            join chats c on c.telegram_id = o.chat_id
            where o.id = ?
            """,
            (observation_id,),
        ).fetchone()
        return row

    def mark_reminded(self, observation_id: int) -> None:
        self.conn.execute(
            "update observations set last_reminded_at = current_timestamp where id = ?",
            (observation_id,),
        )
        self.conn.commit()

    def create_codex_request(self, chat_id: int, message_id: int, sender_id: int, text: str) -> int:
        cursor = self.conn.execute(
            """
            insert into codex_requests (chat_id, message_id, sender_id, text)
            values (?, ?, ?, ?)
            """,
            (chat_id, message_id, sender_id, text),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def backfill_codex_requests_from_private_messages(self, owner_telegram_id: int) -> int:
        rows = list(
            self.conn.execute(
                """
                select m.chat_id, m.message_id, m.sender_id, m.text
                from messages m
                left join codex_requests r
                    on r.chat_id = m.chat_id
                    and r.message_id = m.message_id
                left join observations o
                    on o.chat_id = m.chat_id
                    and o.message_id = m.message_id
                where m.chat_id = ?
                    and m.sender_id = ?
                    and m.text not like '/%'
                    and r.id is null
                    and o.id is null
                order by m.created_at asc
                """,
                (owner_telegram_id, owner_telegram_id),
            )
        )

        for row in rows:
            self.conn.execute(
                """
                insert into codex_requests (chat_id, message_id, sender_id, text)
                values (?, ?, ?, ?)
                """,
                (row["chat_id"], row["message_id"], row["sender_id"], row["text"]),
            )
        self.conn.commit()
        return len(rows)

    def list_pending_codex_requests(self, limit: int = 10) -> List[sqlite3.Row]:
        return list(
            self.conn.execute(
                """
                select
                    r.id,
                    r.chat_id,
                    r.message_id,
                    r.sender_id,
                    r.text,
                    r.created_at,
                    p.display_name as sender_name
                from codex_requests r
                left join people p on p.telegram_id = r.sender_id
                where r.status = 'pending'
                order by r.created_at asc
                limit ?
                """,
                (limit,),
            )
        )

    def get_codex_request(self, request_id: int) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            """
            select
                r.id,
                r.chat_id,
                r.message_id,
                r.sender_id,
                r.text,
                r.status,
                r.created_at,
                p.display_name as sender_name
            from codex_requests r
            left join people p on p.telegram_id = r.sender_id
            where r.id = ?
            """,
            (request_id,),
        ).fetchone()

    def mark_codex_request_answered(self, request_id: int, answer: str) -> None:
        self.conn.execute(
            """
            update codex_requests
            set status = 'answered',
                answer = ?,
                answered_at = current_timestamp
            where id = ?
            """,
            (answer, request_id),
        )
        self.conn.commit()

    def has_scheduled_digest_been_sent(self, digest_key: str) -> bool:
        row = self.conn.execute(
            "select 1 from scheduled_digests where digest_key = ?",
            (digest_key,),
        ).fetchone()
        return row is not None

    def mark_scheduled_digest_sent(self, digest_key: str) -> None:
        self.conn.execute(
            """
            insert or ignore into scheduled_digests (digest_key)
            values (?)
            """,
            (digest_key,),
        )
        self.conn.commit()

    def digest_payload(self, limit: int = 50) -> Dict[str, Any]:
        rows = self.list_open_observations(limit=limit)
        return {
            "open_items": [
                {
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
                for row in rows
            ]
        }

    def _migrate(self) -> None:
        self.conn.executescript(
            """
            create table if not exists people (
                telegram_id integer primary key,
                display_name text not null,
                username text,
                is_owner integer not null default 0,
                created_at text not null default current_timestamp
            );

            create table if not exists chats (
                telegram_id integer primary key,
                title text not null,
                type text not null,
                created_at text not null default current_timestamp
            );

            create table if not exists messages (
                chat_id integer not null,
                message_id integer not null,
                sender_id integer not null,
                text text not null,
                created_at text not null default current_timestamp,
                primary key (chat_id, message_id)
            );

            create table if not exists observations (
                id integer primary key autoincrement,
                chat_id integer not null,
                message_id integer not null,
                kind text not null,
                actor_id integer not null,
                target_id integer,
                target_label text,
                summary text not null,
                evidence text not null,
                confidence real not null,
                due_text text,
                status text not null default 'open',
                created_at text not null default current_timestamp,
                last_reminded_at text
            );

            create table if not exists codex_requests (
                id integer primary key autoincrement,
                chat_id integer not null,
                message_id integer not null,
                sender_id integer not null,
                text text not null,
                status text not null default 'pending',
                answer text,
                created_at text not null default current_timestamp,
                answered_at text
            );

            create table if not exists scheduled_digests (
                digest_key text primary key,
                sent_at text not null default current_timestamp
            );

            create table if not exists person_aliases (
                alias_norm text primary key,
                person_key text not null,
                alias text not null,
                created_at text not null default current_timestamp
            );

            create table if not exists dashboard_person_labels (
                person_key text primary key,
                label text not null default '',
                updated_at text not null default current_timestamp
            );

            create index if not exists idx_observations_status_created
                on observations (status, created_at);

            create index if not exists idx_codex_requests_status_created
                on codex_requests (status, created_at);
            """
        )
        self._ensure_column("observations", "target_label", "text")
        self._ensure_column("observations", "due_text", "text")
        self.conn.commit()

    def _ensure_column(self, table: str, column: str, declaration: str) -> None:
        columns = {row["name"] for row in self.conn.execute(f"pragma table_info({table})")}
        if column not in columns:
            self.conn.execute(f"alter table {table} add column {column} {declaration}")


def normalize_person_alias(value: str) -> str:
    text = str(value or "").strip().lower().replace("ё", "е")
    if text.startswith("@"):
        text = text[1:]
    text = re.sub(r"[^0-9a-zа-я_ -]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    words = [_normalize_name_word(word) for word in text.split()]
    return " ".join(word for word in words if word)


def _compact_alias(value: str) -> str:
    return re.sub(r"[\s_-]+", "", value)


def _normalize_name_word(word: str) -> str:
    for suffix in ("ому", "ему", "ыми", "ими", "ого", "его", "ой", "ый", "ий", "ая", "яя"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[: -len(suffix)]
    if len(word) > 3 and word[-1] in {"а", "у", "ю", "е", "ы", "и"}:
        return word[:-1]
    return word


def _alias_match_score(source: str, candidate: str) -> int:
    source_compact = _compact_alias(source)
    candidate_compact = _compact_alias(candidate)
    if not source_compact or not candidate_compact:
        return 0
    if source == candidate or source_compact == candidate_compact:
        return 100
    if len(source_compact) >= 5 and len(candidate_compact) >= 5:
        distance = _levenshtein(source_compact, candidate_compact)
        threshold = max(2, round(max(len(source_compact), len(candidate_compact)) * 0.24))
        if distance <= threshold:
            return 84 - distance

    source_tokens = source.split()
    candidate_tokens = candidate.split()
    matched_tokens = sum(
        1
        for source_token in source_tokens
        if any(_words_match(source_token, candidate_token) for candidate_token in candidate_tokens)
    )
    if matched_tokens >= 2:
        return 82 + min(matched_tokens, 3)
    return 0


def _words_match(left: str, right: str) -> bool:
    if left == right:
        return True
    if len(left) < 4 or len(right) < 4:
        return False
    if left.startswith(right) or right.startswith(left):
        return True
    distance = _levenshtein(left, right)
    threshold = 1 if max(len(left), len(right)) <= 6 else 2
    return distance <= threshold


def _levenshtein(left: str, right: str) -> int:
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


def _telegram_id_from_person_key(person_key: str) -> Optional[int]:
    if not person_key.startswith("tg:"):
        return None
    try:
        return int(person_key[3:])
    except ValueError:
        return None


def _label_from_person_key(person_key: str) -> str:
    if person_key.startswith("label:"):
        return person_key[6:]
    return person_key
