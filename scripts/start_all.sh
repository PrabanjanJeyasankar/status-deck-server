#!/usr/bin/env sh
set -euo pipefail

# Run Redis locally inside the container to avoid external services.
# Note: This is best-effort and uses no persistence (ephemeral storage).
redis-server --save "" --appendonly no --bind 0.0.0.0 --port 6379 &

# Apply Prisma migrations before starting runtime processes.
python -m prisma migrate deploy

# Start the monitor worker in the background.
python -m app.monitors.auto_incident_monitor &

# Start the API server in the foreground so the container stays alive.
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
