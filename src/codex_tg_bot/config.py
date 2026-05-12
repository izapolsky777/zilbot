from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    telegram_bot_token: str
    owner_telegram_id: Optional[int]
    database_path: Path
    codex_inbox_markdown: Path
    codex_inbox_json: Path
    codex_requests_markdown: Path
    codex_requests_json: Path
    voice_dir: Path
    openai_api_key: Optional[str]
    audio_transcription_model: str
    auto_reply_with_openai: bool
    openai_chat_model: str
    openai_worker_interval_seconds: int
    daily_digest_enabled: bool
    daily_digest_times: Tuple[str, ...]
    daily_digest_timezone: str
    google_service_account_file: Optional[Path]
    metrics_sources_path: Path
    metrics_cache_path: Path
    metrics_cache_ttl_seconds: int
    metrics_chart_dir: Path


def load_config() -> Config:
    load_dotenv()

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    owner_id = os.getenv("OWNER_TELEGRAM_ID", "").strip()
    openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
    google_service_account_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()

    return Config(
        telegram_bot_token=token,
        owner_telegram_id=int(owner_id) if owner_id else None,
        database_path=Path(os.getenv("DATABASE_PATH", "data/bot.sqlite3")),
        codex_inbox_markdown=Path(os.getenv("CODEX_INBOX_MARKDOWN", "data/codex_inbox.md")),
        codex_inbox_json=Path(os.getenv("CODEX_INBOX_JSON", "data/codex_inbox.json")),
        codex_requests_markdown=Path(os.getenv("CODEX_REQUESTS_MARKDOWN", "data/codex_requests.md")),
        codex_requests_json=Path(os.getenv("CODEX_REQUESTS_JSON", "data/codex_requests.json")),
        voice_dir=Path(os.getenv("VOICE_DIR", "data/voice")),
        openai_api_key=openai_api_key or None,
        audio_transcription_model=os.getenv("AUDIO_TRANSCRIPTION_MODEL", "whisper-1").strip() or "whisper-1",
        auto_reply_with_openai=os.getenv("AUTO_REPLY_WITH_OPENAI", "").strip().lower() in {"1", "true", "yes", "on"},
        openai_chat_model=os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini",
        openai_worker_interval_seconds=int(os.getenv("OPENAI_WORKER_INTERVAL_SECONDS", "30").strip() or "30"),
        daily_digest_enabled=os.getenv("DAILY_DIGEST_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"},
        daily_digest_times=tuple(
            item.strip()
            for item in os.getenv("DAILY_DIGEST_TIMES", "10:00,18:00").split(",")
            if item.strip()
        ),
        daily_digest_timezone=os.getenv("DAILY_DIGEST_TIMEZONE", "Europe/Moscow").strip() or "Europe/Moscow",
        google_service_account_file=Path(google_service_account_file) if google_service_account_file else None,
        metrics_sources_path=Path(os.getenv("METRICS_SOURCES_PATH", "data/metrics_sources.json")),
        metrics_cache_path=Path(os.getenv("METRICS_CACHE_PATH", "data/metrics_cache.json")),
        metrics_cache_ttl_seconds=int(os.getenv("METRICS_CACHE_TTL_SECONDS", "300").strip() or "300"),
        metrics_chart_dir=Path(os.getenv("METRICS_CHART_DIR", "data/metric_charts")),
    )
