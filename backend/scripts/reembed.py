"""Re-embed every resume chunk with the current EMBEDDING_PROVIDER (after switching models).

Changing EMBEDDING_DIMENSIONS also needs a migration that alters resume_chunks.embedding to vector(N).
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select  # noqa: E402

from app.core.db import dispose_engine, system_session  # noqa: E402
from app.integrations.embeddings import get_embeddings  # noqa: E402
from app.models import ResumeChunk  # noqa: E402


async def main() -> None:
    emb = get_embeddings()
    async with system_session() as s:
        chunks = (await s.execute(select(ResumeChunk))).scalars().all()
        for i in range(0, len(chunks), 32):
            batch = chunks[i:i + 32]
            for c, v in zip(batch, await emb.embed_documents([c.content for c in batch]), strict=True):
                c.embedding, c.embedding_model = v, emb.model
    print(f"re-embedded {len(chunks)} chunks with {emb.model}; re-run matching to refresh scores")
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
