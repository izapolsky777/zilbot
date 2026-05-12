# Codex Telegram Work Bot

Telegram bot for work chats: watches group messages, recognizes tasks/promises, keeps a local task ledger, and exports a Codex-readable inbox.

## What it does

- Reads messages in Telegram groups where the bot is present.
- Distinguishes the owner from colleagues by Telegram user id.
- Detects simple Russian task and promise patterns.
- Stores chats, people, messages, observations, and reminders in SQLite.
- Provides private commands for the owner:
  - `/whoami` shows your Telegram id.
  - `/digest` shows recent promises and assignments.
  - `/tasks` shows open tasks.
  - `/remind <task id>` sends a reminder into the original chat.
- Turns private messages from the owner into Codex requests.
- Turns private voice messages from the owner into Codex requests after speech-to-text transcription.
- Answers private voice/text questions about Google Sheets metrics and can send simple charts.
- Exports `data/codex_inbox.md` and `data/codex_inbox.json` for Codex review.
- Exports `data/codex_requests.md` and `data/codex_requests.json` for Telegram-to-Codex requests.

## Telegram setup

1. Create a bot with BotFather and copy the token.
2. In BotFather, turn group privacy off:
   - `/setprivacy`
   - select the bot
   - choose `Disable`
3. Add the bot to your work chat.
4. If you want it to write reminders, give it permission to send messages.
5. Send `/whoami` to the bot in private chat and put your id into `.env`.

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
```

Edit `.env`:

```bash
TELEGRAM_BOT_TOKEN=123456:...
OWNER_TELEGRAM_ID=123456789
OPENAI_API_KEY=sk-...
```

`OPENAI_API_KEY` is required only for voice message transcription.

## Google Sheets metrics

The bot can answer private questions like:

```text
Сколько поездок планируется на 12 мая?
Покажи график активных водителей.
Какой план/факт по НикВаТакс?
```

Production access uses the Google Sheets API with a service account. Do not put a Google email password into the bot.

1. Create a Google Cloud service account and JSON key.
2. Enable Google Sheets API for the project.
3. Share the spreadsheet with the service account email as Viewer.
4. Put the JSON key somewhere under ignored runtime data, for example `data/google-service-account.json`.
5. Configure `.env`:

```bash
GOOGLE_SERVICE_ACCOUNT_FILE=data/google-service-account.json
METRICS_SOURCES_PATH=data/metrics_sources.json
METRICS_CHART_DIR=data/metric_charts
```

The current default source is the “Беларусь Supply” spreadsheet. To override or add more sources, copy `metrics_sources.example.json` to `data/metrics_sources.json` and edit sheet names, ranges, or spreadsheet ids.

Run:

```bash
codex-tg-bot
```

## Codex workflow

The bot writes its current summary to:

- `data/codex_inbox.md`
- `data/codex_inbox.json`
- `data/codex_requests.md`
- `data/codex_requests.json`

Open `data/codex_inbox.md` in Codex whenever you want a compact briefing. A future step can add a Codex heartbeat automation that periodically reads this file and surfaces reminders in this thread.

## Local dashboard

The project includes a browser dashboard that refreshes from the bot database automatically:

```bash
python3 dashboard/server.py
```

Then open:

```text
http://localhost:8765/
```

The page reads the bot SQLite ledger every few seconds, so new Telegram observations appear without reloading the tab. You can also edit task text, assignees, due dates, and your own labels for Telegram accounts directly on the page.

To use Telegram as a Codex bridge:

1. Send a normal private message to the bot.
2. The bot saves it as a pending request and replies with a request number.
3. In Codex, list pending requests:

```bash
PYTHONPATH=src .venv/bin/python -m codex_tg_bot.bridge pending
```

4. Send an answer back to Telegram:

```bash
PYTHONPATH=src .venv/bin/python -m codex_tg_bot.bridge reply 1 "Готово, вот результат..."
```

You can also send a private voice message to the bot. The bot downloads the Telegram voice file, transcribes it, saves the transcript as the Codex request, and replies with the transcript preview.

## Deploying updates to the VPS

The production bot and dashboard run on the VPS at `31.56.177.35` from:

```text
/opt/codex-telegram-bot
```

After changing bot code in `src/` or dashboard code in `dashboard/`, deploy the local project to the server:

```bash
./scripts/deploy_to_vps.sh
```

The deploy script syncs the project to the VPS, updates the Python package, and restarts both services:

- `codex-telegram-bot`
- `codex-telegram-dashboard`
- `codex-telegram-openai-worker`

The Telegram bot receives Telegram updates in real time. The OpenAI worker is a backup loop for pending private AI requests and runs every 30 seconds by default (`OPENAI_WORKER_INTERVAL_SECONDS=30`).

It preserves runtime data on the server by not syncing `data/`. It also skips `.venv`, Git metadata, Python caches, and build artifacts. The local `.env` is synced so service settings can be updated from this project.

The dashboard is exposed on the server only locally. From this Mac, open a tunnel:

```bash
ssh -N -L 8766:127.0.0.1:8765 -i ~/.ssh/codex_hostvds_deploy root@31.56.177.35
```

Then open:

```text
http://127.0.0.1:8766/
```

## Current limits

This starter version uses conservative rule-based extraction for Russian work-chat phrasing. It is intentionally easy to inspect and extend. For better recall, add an LLM extractor later, but keep the SQLite ledger and review flow unchanged.
