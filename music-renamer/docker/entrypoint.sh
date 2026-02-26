#!/usr/bin/env bash
set -euo pipefail

mkdir -p /config /library /inbox

# Generate beets config if missing
if [ ! -f /config/config.yaml ]; then
  echo "Generating /config/config.yaml from template..."
  cp /app/beets/config.template.yaml /config/config.yaml
fi

export BEETSDIR=/config  # point beets to /config per official docs
# Start the Flask app via gunicorn (LAN only; no public exposure here)
exec gunicorn -b 0.0.0.0:8080 app.app:app
