from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiohttp

from codex_tg_bot.config import Config


SHEETS_READONLY_SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"
DEFAULT_SPREADSHEET_ID = "1pMp4W1W4bz1b3QLq-HID-LzlLgm8KsD7S5Kl6fgAW2Q"
DEFAULT_METRICS_SOURCES = [
    {
        "name": "Беларусь Supply",
        "spreadsheet_id": DEFAULT_SPREADSHEET_ID,
        "sheets": [
            {"name": "Актуальный план", "kind": "wide", "range": "A1:AR1003"},
            {"name": "Прогнозы", "kind": "table", "range": "A1:AE1000"},
            {"name": "Контрагенты", "kind": "table", "range": "A1:AC1002"},
            {"name": "Прозвон таксопарков", "kind": "notes", "range": "A1:AA1000"},
        ],
    }
]
METRICS_INTENT_RE = re.compile(
    r"\b(метрик|метрик[аиу]|цифр|показател|план|факт|прогноз|поездк|заказ|"
    r"клиент|водител|таксопарк|контрагент|капасити|конверси|o2r|лист ожидани|"
    r"активн|зарегистрирован|гаранти|график|динамик|тренд)\b",
    re.I,
)
CHART_INTENT_RE = re.compile(r"\b(график|диаграмм|динамик|тренд|нарисуй|покажи)\b", re.I)

_CACHE: dict[str, tuple[float, "MetricsDataset"]] = {}


class MetricsUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class MetricPoint:
    label: str
    raw_value: str
    number: float | None


@dataclass(frozen=True)
class MetricSeries:
    source: str
    sheet: str
    block: str
    metric: str
    points: tuple[MetricPoint, ...]


@dataclass(frozen=True)
class TableSheet:
    source: str
    sheet: str
    headers: tuple[str, ...]
    rows: tuple[dict[str, str], ...]
    kind: str


@dataclass(frozen=True)
class MetricsDataset:
    title: str
    loaded_at: float
    series: tuple[MetricSeries, ...]
    tables: tuple[TableSheet, ...]


@dataclass(frozen=True)
class MetricsAnswer:
    text: str
    chart_paths: tuple[Path, ...] = ()


def is_metrics_request(text: str) -> bool:
    return bool(METRICS_INTENT_RE.search(str(text or "")))


async def answer_metrics_request(config: Config, request_text: str) -> MetricsAnswer:
    dataset = await load_metrics_dataset(config)
    context = build_metrics_context(dataset, request_text)
    answer = await _generate_answer(config, request_text, context)
    chart_paths = create_metric_charts(config, dataset, request_text) if CHART_INTENT_RE.search(request_text) else ()
    return MetricsAnswer(text=answer, chart_paths=chart_paths)


async def load_metrics_dataset(config: Config) -> MetricsDataset:
    cache_key = str(config.metrics_sources_path.resolve())
    cached = _CACHE.get(cache_key)
    if cached and time.time() - cached[0] < config.metrics_cache_ttl_seconds:
        return cached[1]

    sources = _load_sources(config.metrics_sources_path)
    values_by_range = await _read_google_sheet_values(config, sources)
    series: list[MetricSeries] = []
    tables: list[TableSheet] = []
    title = ", ".join(source.get("name", "Google Sheet") for source in sources)

    for source in sources:
        source_name = str(source.get("name") or "Google Sheet")
        for sheet in source.get("sheets", []):
            sheet_name = str(sheet.get("name") or "").strip()
            kind = str(sheet.get("kind") or "table").strip().lower()
            rows = values_by_range.get((source_name, sheet_name), [])
            if not rows:
                continue
            if kind == "wide":
                series.extend(_parse_wide_sheet(source_name, sheet_name, rows))
            else:
                table = _parse_table_sheet(source_name, sheet_name, rows, kind)
                if table.rows:
                    tables.append(table)

    dataset = MetricsDataset(title=title, loaded_at=time.time(), series=tuple(series), tables=tuple(tables))
    _CACHE[cache_key] = (time.time(), dataset)
    return dataset


def build_metrics_context(dataset: MetricsDataset, request_text: str) -> str:
    lines = [f"Источник: {dataset.title}", ""]
    ranked_series = _rank_series(dataset.series, request_text)

    if ranked_series:
        lines.append("Временные ряды, наиболее похожие на запрос:")
        for series in ranked_series[:8]:
            points = [point for point in series.points if point.raw_value]
            latest = _latest_point(points)
            previous = _previous_point(points)
            prefix = f"- {series.sheet} / {series.block} / {series.metric}"
            if latest:
                delta = _format_delta(latest, previous)
                prefix += f": последнее {latest.label} = {latest.raw_value}{delta}"
            lines.append(prefix)
            compact_points = "; ".join(f"{point.label}: {point.raw_value}" for point in points[-20:])
            if compact_points:
                lines.append(f"  значения: {compact_points}")
        lines.append("")

    for table in dataset.tables:
        matched_rows = _matched_table_rows(table, request_text)
        summary = _table_summary(table)
        if summary:
            lines.append(f"{table.sheet}: {summary}")
        if matched_rows:
            lines.append(f"{table.sheet}, строки по запросу:")
            for row in matched_rows[:12]:
                lines.append("  - " + _compact_row(row, table.headers))
        lines.append("")

    return "\n".join(_trim_empty(lines)) or "Метрики не найдены."


def create_metric_charts(config: Config, dataset: MetricsDataset, request_text: str) -> tuple[Path, ...]:
    series = [item for item in _rank_series(dataset.series, request_text) if any(point.number is not None for point in item.points)]
    if not series:
        return ()

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:  # pragma: no cover - depends on optional runtime package
        raise MetricsUnavailable(f"Не могу построить график: matplotlib недоступен ({exc}).") from exc

    config.metrics_chart_dir.mkdir(parents=True, exist_ok=True)
    selected = series[:3]
    fig, ax = plt.subplots(figsize=(11, 5.8), dpi=160)
    for item in selected:
        points = [point for point in item.points if point.number is not None]
        if not points:
            continue
        labels = [point.label for point in points]
        values = [float(point.number or 0) for point in points]
        ax.plot(labels, values, marker="o", linewidth=2, markersize=3, label=f"{item.block}: {item.metric}")

    ax.set_title("Метрики из Google Sheets")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best", fontsize=8)
    ax.tick_params(axis="x", labelrotation=45, labelsize=7)
    ax.tick_params(axis="y", labelsize=8)
    fig.tight_layout()
    path = config.metrics_chart_dir / f"metric_{uuid.uuid4().hex[:10]}.png"
    fig.savefig(path)
    plt.close(fig)
    return (path,)


def _load_sources(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return DEFAULT_METRICS_SOURCES

    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("sources", [])
    if not isinstance(data, list) or not data:
        raise MetricsUnavailable(f"Файл источников метрик пустой или неверного формата: {path}")
    return [source for source in data if isinstance(source, dict)]


async def _read_google_sheet_values(config: Config, sources: list[dict[str, Any]]) -> dict[tuple[str, str], list[list[str]]]:
    if config.google_service_account_file is None:
        raise MetricsUnavailable(
            "Не настроен GOOGLE_SERVICE_ACCOUNT_FILE. Нужен JSON-ключ сервисного аккаунта Google, "
            "а саму таблицу надо расшарить на email этого сервисного аккаунта."
        )
    if not config.google_service_account_file.exists():
        raise MetricsUnavailable(f"Файл сервисного аккаунта не найден: {config.google_service_account_file}")

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise MetricsUnavailable(
            "Не установлены библиотеки Google API. Запусти установку зависимостей проекта: pip install -e ."
        ) from exc

    credentials = service_account.Credentials.from_service_account_file(
        str(config.google_service_account_file),
        scopes=[SHEETS_READONLY_SCOPE],
    )
    service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
    result: dict[tuple[str, str], list[list[str]]] = {}

    for source in sources:
        spreadsheet_id = str(source.get("spreadsheet_id") or _spreadsheet_id_from_url(str(source.get("spreadsheet_url") or "")))
        source_name = str(source.get("name") or spreadsheet_id or "Google Sheet")
        if not spreadsheet_id:
            continue
        for sheet in source.get("sheets", []):
            sheet_name = str(sheet.get("name") or "").strip()
            cell_range = str(sheet.get("range") or "A1:ZZ1000").strip()
            if not sheet_name:
                continue
            a1_range = f"{_quote_sheet_name(sheet_name)}!{cell_range}"
            response = (
                service.spreadsheets()
                .values()
                .get(spreadsheetId=spreadsheet_id, range=a1_range, valueRenderOption="FORMATTED_VALUE")
                .execute()
            )
            result[(source_name, sheet_name)] = response.get("values", [])

    return result


async def _generate_answer(config: Config, request_text: str, context: str) -> str:
    if not config.openai_api_key:
        return _fallback_answer(context)

    payload = {
        "model": config.openai_chat_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Ты аналитик метрик в Telegram-боте Ивана. Отвечай по-русски, кратко и точно. "
                    "Используй только данные из контекста Google Sheets. Если точной цифры нет в контексте, скажи это. "
                    "Для план/факт сравнения явно называй дату, показатель, план, факт и разницу."
                ),
            },
            {
                "role": "user",
                "content": f"Контекст Google Sheets:\n{context}\n\nЗапрос:\n{request_text}",
            },
        ],
        "temperature": 0.1,
    }
    headers = {"Authorization": f"Bearer {config.openai_api_key}", "Content-Type": "application/json"}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.post("https://api.openai.com/v1/chat/completions", json=payload) as response:
            data = await response.json(content_type=None)
            if response.status >= 400:
                detail = data.get("error", {}).get("message") if isinstance(data, dict) else None
                raise MetricsUnavailable(detail or f"OpenAI request failed with HTTP {response.status}")

    try:
        return str(data["choices"][0]["message"]["content"]).strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise MetricsUnavailable("OpenAI не вернул текст ответа по метрикам.") from exc


def _parse_wide_sheet(source: str, sheet: str, rows: list[list[str]]) -> list[MetricSeries]:
    series: list[MetricSeries] = []
    current_block = ""
    headers: list[str] = []

    for row in rows:
        padded = [str(cell or "").strip() for cell in row]
        row_block = padded[0] if padded else ""
        label = padded[1] if len(padded) > 1 else ""
        tail = padded[2:] if len(padded) > 2 else []
        if label and _looks_like_date_header(tail):
            current_block = label
            headers = tail
            continue
        if not current_block or not headers or not label:
            continue

        block = row_block or current_block
        if row_block:
            current_block = row_block

        points = []
        for header, value in zip(headers, tail):
            clean_value = str(value or "").strip()
            if not header or not clean_value:
                continue
            points.append(MetricPoint(label=header, raw_value=clean_value, number=_parse_number(clean_value)))
        if points:
            series.append(MetricSeries(source=source, sheet=sheet, block=block, metric=label, points=tuple(points)))

    return series


def _parse_table_sheet(source: str, sheet: str, rows: list[list[str]], kind: str) -> TableSheet:
    header_index = 0
    for index, row in enumerate(rows[:20]):
        if sum(1 for cell in row if str(cell or "").strip()) >= 2:
            header_index = index
            break

    headers = [_clean_header(cell, index) for index, cell in enumerate(rows[header_index])]
    output_rows = []
    for row in rows[header_index + 1 :]:
        if not any(str(cell or "").strip() for cell in row):
            continue
        values = [str(cell or "").strip() for cell in row]
        record = {
            headers[index] if index < len(headers) else f"Столбец {index + 1}": values[index]
            for index in range(max(len(headers), len(values)))
            if index < len(values) and values[index]
        }
        if record:
            output_rows.append(record)

    return TableSheet(source=source, sheet=sheet, headers=tuple(headers), rows=tuple(output_rows), kind=kind)


def _rank_series(series: tuple[MetricSeries, ...], request_text: str) -> list[MetricSeries]:
    query = _normalize_text(request_text)
    scored = []
    for item in series:
        haystack = _normalize_text(f"{item.sheet} {item.block} {item.metric}")
        score = sum(3 for token in query.split() if len(token) > 2 and token in haystack)
        if not score and any(word in haystack for word in ("поездк", "заказ", "водител", "клиент")):
            score = 1
        scored.append((score, item))
    return [item for score, item in sorted(scored, key=lambda pair: pair[0], reverse=True) if score > 0]


def _matched_table_rows(table: TableSheet, request_text: str) -> list[dict[str, str]]:
    tokens = [token for token in _normalize_text(request_text).split() if len(token) >= 4]
    if not tokens:
        return []
    matched = []
    for row in table.rows:
        haystack = _normalize_text(" ".join(row.values()))
        if any(token in haystack for token in tokens):
            matched.append(row)
    return matched


def _table_summary(table: TableSheet) -> str:
    if table.sheet == "Контрагенты":
        capacity = 0.0
        signed = 0
        for row in table.rows:
            capacity += _parse_number(row.get("Капасити водителей", "")) or 0
            if str(row.get("Письмо направили", "")).strip().lower() == "да":
                signed += 1
        return f"{len(table.rows)} строк, суммарное капасити {capacity:g}, письмо направили: {signed}"
    if table.sheet == "Прогнозы":
        return f"{len(table.rows)} строк план/факта по таксопаркам"
    if table.sheet == "Прозвон таксопарков":
        return f"{len(table.rows)} строк заметок по прозвону"
    return f"{len(table.rows)} строк"


def _fallback_answer(context: str) -> str:
    lines = context.splitlines()
    useful = [line for line in lines if line.startswith("- ") or "строк" in line]
    if not useful:
        return "Метрики загрузил, но не нашел подходящих цифр под запрос."
    return "Нашел в Google Sheets:\n" + "\n".join(useful[:12])


def _latest_point(points: list[MetricPoint]) -> MetricPoint | None:
    return points[-1] if points else None


def _previous_point(points: list[MetricPoint]) -> MetricPoint | None:
    return points[-2] if len(points) >= 2 else None


def _format_delta(latest: MetricPoint, previous: MetricPoint | None) -> str:
    if latest.number is None or previous is None or previous.number is None:
        return ""
    delta = latest.number - previous.number
    sign = "+" if delta > 0 else ""
    return f" ({sign}{delta:g} к {previous.label})"


def _compact_row(row: dict[str, str], headers: tuple[str, ...]) -> str:
    parts = []
    for header in headers[:10]:
        value = row.get(header)
        if value:
            parts.append(f"{header}: {value}")
    return "; ".join(parts)


def _clean_header(value: Any, index: int) -> str:
    text = str(value or "").strip()
    return text or f"Столбец {index + 1}"


def _looks_like_date_header(values: list[str]) -> bool:
    non_empty = [value for value in values if value]
    if len(non_empty) < 3:
        return False
    return sum(1 for value in non_empty if re.search(r"\d{1,2}[./-]\d|[а-яё]", value, re.I)) >= 3


def _parse_number(value: str) -> float | None:
    text = str(value or "").strip().replace("\xa0", " ").replace(" ", "")
    if not text or text in {"-", "-."} or text.startswith("-"):
        if re.fullmatch(r"-+", text):
            return None
    text = text.rstrip("%").replace(",", ".")
    text = re.sub(r"[^0-9.+-]", "", text)
    if not text or text in {".", "+", "-"}:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return number


def _normalize_text(value: str) -> str:
    text = str(value or "").lower().replace("ё", "е")
    text = re.sub(r"[^0-9a-zа-я_]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _spreadsheet_id_from_url(value: str) -> str:
    match = re.search(r"/spreadsheets/d/([^/]+)", value)
    return match.group(1) if match else value.strip()


def _quote_sheet_name(name: str) -> str:
    return "'" + name.replace("'", "''") + "'"


def _trim_empty(lines: list[str]) -> list[str]:
    while lines and not lines[-1].strip():
        lines.pop()
    return lines
