"""Re-encrypt stored OAuth tokens with the first key in TOKEN_ENCRYPTION_KEYS (docs/SECURITY.md §4)."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select  # noqa: E402

from app.core import crypto  # noqa: E402
from app.core.db import dispose_engine, system_session  # noqa: E402
from app.models import OAuthConnection  # noqa: E402


async def main() -> None:
    n = 0
    async with system_session() as s:
        for conn in (await s.execute(select(OAuthConnection))).scalars():
            if conn.access_token_enc:
                conn.access_token_enc, conn.token_key_id = crypto.rotate(conn.access_token_enc)
            if conn.refresh_token_enc:
                conn.refresh_token_enc, _ = crypto.rotate(conn.refresh_token_enc)
            n += 1
    print(f"rotated {n} connection(s); you can now remove the old key")
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
