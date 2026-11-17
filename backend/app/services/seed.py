"""Idempotent seed of the shared skill taxonomy (and nothing user-specific)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.db import system_session
from app.domain.skills import get_taxonomy
from app.models import Skill


async def seed_taxonomy() -> int:
    tax = get_taxonomy()
    async with system_session() as s:
        rows = [{"canonical_name": e.canonical, "slug": e.slug, "category": e.category, "aliases": list(e.aliases)}
                for e in tax.entries.values()]
        stmt = insert(Skill).values(rows)
        await s.execute(stmt.on_conflict_do_update(index_elements=[Skill.canonical_name],
                                                   set_={"aliases": stmt.excluded.aliases, "category": stmt.excluded.category}))
        ids = dict((await s.execute(select(Skill.canonical_name, Skill.id))).all())
        for child, parent in tax.parent.items():
            if child in ids and parent in ids:
                skill = await s.get(Skill, ids[child])
                skill.parent_id = ids[parent]
        return len(rows)
