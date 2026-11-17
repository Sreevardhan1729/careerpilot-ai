"""Skill taxonomy: alias normalisation, in-text detection, parent relations, business domains.

Detection rules (keep false positives low):
- aliases of 4+ chars match case-insensitively on word boundaries;
- short alphabetic aliases (<= 3 chars, e.g. "AI", "AWS", "SQL") must appear uppercase or in canonical case;
- ambiguous words ("Go", "C", "R", "REST", "Spring", …) must appear in canonical case AND in a list context
  (adjacent comma, slash, pipe, parenthesis, colon, '&', or "and"/"or").
- at any position the longest alias wins, so "SQL Server" never also yields "SQL".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from app.domain.text import normalize_for_match

TAXONOMY_PATH = Path(__file__).resolve().parents[1] / "data" / "skills_taxonomy.yaml"

# alias (lowercase) -> required surface form (case-sensitive), plus list-context requirement
_LIST_CONTEXT_ONLY: dict[str, str | None] = {
    "c": "C", "r": "R", "go": "Go", "rest": "REST", "render": "Render", "lambda": "Lambda",
    "spring": "Spring", "express": "Express", "node": "Node", "oracle": "Oracle", "swift": "Swift",
    "julia": "Julia", "agents": None, "transformers": None, "shell": None,
}
# Unambiguous short tokens commonly written lowercase in JDs.
_SHORT_ANY_CASE = {"git", "aws", "gcp", "sql", "dbt", "etl", "nlp", "rag", "llm", "llms", "oop", "dsa", "tdd", "faiss"}
_LIST_SEPARATORS = re.compile(r"(^|[,/|()\[\]:;&+•·*-]|\band\b|\bor\b)\s*$", re.IGNORECASE)
_LIST_SEPARATORS_AFTER = re.compile(r"^\s*($|[,/|()\[\]:;&+•·]|\band\b|\bor\b)", re.IGNORECASE)
_VERSION_SUFFIX = re.compile(r"\s*\d+(\.\d+)*\s*$")


def slugify(name: str) -> str:
    s = name.lower().replace("+", "p").replace("#", "sharp").replace(".", "dot")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def _alias_key(text: str) -> str:
    s = normalize_for_match(text)
    s = _VERSION_SUFFIX.sub("", s)
    return re.sub(r"\s+", " ", s.replace("_", " ")).strip()


@dataclass(frozen=True)
class SkillEntry:
    canonical: str
    slug: str
    category: str
    aliases: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SkillMatch:
    entry: SkillEntry
    start: int
    end: int
    matched_text: str


class Taxonomy:
    def __init__(self, data: dict):
        self.version: str = str(data.get("version", "0"))
        self.entries: dict[str, SkillEntry] = {}
        self._by_alias: dict[str, SkillEntry] = {}
        for category, items in (data.get("skills") or {}).items():
            for item in items:
                canonical, _, alias_part = str(item).partition("|")
                canonical = canonical.strip()
                aliases = tuple(a.strip() for a in alias_part.split(",") if a.strip())
                entry = SkillEntry(canonical, slugify(canonical), category, aliases)
                self.entries[canonical] = entry
                for alias in (canonical, *aliases):
                    self._by_alias.setdefault(_alias_key(alias), entry)
        self.parent: dict[str, str] = {}
        for parent, children in (data.get("parents") or {}).items():
            for child in children:
                self.parent[child] = parent
        self.domains: dict[str, tuple[str, ...]] = {
            k: tuple(normalize_for_match(v) for v in vals) for k, vals in (data.get("domains") or {}).items()
        }
        self.domain_adjacency: dict[str, set[str]] = {
            k: set(v) for k, v in (data.get("domain_adjacency") or {}).items()
        }
        self._pattern = self._compile()

    # ---- lookup -------------------------------------------------------------------------------
    def canonicalize(self, name: str | None) -> SkillEntry | None:
        if not name:
            return None
        return self._by_alias.get(_alias_key(name))

    def normalize_name(self, raw: str) -> str:
        entry = self.canonicalize(raw)
        if entry:
            return entry.canonical
        cleaned = re.sub(r"\s+", " ", raw).strip(" .,;:-")
        return cleaned

    def category_of(self, name: str, default: str = "domain_knowledge") -> str:
        entry = self.canonicalize(name)
        return entry.category if entry else default

    def related(self, a: str, b: str) -> bool:
        """True if one is the parent of the other, or both share a parent."""
        pa, pb = self.parent.get(a), self.parent.get(b)
        return a != b and (pa == b or pb == a or (pa is not None and pa == pb))

    # ---- detection ----------------------------------------------------------------------------
    def _compile(self) -> re.Pattern[str]:
        alias_forms = sorted({a for e in self.entries.values() for a in (e.canonical, *e.aliases)}, key=len, reverse=True)
        parts = [re.escape(a).replace(r"\ ", r"\s+") for a in alias_forms]
        return re.compile(r"(?<![A-Za-z0-9+#])(" + "|".join(parts) + r")(?![A-Za-z0-9+#])", re.IGNORECASE)

    def find_in_text(self, text: str) -> list[SkillMatch]:
        matches: list[SkillMatch] = []
        for m in self._pattern.finditer(text):
            surface = m.group(1)
            key = _alias_key(surface)
            entry = self._by_alias.get(key)
            if entry is None or not self._accept(surface, key, entry, text, m.start(1), m.end(1)):
                continue
            matches.append(SkillMatch(entry, m.start(1), m.end(1), surface))
        return matches

    def _accept(self, surface: str, key: str, entry: SkillEntry, text: str, start: int, end: int) -> bool:
        if key in _LIST_CONTEXT_ONLY:
            required = _LIST_CONTEXT_ONLY[key]
            if required is not None and surface != required:
                return False
            before = text[max(0, start - 6):start]
            after = text[end:end + 6]
            line_start = text.rfind("\n", 0, start) + 1
            before_line = text[line_start:start]
            return bool(_LIST_SEPARATORS.search(before) or _LIST_SEPARATORS_AFTER.search(after)) and (
                bool(before_line.strip()) or bool(_LIST_SEPARATORS_AFTER.search(after))
            )
        if len(key) <= 3 and key.isalpha() and key not in _SHORT_ANY_CASE:
            forms = {entry.canonical, *entry.aliases}
            return surface == surface.upper() or (
                surface in forms and (surface != surface.lower() or entry.canonical.islower())
            )
        return True

    def skills_in(self, text: str) -> list[SkillEntry]:
        seen: dict[str, SkillEntry] = {}
        for m in self.find_in_text(text):
            seen.setdefault(m.entry.canonical, m.entry)
        return list(seen.values())

    # ---- domains --------------------------------------------------------------------------------
    def domains_in(self, text: str | None) -> set[str]:
        if not text:
            return set()
        norm = " " + re.sub(r"[^a-z0-9+#.\- ]", " ", normalize_for_match(text)) + " "
        found = set()
        for key, words in self.domains.items():
            if any(re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", norm) for w in words):
                found.add(key)
        return found

    def canonical_domain(self, text: str | None) -> str | None:
        if not text:
            return None
        if text in self.domains:
            return text
        found = self.domains_in(text)
        return sorted(found)[0] if found else None

    def domains_adjacent(self, a: str, b: str) -> bool:
        return b in self.domain_adjacency.get(a, set()) or a in self.domain_adjacency.get(b, set())


@lru_cache
def get_taxonomy() -> Taxonomy:
    with TAXONOMY_PATH.open(encoding="utf-8") as fh:
        return Taxonomy(yaml.safe_load(fh))
