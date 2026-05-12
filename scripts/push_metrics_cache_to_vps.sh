#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVER_HOST="${CODEX_BOT_SERVER_HOST:-31.56.177.35}"
SERVER_USER="${CODEX_BOT_SERVER_USER:-root}"
SERVER_DIR="${CODEX_BOT_SERVER_DIR:-/opt/codex-telegram-bot}"
SSH_KEY="${CODEX_BOT_SSH_KEY:-$HOME/.ssh/codex_hostvds_deploy}"
KNOWN_HOSTS="${CODEX_BOT_KNOWN_HOSTS:-/tmp/codex_known_hosts_deploy}"
LOCAL_CACHE="${METRICS_CACHE_PATH:-$PROJECT_ROOT/data/metrics_cache.json}"
LOCAL_SOURCES="${METRICS_SOURCES_PATH:-$PROJECT_ROOT/data/metrics_sources.json}"

SSH_OPTS=(
  -i "$SSH_KEY"
  -o StrictHostKeyChecking=no
  -o UserKnownHostsFile="$KNOWN_HOSTS"
)

if [[ ! -f "$SSH_KEY" ]]; then
  echo "SSH key not found: $SSH_KEY" >&2
  exit 1
fi

if [[ ! -f "$LOCAL_CACHE" ]]; then
  echo "Metrics cache not found: $LOCAL_CACHE" >&2
  exit 1
fi

ssh "${SSH_OPTS[@]}" "${SERVER_USER}@${SERVER_HOST}" "mkdir -p '$SERVER_DIR/data'"
scp "${SSH_OPTS[@]}" "$LOCAL_CACHE" "${SERVER_USER}@${SERVER_HOST}:$SERVER_DIR/data/metrics_cache.json"

if [[ -f "$LOCAL_SOURCES" ]]; then
  scp "${SSH_OPTS[@]}" "$LOCAL_SOURCES" "${SERVER_USER}@${SERVER_HOST}:$SERVER_DIR/data/metrics_sources.json"
fi

ssh "${SSH_OPTS[@]}" "${SERVER_USER}@${SERVER_HOST}" "systemctl restart codex-telegram-bot codex-telegram-dashboard"

echo "Metrics cache pushed to ${SERVER_USER}@${SERVER_HOST}:${SERVER_DIR}/data/metrics_cache.json"
