"""Seed the shared skill taxonomy (idempotent). Usage: uv run python -m scripts.seed"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.db import dispose_engine  # noqa: E402
from app.services.seed import seed_taxonomy  # noqa: E402


async def main() -> None:
    print(f"seeded {await seed_taxonomy()} skills")
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
