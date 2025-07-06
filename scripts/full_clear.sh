#!/bin/bash

# ---
# File: scripts/full_clear.sh
# Purpose: Remove caches, flush Redis, regenerate Prisma client for a clean local environment
# ---

set -e  # Exit on error

echo "Removing all __pycache__ directories and .pyc files..."
find . -type d -name "__pycache__" -exec rm -rf {} +
find . -name "*.pyc" -delete

echo "Flushing ALL Redis keys from ALL databases..."
redis-cli FLUSHALL

echo "Regenerating Prisma Python client..."
prisma generate

echo "All caches cleared and client regenerated."
