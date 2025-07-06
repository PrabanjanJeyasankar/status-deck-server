#!/usr/bin/env bash

# ---
# File: scripts/dev_run.sh
# Purpose: Activate virtual environment, generate Prisma client, and start dev environment with live logs
# ---

# Fail on first error
set -e

echo "Activating venv..."
source venv/bin/activate

echo "Generating Prisma client..."
python -m prisma generate

echo "Starting Status Deck Dev Environment with live logs..."
honcho start
