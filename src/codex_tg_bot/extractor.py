from __future__ import annotations

import re
from typing import List, Optional, Tuple

from codex_tg_bot.models import Observation, Person


PROMISE_PATTERNS = [
    re.compile(r"\b(сделаю|подготовлю|пришлю|скину|проверю|создам|добавлю|исправлю|разберусь)\b", re.I),
    re.compile(r"\b(беру|возьму)\s+(на\s+себя|в\s+работу)\b", re.I),
]

ASSIGNMENT_PATTERNS = [
    re.compile(r"\b(поставь|добавь|создай|запиши)\s+(?:пожалуйста,\s+)?задач[ауи]\b", re.I),
    re.compile(r"(?<!\w)@[A-Za-z0-9_]{3,32}\b.+\b(нужно|надо|должен|должна|должны|пусть|попроси|поручи)\b", re.I),
    re.compile(r"(?<!\w)@[A-Za-z0-9_]{3,32}\b\s+с\s+(?:тебя|вас|него|нее|них)\b", re.I),
    re.compile(r"\b(сделай|подготовь|пришли|скинь|проверь|создай|добавь|исправь|разберись)\b", re.I),
    re.compile(r"\b(сходи|сходить|купи|купить|позвони|позвонить|отправь|отправить|закажи|заказать|привези|привезти|подай|подать)\b", re.I),
    re.compile(r"\b(сделать|подготовить|прислать|скинуть|проверить|создать|добавить|исправить|разобраться|сходить|купить|позвонить|отправить|заказать|привезти|подать)\b", re.I),
    re.compile(r"\b(нужно|надо|давай)\s+.+\b(сделать|подготовить|проверить|исправить|добавить|сходить|купить|позвонить|отправить|заказать|привезти|подать)\b", re.I),
    re.compile(r"\b(прошу|поручаю|попроси|поручи)\b.+\b(сделать|подготовить|проверить|исправить|добавить|сходить|купить|позвонить|отправить|заказать|привезти|подать)\b", re.I),
]

SELF_TASK_LIST_RE = re.compile(
    r"\b(мои\s+(?:дела|задачи)|мой\s+список\s+(?:дел|задач)|дела\s+на\s+сегодня)\b",
    re.I,
)
SELF_TASK_ITEM_RE = re.compile(
    r"(?:^|[.;]\s*)нужно\s+(?P<task>.+?)(?=(?:[.;]\s*нужно\s+)|$)",
    re.I,
)

MENTION_RE = re.compile(r"(?<!\w)@([A-Za-z0-9_]{3,32})")
NAMED_TASK_RE = re.compile(
    r"(?:поставь|добавь|создай|запиши)\s+(?:пожалуйста,\s+)?задач[ауи]\s+"
    r"(?:на|для|к)\s+"
    r"(?P<target>[А-ЯЁA-Z][А-ЯЁA-Zа-яёa-z-]+(?:\s+[А-ЯЁA-Z][А-ЯЁA-Zа-яёa-z-]+){0,2})"
    r"\s*,?\s*(?:чтобы|что|о\s+том,\s+что)?\s*(?P<task>.+?)(?=(?:\.\s*(?:поставь|добавь|создай|запиши)\s+задач)|$)",
    re.I,
)
NAMED_DATIVE_TASK_RE = re.compile(
    r"(?:поставь|добавь|создай|запиши)\s+(?:пожалуйста,\s+)?задач[ауи]\s+"
    r"(?P<target>[А-ЯЁA-Z][А-ЯЁA-Zа-яёa-z-]+(?:у|ю|е|ой|ому|ему)(?:\s+[А-ЯЁA-Z][А-ЯЁA-Zа-яёa-z-]+(?:у|ю|е|ой|ому|ему)){0,2})"
    r"\s*,?\s*(?:чтобы|что|о\s+том,\s+что)?\s*(?P<task>.+?)(?=(?:\.\s*(?:поставь|добавь|создай|запиши)\s+задач)|$)",
    re.I,
)
DIRECT_NAMED_COMMAND_RE = re.compile(
    r"^(?P<target>[А-ЯЁA-Z][А-ЯЁA-Zа-яёa-z-]+(?:\s+[А-ЯЁA-Z][А-ЯЁA-Zа-яёa-z-]+){0,2})"
    r"\s*,\s*"
    r"(?P<task>.+)",
    re.I,
)
DUE_PATTERNS = [
    re.compile(r"\b(сегодня|завтра|послезавтра)\b", re.I),
    re.compile(
        r"\bчерез\s+(?:\d+|один|два|три|четыре|пять|шесть|семь|восемь|девять|десять)\s+"
        r"(?:день|дня|дней|час|часа|часов|неделю|недели|недель)\b",
        re.I,
    ),
    re.compile(r"\b(до|к)\s+([0-3]?\d[./-][01]?\d(?:[./-]\d{2,4})?)\b", re.I),
    re.compile(r"\b(до|к|в)\s+([0-2]?\d[:.][0-5]\d)\b", re.I),
    re.compile(r"\b(в|во|к|ко|до)\s+ближайш(?:ий|ую|его|ей)\s+(понедельник|вторник|среду|четверг|пятницу|субботу|воскресенье)\b", re.I),
    re.compile(r"\b(в|во|к|ко|до)\s+(понедельник|вторник|среду|четверг|пятницу|субботу|воскресенье)\b", re.I),
    re.compile(r"\b(до|к)\s+(понедельника|вторника|среды|четверга|пятницы|субботы|воскресенья)\b", re.I),
]


def extract_observations(
    text: str,
    sender: Person,
    owner_telegram_id: Optional[int],
    reply_to_user_id: Optional[int] = None,
) -> List[Observation]:
    normalized = " ".join(text.split())
    if not normalized:
        return []

    observations: List[Observation] = []

    self_task_parts = _split_self_task_list(normalized)
    if self_task_parts:
        due_text = "сегодня" if re.search(r"\bсегодня\b", normalized, re.I) else _extract_due_text(normalized)
        for task_text in self_task_parts:
            observations.append(
                Observation(
                    kind="assignment",
                    actor_id=sender.telegram_id,
                    target_id=sender.telegram_id,
                    target_label="На мне",
                    summary=_summarize(task_text),
                    evidence=normalized,
                    confidence=0.76,
                    due_text=_extract_due_text(task_text) or due_text,
                )
            )
        return observations

    if any(pattern.search(normalized) for pattern in PROMISE_PATTERNS):
        observations.append(
            Observation(
                kind="promise",
                actor_id=sender.telegram_id,
                target_id=None,
                target_label=None,
                summary=_summarize(normalized),
                evidence=normalized,
                confidence=0.66,
                due_text=_extract_due_text(normalized),
            )
        )

    if any(pattern.search(normalized) for pattern in ASSIGNMENT_PATTERNS):
        assignment_parts = _split_assignments_by_mentions(normalized)
        if not assignment_parts:
            assignment_parts = _split_assignments_by_named_targets(normalized)
        if not assignment_parts:
            assignment_parts = _split_direct_named_command(normalized)

        if assignment_parts:
            for target_label, task_text in assignment_parts:
                observations.append(
                    Observation(
                        kind="assignment",
                        actor_id=sender.telegram_id,
                        target_id=None,
                        target_label=target_label,
                        summary=_summarize(task_text),
                        evidence=normalized,
                        confidence=0.72,
                        due_text=_extract_due_text(task_text),
                    )
                )
        else:
            target_id = reply_to_user_id
            if target_id is None and owner_telegram_id and sender.telegram_id == owner_telegram_id:
                target_id = None

            observations.append(
                Observation(
                    kind="assignment",
                    actor_id=sender.telegram_id,
                    target_id=target_id,
                    target_label=None,
                    summary=_summarize(normalized),
                    evidence=normalized,
                    confidence=0.58,
                    due_text=_extract_due_text(normalized),
                )
            )

    return observations


def _split_self_task_list(text: str) -> List[str]:
    if not SELF_TASK_LIST_RE.search(text):
        return []

    parts: List[str] = []
    for match in SELF_TASK_ITEM_RE.finditer(text):
        task = _clean_task_text(match.group("task"))
        if task and task.lower() not in {"все", "всё"}:
            parts.append(task)
    return parts


def _split_assignments_by_mentions(text: str) -> List[Tuple[str, str]]:
    matches = list(MENTION_RE.finditer(text))
    if not matches:
        return []

    parts: List[Tuple[str, str]] = []
    for index, match in enumerate(matches):
        target_label = "@" + match.group(1)
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        task_text = _clean_task_text(text[start:end])
        if task_text:
            parts.append((target_label, task_text))

    return parts


def _split_assignments_by_named_targets(text: str) -> List[Tuple[str, str]]:
    matches = list(NAMED_TASK_RE.finditer(text)) or list(NAMED_DATIVE_TASK_RE.finditer(text))
    parts: List[Tuple[str, str]] = []

    for match in matches:
        target = _clean_target_label(match.group("target"))
        task = _clean_task_text(match.group("task"))
        if target and task:
            parts.append((target, task))

    return _drop_superseded_named_targets(parts)


def _split_direct_named_command(text: str) -> List[Tuple[str, str]]:
    match = DIRECT_NAMED_COMMAND_RE.search(text)
    if not match:
        return []

    target = _clean_target_label(match.group("target"))
    task = _clean_task_text(match.group("task"))
    if not target or not task or not _looks_like_task_text(task):
        return []
    return [(target, task)]


def _looks_like_task_text(text: str) -> bool:
    return any(pattern.search(text) for pattern in ASSIGNMENT_PATTERNS)


def _drop_superseded_named_targets(parts: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    result: List[Tuple[str, str]] = []
    targets = [target.lower() for target, _task in parts]

    for index, (target, task) in enumerate(parts):
        target_lower = target.lower()
        task_lower = task.lower()
        has_more_specific_later_target = any(
            other.startswith(target_lower + " ")
            for other in targets[index + 1 :]
        )
        if has_more_specific_later_target and ("короче" in task_lower or len(target.split()) == 1):
            continue
        result.append((target, task))

    return result


def _clean_target_label(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip(" ,.;:-")
    return _normalize_russian_name_case(cleaned)


def _normalize_russian_name_case(text: str) -> str:
    words = text.split()
    if not 1 <= len(words) <= 3:
        return text

    normalized = []
    changed = False
    for word in words:
        if len(word) > 3 and word[-1].lower() in {"а", "у"}:
            normalized.append(word[:-1])
            changed = True
        else:
            normalized.append(word)

    return " ".join(normalized) if changed else text


def _clean_task_text(text: str) -> str:
    cleaned = text.strip(" ,.;:-")
    cleaned = re.sub(
        r"^(а\s+ты|ты|тебе|тебя|с\s+тебя|с\s+вас|с\s+него|с\s+нее|с\s+них|он\s+должен|она\s+должна|они\s+должны|он|она|они|должен|должна|должны|нужно|надо|пусть|прошу\s+тебя|прошу|пожалуйста)\s+",
        "",
        cleaned,
        flags=re.I,
    )
    cleaned = re.sub(r"\s*[.;,]?\s*(?:все|всё)\.?$", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _summarize(text: str, limit: int = 180) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def _extract_due_text(text: str) -> Optional[str]:
    for pattern in DUE_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(0)
    return None
