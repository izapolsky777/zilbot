from __future__ import annotations

import asyncio
import contextlib
import logging
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import FSInputFile, Message

from codex_tg_bot.codex_export import export_codex_inbox, export_codex_requests
from codex_tg_bot.config import Config, load_config
from codex_tg_bot.extractor import extract_observations
from codex_tg_bot.metrics import (
    MetricsUnavailable,
    answer_metrics_request,
    build_daily_metrics_digests,
    is_metrics_request,
)
from codex_tg_bot.models import Chat, Observation, Person
from codex_tg_bot.openai_responder import OpenAIResponderError, generate_openai_answer
from codex_tg_bot.routing import has_assignment, is_project_request
from codex_tg_bot.store import Store
from codex_tg_bot.transcriber import TranscriptionError, transcribe_audio_file


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    asyncio.run(run())


async def run() -> None:
    config = load_config()
    if not config.telegram_bot_token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is required. Copy .env.example to .env and fill it in.")

    store = Store(config.database_path)
    bot = Bot(config.telegram_bot_token)
    dispatcher = Dispatcher()

    register_handlers(dispatcher, store, config, bot)
    digest_task = asyncio.create_task(_scheduled_digest_loop(bot, store, config))

    try:
        await dispatcher.start_polling(bot)
    finally:
        digest_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await digest_task
        store.close()
        await bot.session.close()


def register_handlers(dispatcher: Dispatcher, store: Store, config: Config, bot: Bot) -> None:
    @dispatcher.message(Command("whoami"))
    async def whoami(message: Message) -> None:
        if message.from_user is None:
            return
        await _safe_answer(bot, message, f"Ваш Telegram ID: {message.from_user.id}")

    @dispatcher.message(Command("digest"))
    async def digest(message: Message) -> None:
        if not _is_owner(message, config):
            await _safe_answer(bot, message, "Эта команда доступна только владельцу бота.")
            return

        rows = store.list_open_observations(limit=100)
        if not rows:
            await _safe_answer(bot, message, "Пока нет открытых обещаний или задач.")
            return

        await _safe_answer(bot, message, _format_digest(rows, config))

    @dispatcher.message(Command("tasks"))
    async def tasks(message: Message) -> None:
        if not _is_owner(message, config):
            await _safe_answer(bot, message, "Эта команда доступна только владельцу бота.")
            return

        rows = [row for row in store.list_open_observations(limit=20) if row["kind"] == "assignment"]
        if not rows:
            await _safe_answer(bot, message, "Открытых задач пока нет.")
            return

        await _safe_answer(bot, message, _format_rows(rows))

    @dispatcher.message(Command("today"))
    async def today(message: Message) -> None:
        if not _is_owner(message, config):
            await _safe_answer(bot, message, "Эта команда доступна только владельцу бота.")
            return

        await _safe_answer(bot, message, _format_today_digest(store, config, _digest_now(config).date()))

    @dispatcher.message(Command("metrics"))
    async def metrics(message: Message) -> None:
        if not _is_owner(message, config):
            await _safe_answer(bot, message, "Эта команда доступна только владельцу бота.")
            return

        await _safe_answer(
            bot,
            message,
            "\n".join(
                [
                    "Раздел метрик активен.",
                    "",
                    "Пиши или диктуй вопросы по Google Sheets:",
                    "1. Сколько поездок на 12 мая?",
                    "2. Покажи график активных водителей.",
                    "3. Какой план/факт по НикВаТакс?",
                    "4. /metrics_digest — прислать утреннюю сводку сейчас.",
                    "",
                    "Источники: Беларусь, Кыргызстан, Узбекистан.",
                ]
            ),
        )

    @dispatcher.message(Command("metrics_digest"))
    async def metrics_digest(message: Message) -> None:
        if not _is_owner(message, config):
            await _safe_answer(bot, message, "Эта команда доступна только владельцу бота.")
            return

        _remember_metrics_digest_target(store, message)
        await _safe_answer(bot, message, "Собираю ежедневную сводку по метрикам.")
        await _send_metrics_digest_now(
            bot,
            config,
            {
                "chat_id": message.chat.id,
                "message_thread_id": _message_thread_id(message),
                "direct_messages_topic_id": _direct_messages_topic_id(message),
            },
            _metrics_report_date(config),
        )

    @dispatcher.message(Command("remind"))
    async def remind(message: Message) -> None:
        if not _is_owner(message, config):
            await _safe_answer(bot, message, "Эта команда доступна только владельцу бота.")
            return

        parts = (message.text or "").split(maxsplit=1)
        if len(parts) != 2 or not parts[1].strip().isdigit():
            await _safe_answer(bot, message, "Использование: /remind <id>")
            return

        observation_id = int(parts[1].strip())
        row = store.get_observation(observation_id)
        if row is None:
            await _safe_answer(bot, message, "Не нашел такую задачу или обещание.")
            return

        reminder = f"Напоминание по #{row['id']}: {row['summary']}"
        await _safe_send_reminder(bot, row["chat_id"], reminder, row["message_id"])
        store.mark_reminded(observation_id)
        await _safe_answer(bot, message, f"Напомнил в чате: {row['chat_title']}")

    @dispatcher.message(F.voice)
    async def watch_voice(message: Message) -> None:
        if message.from_user is None or message.voice is None:
            return

        person = _person_from_message(message, config)
        chat = _chat_from_message(message)
        store.upsert_person(person)
        store.upsert_chat(chat)

        is_private = message.chat.type == "private"
        is_owner = _is_owner(message, config)

        if is_private and not is_owner:
            await _safe_answer(bot, message, "Я принимаю голосовые запросы к Codex только от владельца.")
            return

        if not config.openai_api_key:
            if is_private or is_owner:
                await _safe_answer(
                    bot,
                    message,
                    "Голосовое получил, но распознавание еще не настроено. Добавь OPENAI_API_KEY в .env, и я смогу превращать голос в запросы для Codex.",
                )
            return

        if is_private:
            await _safe_answer(bot, message, "Голосовое получил. Расшифровываю и передаю в Codex.")

        try:
            voice_path = await _download_voice(bot, message, config.voice_dir)
            transcript = await transcribe_audio_file(
                voice_path,
                api_key=config.openai_api_key,
                model=config.audio_transcription_model,
            )
        except TranscriptionError as exc:
            logger.exception("Voice transcription failed")
            if is_private or is_owner:
                await _safe_answer(bot, message, f"Не смог разобрать голосовое: {exc}")
            return

        if not is_private:
            transcript_text = f"Голосовое сообщение, расшифровка:\n\n{transcript}"
            store.save_message(chat.telegram_id, message.message_id, person.telegram_id, transcript_text)
            observations = _save_observations_from_text(
                store,
                config,
                chat,
                message.message_id,
                person,
                transcript,
                reply_to_user_id=_reply_to_user_id(message, store, config),
            )
            if observations:
                export_codex_inbox(store, config.codex_inbox_markdown, config.codex_inbox_json)
                logger.info("Saved %s observations from voice in chat %s", len(observations), chat.title)
            else:
                logger.info("Voice in chat %s transcribed but no observations were extracted", chat.title)
            return

        request_text = f"Голосовой запрос, расшифровка:\n\n{transcript}"
        store.save_message(chat.telegram_id, message.message_id, person.telegram_id, request_text)
        outbound_result = await _handle_private_outbound_request(
            bot,
            store,
            config,
            chat,
            message.message_id,
            person,
            transcript,
            voice=True,
        )
        if outbound_result:
            await _safe_answer(bot, message, outbound_result)
            return

        if is_metrics_request(transcript):
            await _try_metrics_answer(bot, message, config, transcript)
            return

        project_request = is_project_request(transcript)
        observations = []
        if not project_request:
            observations = _save_observations_from_text(store, config, chat, message.message_id, person, transcript)
        if observations:
            export_codex_inbox(store, config.codex_inbox_markdown, config.codex_inbox_json)

        if has_assignment(observations):
            await _safe_answer(
                bot,
                message,
                _format_private_task_ack(observations, transcript, voice=True),
            )
            logger.info("Saved private voice task from %s", person.display_name)
            return

        request_id = store.create_codex_request(
            chat.telegram_id,
            message.message_id,
            person.telegram_id,
            request_text,
        )
        export_codex_requests(store, config.codex_requests_markdown, config.codex_requests_json)
        await _safe_answer(
            bot,
            message,
            _format_private_request_ack(request_id, observations, transcript, voice=True),
        )
        await _try_auto_reply(bot, store, config, request_id, chat.telegram_id, message.message_id, request_text)
        logger.info("Saved voice Codex request %s from %s", request_id, person.display_name)

    @dispatcher.message(F.text)
    async def watch_message(message: Message) -> None:
        if message.from_user is None or message.text is None:
            return

        person = _person_from_message(message, config)
        chat = _chat_from_message(message)
        store.upsert_person(person)
        store.upsert_chat(chat)
        store.save_message(chat.telegram_id, message.message_id, person.telegram_id, message.text)

        if message.chat.type == "private":
            if not _is_owner(message, config):
                await _safe_answer(bot, message, "Я принимаю запросы к Codex только от владельца.")
                return

            outbound_result = await _handle_private_outbound_request(
                bot,
                store,
                config,
                chat,
                message.message_id,
                person,
                message.text,
                voice=False,
            )
            if outbound_result:
                await _safe_answer(bot, message, outbound_result)
                return

            if is_metrics_request(message.text):
                await _try_metrics_answer(bot, message, config, message.text)
                return

            project_request = is_project_request(message.text)
            observations = []
            if not project_request:
                observations = _save_observations_from_text(store, config, chat, message.message_id, person, message.text)
            if observations:
                export_codex_inbox(store, config.codex_inbox_markdown, config.codex_inbox_json)

            if has_assignment(observations):
                await _safe_answer(
                    bot,
                    message,
                    _format_private_task_ack(observations, message.text, voice=False),
                )
                logger.info("Saved private task from %s", person.display_name)
                return

            request_id = store.create_codex_request(
                chat.telegram_id,
                message.message_id,
                person.telegram_id,
                message.text,
            )
            export_codex_requests(store, config.codex_requests_markdown, config.codex_requests_json)
            await _safe_answer(
                bot,
                message,
                _format_private_request_ack(request_id, observations, message.text, voice=False),
            )
            await _try_auto_reply(bot, store, config, request_id, chat.telegram_id, message.message_id, message.text)
            logger.info("Saved Codex request %s from %s", request_id, person.display_name)
            return

        observations = extract_observations(
            message.text,
            sender=person,
            owner_telegram_id=config.owner_telegram_id,
            reply_to_user_id=_reply_to_user_id(message, store, config),
        )

        for observation in observations:
            store.save_observation(chat.telegram_id, message.message_id, observation)

        if observations:
            export_codex_inbox(store, config.codex_inbox_markdown, config.codex_inbox_json)
            logger.info("Saved %s observations from chat %s", len(observations), chat.title)


OUTBOUND_COMMAND_RE = re.compile(r"\b(напомни|напомнить|отправь|отправить|напиши|написать|перешли|переслать)\b", re.I)
OUTBOUND_TARGET_RE = re.compile(
    r"\b(?:напомни|напомнить|отправь|отправить|напиши|написать|перешли|переслать)\s+"
    r"(?P<target>@?[A-Za-z0-9_]{3,32}|[А-ЯЁA-Z][А-ЯЁA-Zа-яёa-z-]+(?:\s+[А-ЯЁA-Z][А-ЯЁA-Zа-яёa-z-]+){0,2})",
    re.I,
)
TASK_LIST_RE = re.compile(r"\b(список\s+)?(его\s+|ее\s+|их\s+)?задач[иу]?\b", re.I)
OUTBOUND_TASK_INTENT_RE = re.compile(
    r"\b(поставь|добавь|создай|запиши|закинь|внеси)\b.+\b(задач|дашборд)|\bзадач[иу]?\s*[:：-]",
    re.I,
)


async def _handle_private_outbound_request(
    bot: Bot,
    store: Store,
    config: Config,
    chat: Chat,
    message_id: int,
    person: Person,
    text: str,
    voice: bool,
) -> str | None:
    request = _parse_outbound_request(store, text)
    if request is None:
        return None

    if request["telegram_id"] is None:
        return (
            "Понял, что нужно написать человеку, но не смог связать адресата с Telegram-профилем.\n"
            f"Адресат: {request['target_label']}.\n"
            "Добавь ему алиас на дашборде или пусть он напишет боту/появится в рабочем чате."
        )

    created = _create_outbound_assignments_if_needed(store, chat, message_id, person, text, request["canonical_label"])
    if created:
        export_codex_inbox(store, config.codex_inbox_markdown, config.codex_inbox_json)

    outbound_text = _format_outbound_message(store, request, text, created)
    try:
        await _send_chunks(bot, request["telegram_id"], outbound_text, reply_to_message_id=0)
    except TelegramForbiddenError:
        return (
            f"Задачу понял, адресат распознан: {request['display_name']}.\n"
            "Но Telegram не дал написать ему в личку: человек должен сначала открыть диалог с ботом и нажать Start или написать ему любое сообщение."
        )
    except TelegramBadRequest as exc:
        return (
            f"Задачу понял, адресат распознан: {request['display_name']}.\n"
            f"Но личное сообщение не ушло: {exc}"
        )

    lines = ["Готово: отправил личное сообщение."]
    lines.append(f"Адресат: {request['display_name']}.")
    if created:
        lines.append(f"Новых задач на дашборде: {len(created)}.")
    if voice:
        lines.extend(["", "Расшифровка:", _clip(text, 700)])
    return "\n".join(lines)


def _parse_outbound_request(store: Store, text: str) -> Dict | None:
    normalized = " ".join(str(text or "").split())
    if not OUTBOUND_COMMAND_RE.search(normalized):
        return None

    target_label = _extract_outbound_target(normalized)
    if not target_label:
        return None

    match = store.resolve_person_reference(target_label)
    if not match:
        return {
            "target_label": target_label,
            "telegram_id": None,
            "canonical_label": target_label,
            "display_name": target_label,
        }

    telegram_id = match["telegram_id"]
    canonical_label = match["canonical_label"]
    return {
        "target_label": target_label,
        "telegram_id": telegram_id,
        "canonical_label": canonical_label,
        "display_name": canonical_label,
    }


def _extract_outbound_target(text: str) -> str | None:
    match = OUTBOUND_TARGET_RE.search(text)
    if not match:
        return None
    target = match.group("target").strip(" ,.;:-")
    target_words = target.split()
    stop_words = {"напоминание", "напоминания", "сообщение", "сообщения", "список", "задачи", "задачу", "задач"}
    for index, word in enumerate(target_words):
        if word.lower().replace("ё", "е") in stop_words:
            target = " ".join(target_words[:index]).strip()
            break
    if target.lower() in {"мне", "ему", "ей", "им", "его", "ее", "их"}:
        return None
    return target


def _create_outbound_assignments_if_needed(
    store: Store,
    chat: Chat,
    message_id: int,
    person: Person,
    text: str,
    target_label: str,
) -> List[Observation]:
    if not OUTBOUND_TASK_INTENT_RE.search(text):
        return []

    task_texts = _extract_outbound_task_texts(text)
    created: List[Observation] = []
    for task_text in task_texts:
        observation = Observation(
            kind="assignment",
            actor_id=person.telegram_id,
            target_id=None,
            target_label=target_label,
            summary=_clip(task_text, 180),
            evidence=text,
            confidence=0.7,
            due_text=_extract_due_from_text(task_text),
        )
        store.save_observation(chat.telegram_id, message_id, observation)
        created.append(observation)
    return created


def _extract_outbound_task_texts(text: str) -> List[str]:
    payload = text
    split_match = re.search(r"(?:задач[иу]?|следующее|следующие)\s*[:：-]\s*(?P<payload>.+)$", text, re.I)
    if split_match:
        payload = split_match.group("payload")
    else:
        marker = re.search(r"\b(?:чтобы|что)\b\s+(?P<payload>.+)$", text, re.I)
        if marker:
            payload = marker.group("payload")

    parts = [
        part.strip(" ,.;:-")
        for part in re.split(r"(?:\n+|(?:^|\s)\d+[.)]\s+|;\s+|\s+-\s+)", payload)
        if part.strip(" ,.;:-")
    ]
    if not parts:
        parts = [payload.strip(" ,.;:-")]
    return [_clean_outbound_task_text(part) for part in parts if _clean_outbound_task_text(part)]


def _clean_outbound_task_text(text: str) -> str:
    cleaned = re.sub(
        r"^(?:он|она|они|ты)?\s*(?:должен|должна|должны|нужно|надо|пусть|с\s+тебя)\s+",
        "",
        text.strip(" ,.;:-"),
        flags=re.I,
    )
    return re.sub(r"\s+", " ", cleaned).strip()


def _format_outbound_message(store: Store, request: Dict, source_text: str, created: List[Observation]) -> str:
    lines = ["Напоминание от Силбота."]
    custom_message = _extract_custom_outbound_message(source_text)

    if custom_message:
        lines.extend(["", custom_message])

    if created:
        lines.extend(["", "Новые задачи:"])
        for index, item in enumerate(created, start=1):
            due = f" Срок: {item.due_text}." if item.due_text else ""
            lines.append(f"{index}. {item.summary}.{due}")

    if TASK_LIST_RE.search(source_text) and request["telegram_id"]:
        rows = store.list_open_assignments_for_person(request["telegram_id"], limit=30)
        lines.extend(["", "Открытые задачи на тебе:"])
        if rows:
            for index, row in enumerate(rows, start=1):
                due = f" Срок: {row['due_text']}." if row["due_text"] else ""
                lines.append(f"{index}. {row['summary']}.{due}")
        else:
            lines.append("Сейчас открытых задач не вижу.")

    if len(lines) == 1:
        lines.append("")
        lines.append(_clip(source_text, 1200))

    return "\n".join(lines)


def _extract_custom_outbound_message(text: str) -> str:
    patterns = [
        r"\bнапоминани[ея]\s+о\s+том,\s+что\s+(?P<body>.+)$",
        r"\bнапоминани[ея]\s+что\s+(?P<body>.+)$",
        r"\bсообщени[ея]\s+о\s+том,\s+что\s+(?P<body>.+)$",
        r"\bсообщени[ея]\s+что\s+(?P<body>.+)$",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return _clip(match.group("body").strip(" ,.;:-"), 1200)
    return ""


def _extract_due_from_text(text: str) -> str | None:
    observations = extract_observations(
        f"@temporary {text}",
        sender=Person(telegram_id=0, display_name="temporary", username=None, is_owner=False),
        owner_telegram_id=None,
    )
    for observation in observations:
        if observation.due_text:
            return observation.due_text
    return None


def _is_owner(message: Message, config: Config) -> bool:
    return bool(message.from_user and config.owner_telegram_id == message.from_user.id)


def _person_from_message(message: Message, config: Config) -> Person:
    user = message.from_user
    if user is None:
        raise ValueError("message has no sender")
    return Person(
        telegram_id=user.id,
        display_name=_display_name(user),
        username=user.username,
        is_owner=config.owner_telegram_id == user.id,
    )


def _chat_from_message(message: Message) -> Chat:
    title = message.chat.title or message.chat.full_name or str(message.chat.id)
    return Chat(telegram_id=message.chat.id, title=title, type=message.chat.type)


def _display_name(user: object) -> str:
    first_name = getattr(user, "first_name", None) or ""
    last_name = getattr(user, "last_name", None) or ""
    username = getattr(user, "username", None)
    full_name = " ".join(part for part in [first_name, last_name] if part).strip()
    return full_name or (f"@{username}" if username else str(getattr(user, "id", "")))


def _reply_to_user_id(message: Message, store: Store, config: Config) -> int | None:
    if not message.reply_to_message or not message.reply_to_message.from_user:
        return None

    reply_to_user = message.reply_to_message.from_user
    reply_to_person = Person(
        telegram_id=reply_to_user.id,
        display_name=_display_name(reply_to_user),
        username=reply_to_user.username,
        is_owner=config.owner_telegram_id == reply_to_user.id,
    )
    store.upsert_person(reply_to_person)
    return reply_to_user.id


def _save_observations_from_text(
    store: Store,
    config: Config,
    chat: Chat,
    message_id: int,
    person: Person,
    text: str,
    reply_to_user_id: int | None = None,
) -> List:
    observations = extract_observations(
        text,
        sender=person,
        owner_telegram_id=config.owner_telegram_id,
        reply_to_user_id=reply_to_user_id,
    )
    for observation in observations:
        store.save_observation(chat.telegram_id, message_id, observation)
    return observations


def _format_private_request_ack(request_id: int, observations: List, source_text: str, voice: bool) -> str:
    prefix = "Принял голосовой запрос" if voice else "Принял запрос"
    lines = [f"{prefix} #{request_id} и передал его в Codex."]

    assignments = [item for item in observations if item.kind == "assignment"]
    if assignments:
        lines.extend(["", "Также зафиксировал задачи:"])
        for index, item in enumerate(assignments, start=1):
            assignee = item.target_label or "адресат не распознан"
            due = f" Срок: {item.due_text}." if item.due_text else ""
            lines.append(f"{index}. {assignee}: {item.summary}.{due}")

    if voice:
        lines.extend(["", "Расшифровка:", _clip(source_text, 700)])
    else:
        lines.append("Отвечу сюда, когда будет результат.")

    return "\n".join(lines)


def _format_private_task_ack(observations: List, source_text: str, voice: bool) -> str:
    prefix = "Принял голосовое и поставил задачу" if voice else "Принял и поставил задачу"
    assignments = [item for item in observations if item.kind == "assignment"]
    lines = [f"{prefix} на дашборд."]

    for index, item in enumerate(assignments, start=1):
        assignee = item.target_label or "адресат не распознан"
        due = f" Срок: {item.due_text}." if item.due_text else ""
        lines.append(f"{index}. {assignee}: {item.summary}.{due}")

    if voice:
        lines.extend(["", "Расшифровка:", _clip(source_text, 700)])

    return "\n".join(lines)


async def _try_metrics_answer(bot: Bot, message: Message, config: Config, text: str) -> None:
    await _safe_answer(bot, message, "Смотрю Google Sheets и собираю метрики.")
    try:
        answer = await answer_metrics_request(config, text)
    except MetricsUnavailable as exc:
        await _safe_answer(bot, message, f"Метрики пока не могу прочитать: {exc}")
        return
    except Exception as exc:
        logger.exception("Metrics request failed")
        await _safe_answer(bot, message, f"Не смог собрать ответ по метрикам: {exc}")
        return

    await _safe_answer(bot, message, answer.text)
    for chart_path in answer.chart_paths:
        if chart_path.exists():
            await bot.send_photo(chat_id=message.chat.id, photo=FSInputFile(chart_path), reply_to_message_id=message.message_id)


async def _safe_answer(bot: Bot, message: Message, text: str) -> None:
    try:
        await message.answer(text)
    except TelegramBadRequest as exc:
        if "message thread not found" not in str(exc):
            raise
        await bot.send_message(chat_id=message.chat.id, text=text)


async def _safe_send_reminder(bot: Bot, chat_id: int, text: str, reply_to_message_id: int) -> None:
    try:
        await bot.send_message(chat_id=chat_id, text=text, reply_to_message_id=reply_to_message_id)
    except TelegramBadRequest as exc:
        if "message thread not found" not in str(exc):
            raise
        await bot.send_message(chat_id=chat_id, text=text)


async def _try_auto_reply(
    bot: Bot,
    store: Store,
    config: Config,
    request_id: int,
    chat_id: int,
    message_id: int,
    request_text: str,
) -> None:
    if not config.auto_reply_with_openai:
        return

    try:
        answer = await generate_openai_answer(config, store, request_text)
    except OpenAIResponderError as exc:
        logger.exception("OpenAI auto reply failed")
        await _send_chunks(bot, chat_id, f"Не смог получить ответ ИИ по запросу #{request_id}: {exc}", message_id)
        return

    text = f"Ответ ИИ по запросу #{request_id}:\n\n{answer}"
    await _send_chunks(bot, chat_id, text, message_id)
    store.mark_codex_request_answered(request_id, answer)
    export_codex_requests(store, config.codex_requests_markdown, config.codex_requests_json)


async def _send_chunks(
    bot: Bot,
    chat_id: int,
    text: str,
    reply_to_message_id: int,
    message_thread_id: int | None = None,
    direct_messages_topic_id: int | None = None,
) -> None:
    for index, chunk in enumerate(_chunk_text(text)):
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=chunk,
                reply_to_message_id=reply_to_message_id if index == 0 and reply_to_message_id else None,
                message_thread_id=message_thread_id,
                direct_messages_topic_id=direct_messages_topic_id,
            )
        except TelegramBadRequest as exc:
            if "message thread not found" not in str(exc):
                raise
            await bot.send_message(chat_id=chat_id, text=chunk, direct_messages_topic_id=direct_messages_topic_id)


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


async def _download_voice(bot: Bot, message: Message, voice_dir: Path) -> Path:
    if message.voice is None:
        raise TranscriptionError("Voice message is missing.")

    voice_dir.mkdir(parents=True, exist_ok=True)
    file = await bot.get_file(message.voice.file_id)
    path = voice_dir / f"{message.chat.id}_{message.message_id}.ogg"
    with path.open("wb") as destination:
        await bot.download_file(file.file_path, destination=destination)
    return path


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def _format_rows(rows: List) -> str:
    chunks = []
    for row in rows:
        kind = "обещание" if row["kind"] == "promise" else "задача"
        target_name = row["target_name"] or row["target_label"]
        target = f" -> {target_name}" if target_name else ""
        chunks.append(
            f"#{row['id']} {kind}: {row['actor_name']}{target}\n"
            f"Чат: {row['chat_title']}\n"
            f"{row['summary']}"
        )
    return "\n\n".join(chunks)


def _format_digest(rows: List, config: Config) -> str:
    assignments = [row for row in rows if row["kind"] == "assignment"]
    promises = [row for row in rows if row["kind"] == "promise"]

    lines = ["Дайджест задач и обещаний", ""]

    if assignments:
        lines.append("Задачи по исполнителям:")
        owner_rows = []
        groups = _group_assignments(assignments)
        for group in groups:
            if _is_owner_group(group["rows"], group["name"], config):
                owner_rows.extend(group["rows"])
                continue
            lines.extend(_format_assignment_group(group["name"], group["rows"]))
            lines.append("")
    else:
        lines.extend(["Задачи по исполнителям:", "Пока нет открытых задач.", ""])
        owner_rows = []

    if promises:
        lines.append("Обещания:")
        for index, row in enumerate(promises, start=1):
            actor = _person_display(row, "actor")
            due = f" Срок: {row['due_text']}." if row["due_text"] else ""
            lines.append(f"{index}. {actor}: {row['summary']}.{due}")
        lines.append("")

    lines.append("На мне:")
    if owner_rows:
        for index, row in enumerate(owner_rows, start=1):
            due = f" Срок: {row['due_text']}." if row["due_text"] else ""
            lines.append(f"{index}. {row['summary']}.{due}")
    else:
        lines.append("Сейчас открытых задач на тебе не вижу.")

    return "\n".join(_trim_empty_tail(lines))


def _group_assignments(rows: List) -> List[Dict]:
    groups: Dict[str, Dict] = {}
    for row in rows:
        key = _assignee_key(row)
        if key not in groups:
            groups[key] = {"name": _assignee_display(row), "rows": []}
        groups[key]["rows"].append(row)

    return sorted(
        groups.values(),
        key=lambda group: (group["name"].lower() == "без исполнителя", group["name"].lower()),
    )


def _format_assignment_group(name: str, rows: List) -> List[str]:
    lines = [f"{name}:"]
    for index, row in enumerate(_sort_group_rows(rows), start=1):
        due = f" Срок: {row['due_text']}." if row["due_text"] else ""
        lines.append(f"{index}. {row['summary']}.{due}")
    return lines


def _sort_group_rows(rows: List) -> List:
    return sorted(rows, key=lambda row: (row["due_text"] is None, str(row["due_text"] or ""), str(row["created_at"] or "")))


def _assignee_key(row) -> str:
    if row["target_telegram_id"]:
        return f"tg:{row['target_telegram_id']}"
    if row["target_label"]:
        return f"label:{str(row['target_label']).lower()}"
    return "unassigned"


def _assignee_display(row) -> str:
    return row["target_label_custom"] or row["target_text_label_custom"] or _person_display(row, "target") or row["target_label"] or "Без исполнителя"


def _person_display(row, prefix: str) -> str:
    if prefix == "actor" and row["actor_label"]:
        return row["actor_label"]
    if prefix == "target" and row["target_label_custom"]:
        return row["target_label_custom"]
    username = row[f"{prefix}_username"]
    name = row[f"{prefix}_name"]
    if username:
        return "@" + username
    return name or ""


def _is_owner_group(rows: List, name: str, config: Config) -> bool:
    if config.owner_telegram_id and any(row["target_telegram_id"] == config.owner_telegram_id for row in rows):
        return True
    return name in {"Ivan", "@zilteccorp"}


async def _scheduled_digest_loop(bot: Bot, store: Store, config: Config) -> None:
    if config.owner_telegram_id is None and config.metrics_daily_digest_chat_id is None:
        return
    if not config.daily_digest_enabled and not config.metrics_daily_digest_enabled:
        return

    while True:
        try:
            await _send_due_scheduled_digests(bot, store, config)
            await _send_due_scheduled_metrics_digests(bot, store, config)
        except Exception:
            logger.exception("Scheduled daily digest failed")
        await asyncio.sleep(30)


async def _send_due_scheduled_digests(bot: Bot, store: Store, config: Config) -> None:
    if not config.daily_digest_enabled or config.owner_telegram_id is None:
        return

    now = _digest_now(config)
    today = now.date()
    current_minutes = now.hour * 60 + now.minute

    for digest_time in config.daily_digest_times:
        scheduled_minutes = _parse_digest_time(digest_time)
        if scheduled_minutes is None or not (scheduled_minutes <= current_minutes <= scheduled_minutes + 5):
            continue

        digest_key = f"today:{today.isoformat()}:{digest_time}"
        if store.has_scheduled_digest_been_sent(digest_key):
            continue

        text = _format_today_digest(store, config, today)
        await _send_chunks(bot, config.owner_telegram_id, text, reply_to_message_id=0)
        store.mark_scheduled_digest_sent(digest_key)
        logger.info("Sent scheduled daily digest %s", digest_key)


async def _send_due_scheduled_metrics_digests(bot: Bot, store: Store, config: Config) -> None:
    target = _metrics_digest_target(store, config)
    if not config.metrics_daily_digest_enabled or target is None:
        return

    now = _digest_now(config)
    today = now.date()
    current_minutes = now.hour * 60 + now.minute

    for digest_time in config.metrics_daily_digest_times:
        scheduled_minutes = _parse_digest_time(digest_time)
        if scheduled_minutes is None or not (scheduled_minutes <= current_minutes <= scheduled_minutes + 5):
            continue

        digest_key = f"metrics:{today.isoformat()}:{digest_time}"
        if store.has_scheduled_digest_been_sent(digest_key):
            continue

        try:
            await _send_metrics_digest_now(bot, config, target, _metrics_report_date(config))
        except Exception as exc:
            logger.exception("Scheduled metrics digest failed")
            await _send_chunks(
                bot,
                target["chat_id"],
                f"Не смог собрать утреннюю сводку метрик: {exc}",
                reply_to_message_id=0,
                message_thread_id=target.get("message_thread_id"),
                direct_messages_topic_id=target.get("direct_messages_topic_id"),
            )
        store.mark_scheduled_digest_sent(digest_key)
        logger.info("Sent scheduled metrics digest %s", digest_key)


async def _send_metrics_digest_now(
    bot: Bot,
    config: Config,
    target: Dict[str, int | None],
    report_date: date | None = None,
) -> None:
    chat_id = int(target["chat_id"])
    message_thread_id = target.get("message_thread_id")
    direct_messages_topic_id = target.get("direct_messages_topic_id")
    try:
        digests = await build_daily_metrics_digests(config, report_date=report_date)
    except MetricsUnavailable as exc:
        await _send_chunks(
            bot,
            chat_id,
            f"Метрики пока не могу прочитать: {exc}",
            reply_to_message_id=0,
            message_thread_id=message_thread_id,
            direct_messages_topic_id=direct_messages_topic_id,
        )
        return

    if not digests:
        await _send_chunks(
            bot,
            chat_id,
            "Не нашел данных для ежедневной сводки метрик.",
            reply_to_message_id=0,
            message_thread_id=message_thread_id,
            direct_messages_topic_id=direct_messages_topic_id,
        )
        return

    for digest in digests:
        await _send_chunks(
            bot,
            chat_id,
            digest.text,
            reply_to_message_id=0,
            message_thread_id=message_thread_id,
            direct_messages_topic_id=direct_messages_topic_id,
        )
        for chart_path in digest.chart_paths:
            if chart_path.exists():
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=FSInputFile(chart_path),
                    message_thread_id=message_thread_id,
                    direct_messages_topic_id=direct_messages_topic_id,
                )


def _metrics_report_date(config: Config) -> date:
    return _digest_now(config).date() - timedelta(days=1)


def _metrics_digest_target(store: Store, config: Config) -> Dict[str, int | None] | None:
    if config.metrics_daily_digest_chat_id is not None:
        return {
            "chat_id": config.metrics_daily_digest_chat_id,
            "message_thread_id": None,
            "direct_messages_topic_id": None,
        }
    stored_chat_id = _int_setting(store, "metrics_digest_chat_id")
    if stored_chat_id is not None:
        return {
            "chat_id": stored_chat_id,
            "message_thread_id": _int_setting(store, "metrics_digest_message_thread_id"),
            "direct_messages_topic_id": _int_setting(store, "metrics_digest_direct_messages_topic_id"),
        }
    chat_id = store.find_chat_id_by_title(config.metrics_daily_digest_chat_title)
    if chat_id is None:
        return None
    return {"chat_id": chat_id, "message_thread_id": None, "direct_messages_topic_id": None}


def _remember_metrics_digest_target(store: Store, message: Message) -> None:
    store.set_setting("metrics_digest_chat_id", str(message.chat.id))
    thread_id = _message_thread_id(message)
    direct_topic_id = _direct_messages_topic_id(message)
    store.set_setting("metrics_digest_message_thread_id", str(thread_id or ""))
    store.set_setting("metrics_digest_direct_messages_topic_id", str(direct_topic_id or ""))


def _message_thread_id(message: Message) -> int | None:
    value = getattr(message, "message_thread_id", None)
    return int(value) if value else None


def _direct_messages_topic_id(message: Message) -> int | None:
    topic = getattr(message, "direct_messages_topic", None)
    value = getattr(topic, "topic_id", None) if topic else None
    return int(value) if value else None


def _int_setting(store: Store, key: str) -> int | None:
    value = store.get_setting(key)
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _format_today_digest(store: Store, config: Config, today: date) -> str:
    rows = store.list_open_observations(limit=200)
    due_rows = [row for row in rows if _is_due_on_date(row["due_text"], row["created_at"], today, config)]
    assignments = [row for row in due_rows if row["kind"] == "assignment"]
    promises = [row for row in due_rows if row["kind"] == "promise"]

    lines = [f"План на сегодня, {today.strftime('%d.%m.%Y')}", ""]

    lines.append("Задачи к выполнению сегодня:")
    if assignments:
        for index, row in enumerate(assignments, start=1):
            assignee = _assignee_display(row)
            due = row["due_text"] or "сегодня"
            lines.append(f"{index}. Ответственный: {assignee}")
            lines.append(f"   Задача: {row['summary']}")
            lines.append(f"   Срок: {due}")
            lines.append(f"   Чат: {row['chat_title']}")
    else:
        lines.append("Открытых задач со сроком на сегодня не вижу.")

    lines.append("")
    lines.append("Обещали сделать сегодня:")
    if promises:
        for index, row in enumerate(promises, start=1):
            responsible = _person_display(row, "actor") or row["actor_name"] or "Не распознан"
            due = row["due_text"] or "сегодня"
            lines.append(f"{index}. Ответственный: {responsible}")
            lines.append(f"   Обещание: {row['summary']}")
            lines.append(f"   Срок: {due}")
            lines.append(f"   Чат: {row['chat_title']}")
    else:
        lines.append("Открытых обещаний со сроком на сегодня не вижу.")

    return "\n".join(_trim_empty_tail(lines))


def _is_due_on_date(due_text: str | None, created_at: str | None, target_date: date, config: Config) -> bool:
    due = str(due_text or "").strip().lower().replace("ё", "е")
    if not due:
        return False

    created_date = _created_date(created_at, config)
    if "сегодня" in due:
        return created_date == target_date
    if "завтра" in due and "послезавтра" not in due:
        return created_date + timedelta(days=1) == target_date
    if "послезавтра" in due:
        return created_date + timedelta(days=2) == target_date

    date_match = re.search(r"([0-3]?\d)[./-]([01]?\d)(?:[./-](\d{2,4}))?", due)
    if date_match:
        day = int(date_match.group(1))
        month = int(date_match.group(2))
        year_raw = date_match.group(3)
        year = target_date.year if not year_raw else int(year_raw)
        if year < 100:
            year += 2000
        try:
            return date(year, month, day) == target_date
        except ValueError:
            return False

    weekday = _due_weekday(due)
    if weekday is not None:
        days_ahead = (weekday - created_date.weekday()) % 7
        return created_date + timedelta(days=days_ahead) == target_date

    return False


def _created_date(created_at: str | None, config: Config) -> date:
    if not created_at:
        return _digest_now(config).date()
    try:
        created_utc = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return _digest_now(config).date()
    return created_utc.astimezone(_digest_timezone(config)).date()


def _due_weekday(due: str) -> int | None:
    weekdays = {
        "понедельник": 0,
        "понедельника": 0,
        "вторник": 1,
        "вторника": 1,
        "среду": 2,
        "среда": 2,
        "среды": 2,
        "четверг": 3,
        "четверга": 3,
        "пятницу": 4,
        "пятница": 4,
        "пятницы": 4,
        "субботу": 5,
        "суббота": 5,
        "субботы": 5,
        "воскресенье": 6,
        "воскресенья": 6,
    }
    for word, index in weekdays.items():
        if re.search(rf"\b{word}\b", due):
            return index
    return None


def _parse_digest_time(value: str) -> int | None:
    match = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", value.strip())
    if not match:
        return None
    return int(match.group(1)) * 60 + int(match.group(2))


def _digest_now(config: Config) -> datetime:
    return datetime.now(_digest_timezone(config))


def _digest_timezone(config: Config) -> ZoneInfo:
    try:
        return ZoneInfo(config.daily_digest_timezone)
    except ZoneInfoNotFoundError:
        return ZoneInfo("Europe/Moscow")


def _trim_empty_tail(lines: List[str]) -> List[str]:
    while lines and lines[-1] == "":
        lines.pop()
    return lines


if __name__ == "__main__":
    main()
