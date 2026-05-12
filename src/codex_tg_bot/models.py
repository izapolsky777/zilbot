from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Person:
    telegram_id: int
    display_name: str
    username: Optional[str]
    is_owner: bool


@dataclass(frozen=True)
class Chat:
    telegram_id: int
    title: str
    type: str


@dataclass(frozen=True)
class Observation:
    kind: str
    actor_id: int
    target_id: Optional[int]
    target_label: Optional[str]
    summary: str
    evidence: str
    confidence: float
    due_text: Optional[str] = None
