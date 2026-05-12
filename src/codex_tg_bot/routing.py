from __future__ import annotations

import re
from typing import Iterable


PROJECT_REQUEST_RE = re.compile(
    r"\b("
    r"бот|бота|боте|telegram-?бот|телеграм-?бот|дашборд|dashboard|кодекс|codex|"
    r"логик[ауе]?|распознаван\w+|извлечени\w+|алгоритм|"
    r"исправь|поправь|измени|добавь|сделай\s+так|научись|проверь\s+что|"
    r"перестал[ао]?|не\s+работа\w+|не\s+появил\w+|не\s+подтягива\w+"
    r")\b",
    re.I,
)


def has_assignment(observations: Iterable) -> bool:
    return any(getattr(item, "kind", None) == "assignment" for item in observations)


def is_project_request(text: str) -> bool:
    return bool(PROJECT_REQUEST_RE.search(str(text or "")))
