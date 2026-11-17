#!/bin/sh
# Weekly logical backup (docs/DATABASE_SCHEMA.md §8). Requires pg_dump and DATABASE_URL (postgresql://… form).
set -e
: "${DATABASE_URL:?DATABASE_URL is required}"
URL=$(echo "$DATABASE_URL" | sed 's#postgresql+psycopg://#postgresql://#')
OUT="careerpilot-$(date -u +%Y%m%dT%H%M%SZ).dump"
pg_dump --format=custom --no-owner --no-privileges "$URL" -f "$OUT"
echo "wrote $OUT (restore: pg_restore --no-owner -d <new-url> $OUT && alembic stamp head)"
