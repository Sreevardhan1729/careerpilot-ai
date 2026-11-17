# CareerPilot AI — local development. No database, Docker or API keys required (embedded Postgres + rule-based mode).
.PHONY: setup migrate backend frontend test lint eval openapi

setup:            ## install backend + frontend deps, create the embedded DB and run migrations
	cd backend && uv sync && uv run python scripts/migrate.py && uv run python -m scripts.seed
	@if [ -f frontend/package.json ]; then cd frontend && pnpm install; fi

migrate:
	cd backend && uv run python scripts/migrate.py

backend:          ## API on http://localhost:8000 (docs at /api/v1/docs)
	cd backend && uv run uvicorn app.main:app --reload --port 8000

frontend:         ## UI on http://localhost:3000
	cd frontend && pnpm dev

test:
	cd backend && uv run pytest -q
	@if [ -f frontend/package.json ]; then cd frontend && pnpm test; fi

lint:
	cd backend && uv run ruff check app tests scripts alembic

eval:
	cd backend && uv run python -m evals.run jd_extraction

openapi:
	cd backend && uv run python -I scripts/export_openapi.py ../frontend/openapi.json
