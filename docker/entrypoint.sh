#!/usr/bin/env bash
set -euo pipefail

# Ensure folders exist (mapped din compose)
mkdir -p /inbox /library

exec gunicorn -b 0.0.0.0:8080 app.app:app