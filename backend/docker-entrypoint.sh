#!/bin/sh
# Migrate under an advisory lock, then serve with exactly one worker (in-process task runner + rate limiter).
set -e
python scripts/migrate.py
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1 --proxy-headers --forwarded-allow-ips='*'
