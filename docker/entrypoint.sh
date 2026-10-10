#!/usr/bin/env bash
set -euo pipefail

# Ensure every inbox directory and the library output dir exist.
# MUSIC_INBOXES is a colon-separated list; MUSIC_INBOX is the legacy fallback.
_INBOXES="${MUSIC_INBOXES:-${MUSIC_INBOX:-/inbox}}"
IFS=':' read -ra _DIRS <<< "${_INBOXES}"
for _DIR in "${_DIRS[@]}"; do
  mkdir -p "${_DIR}"
done
mkdir -p /library

exec gunicorn -b 0.0.0.0:8080 app.app:app
