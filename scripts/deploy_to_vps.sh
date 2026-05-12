#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVER_HOST="${CODEX_BOT_SERVER_HOST:-31.56.177.35}"
SERVER_USER="${CODEX_BOT_SERVER_USER:-root}"
SERVER_DIR="${CODEX_BOT_SERVER_DIR:-/opt/codex-telegram-bot}"
SSH_KEY="${CODEX_BOT_SSH_KEY:-$HOME/.ssh/codex_hostvds_deploy}"
KNOWN_HOSTS="${CODEX_BOT_KNOWN_HOSTS:-/tmp/codex_known_hosts_deploy}"

SSH_OPTS=(
  -i "$SSH_KEY"
  -o StrictHostKeyChecking=no
  -o UserKnownHostsFile="$KNOWN_HOSTS"
)

if [[ ! -f "$SSH_KEY" ]]; then
  echo "SSH key not found: $SSH_KEY" >&2
  exit 1
fi

echo "Deploying bot and dashboard to ${SERVER_USER}@${SERVER_HOST}:${SERVER_DIR}"

ssh "${SSH_OPTS[@]}" "${SERVER_USER}@${SERVER_HOST}" "mkdir -p '$SERVER_DIR'"

rsync -az --delete \
  --exclude '.git' \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '*.egg-info' \
  --exclude 'data/' \
  -e "ssh -i '$SSH_KEY' -o StrictHostKeyChecking=no -o UserKnownHostsFile='$KNOWN_HOSTS'" \
  "$PROJECT_ROOT/" "${SERVER_USER}@${SERVER_HOST}:${SERVER_DIR}/"

ssh "${SSH_OPTS[@]}" "${SERVER_USER}@${SERVER_HOST}" "cd '$SERVER_DIR' && \
  mkdir -p data/voice && \
  python3 -m venv .venv && \
  .venv/bin/python -m pip install --upgrade pip setuptools wheel >/dev/null && \
  .venv/bin/pip install -e . >/dev/null && \
  cat >/etc/systemd/system/codex-telegram-openai-worker.service <<'SERVICE_EOF'
[Unit]
Description=Codex Telegram OpenAI Pending Request Worker
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/codex-telegram-bot
Environment=PYTHONPATH=src
ExecStart=/opt/codex-telegram-bot/.venv/bin/python -m codex_tg_bot.openai_worker
Restart=always
RestartSec=5
User=root

[Install]
WantedBy=multi-user.target
SERVICE_EOF
  systemctl daemon-reload && \
  systemctl enable --now codex-telegram-openai-worker >/dev/null && \
  systemctl restart codex-telegram-bot codex-telegram-dashboard codex-telegram-openai-worker && \
  systemctl --no-pager --full status codex-telegram-bot codex-telegram-dashboard codex-telegram-openai-worker | sed -n '1,70p'"

echo
echo "Deploy finished."
echo "Dashboard tunnel, if needed:"
echo "ssh -N -L 8766:127.0.0.1:8765 -i '$SSH_KEY' ${SERVER_USER}@${SERVER_HOST}"
