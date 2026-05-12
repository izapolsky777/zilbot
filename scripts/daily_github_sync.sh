#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="${DAILY_GITHUB_SYNC_BRANCH:-main}"
INTERVAL_LABEL="${DAILY_GITHUB_SYNC_LABEL:-daily-sync}"
STATE_DIR="${HOME}/.codex-github-sync/zilbot"
LAST_SUCCESS_FILE="${STATE_DIR}/last-success-date"
LOG_FILE="${STATE_DIR}/sync.log"
LOCK_DIR="${STATE_DIR}/lock"

mkdir -p "$STATE_DIR"

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >>"$LOG_FILE"
}

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  log "another sync is already running"
  exit 0
fi
trap 'rmdir "$LOCK_DIR"' EXIT

cd "$PROJECT_ROOT"

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

today="$(date '+%Y-%m-%d')"
last_success=""
if [[ -f "$LAST_SUCCESS_FILE" ]]; then
  last_success="$(cat "$LAST_SUCCESS_FILE" 2>/dev/null || true)"
fi

has_changes=0
if [[ -n "$(git status --porcelain)" ]]; then
  has_changes=1
fi

ahead_count=0
if git rev-parse --verify "origin/${BRANCH}" >/dev/null 2>&1; then
  ahead_count="$(git rev-list --count "origin/${BRANCH}..HEAD" 2>/dev/null || printf '0')"
fi

if [[ "$last_success" == "$today" && "$has_changes" -eq 0 && "${ahead_count:-0}" -eq 0 ]]; then
  exit 0
fi

if ! git ls-remote --exit-code origin "refs/heads/${BRANCH}" >/dev/null 2>&1; then
  log "github is not reachable; will retry later"
  exit 0
fi

git fetch origin "$BRANCH" >/dev/null 2>&1 || {
  log "fetch failed; will retry later"
  exit 0
}

if ! git diff --quiet "HEAD..origin/${BRANCH}"; then
  log "remote has commits not present locally; skipping automatic push"
  exit 0
fi

if [[ "$has_changes" -eq 1 ]]; then
  git add -A
  if ! git diff --cached --quiet; then
    git commit -m "Daily sync ${today}" >/dev/null
    log "created commit for ${today}"
  fi
fi

if git rev-parse --verify "origin/${BRANCH}" >/dev/null 2>&1; then
  ahead_count="$(git rev-list --count "origin/${BRANCH}..HEAD" 2>/dev/null || printf '0')"
else
  ahead_count=1
fi

if [[ "${ahead_count:-0}" -gt 0 ]]; then
  git push origin "$BRANCH" >/dev/null
  log "pushed ${ahead_count} commit(s) to origin/${BRANCH}"
else
  log "no local changes to push"
fi

printf '%s\n' "$today" >"$LAST_SUCCESS_FILE"
