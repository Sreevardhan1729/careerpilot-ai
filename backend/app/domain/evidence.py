"""Deterministic evidence verification (docs/AGENT_DESIGN.md §3.3)."""

from __future__ import annotations

import re

from rapidfuzz import fuzz

from app.domain.text import normalize_for_match

MIN_SNIPPET_CHARS = 8
FUZZY_THRESHOLD = 92

_NUMBER = re.compile(r"\d+(?:,\d{2,3})*(?:\.\d+)?")
_PREFERRED = re.compile(
    r"\b(nice[\s-]to[\s-]have|good[\s-]to[\s-]have|preferred|preferably|bonus|a plus|is a plus|plus point|"
    r"desirable|ideally|advantageous|an advantage|optional)\b",
    re.IGNORECASE,
)
_MANDATORY = re.compile(
    r"\b(must[\s-]have|must|required|requirements?|mandatory|essential|need to have|minimum|at least|"
    r"strong (?:experience|knowledge|understanding|proficiency)|proficien(?:t|cy) (?:in|with)|"
    r"hands[\s-]on experience|you (?:have|bring)|qualifications|what we(?:'re| are) looking for|"
    r"who you are|we need)\b",
    re.IGNORECASE,
)


_INJECTION = re.compile(
    r"ignore (?:all |any )?(?:previous|prior|above|earlier) (?:instructions|prompts?)|disregard (?:all|any|the|previous)|"
    r"\byou are now\b|\bact as (?:a|an)\b|^\s*(?:system|assistant|developer)\s*:|\b(?:system|assistant)\s*:\s|"
    r"</?untrusted_document|\breport the (?:salary|experience)\b|\bset (?:the )?salary\b|\bnew instructions\b",
    re.IGNORECASE | re.MULTILINE,
)


def looks_like_injection(text: str | None) -> bool:
    """Instruction-like text aimed at a model; never accepted as evidence for a job fact."""
    return bool(text and _INJECTION.search(text))


def verify_snippet(snippet: str | None, source: str, threshold: int = FUZZY_THRESHOLD) -> bool:
    """True if `snippet` occurs in `source` (normalised), allowing small OCR/punctuation differences."""
    if not snippet or looks_like_injection(snippet):
        return False
    s = normalize_for_match(snippet).strip(" .,;:")
    if len(s) < MIN_SNIPPET_CHARS:
        return False
    src = normalize_for_match(source)
    if s in src:
        return True
    return fuzz.partial_ratio(s, src) >= threshold


def source_span(snippet: str | None, source: str) -> str | None:
    """The (normalised) text of the source that a snippet matched, or None. Values are checked against *this*,
    never against the model's own snippet, so a one-character change in the snippet can't smuggle in new values."""
    if not snippet or looks_like_injection(snippet):
        return None
    s = normalize_for_match(snippet).strip(" .,;:")
    if len(s) < MIN_SNIPPET_CHARS:
        return None
    src = normalize_for_match(source)
    idx = src.find(s)
    if idx >= 0:
        return src[idx: idx + len(s)]
    alignment = fuzz.partial_ratio_alignment(s, src)
    if alignment and alignment.score >= FUZZY_THRESHOLD:
        return src[alignment.dest_start: alignment.dest_end]
    return None


def find_snippet_span(snippet: str, source: str) -> tuple[int, int] | None:
    """Locate a verified snippet in the original source (best effort, for highlighting)."""
    idx = source.lower().find(snippet.lower())
    if idx >= 0:
        return idx, idx + len(snippet)
    alignment = fuzz.partial_ratio_alignment(snippet.lower(), source.lower())
    if alignment and alignment.score >= FUZZY_THRESHOLD:
        return alignment.dest_start, alignment.dest_end
    return None


def numbers_in(text: str) -> list[float]:
    return [float(n.replace(",", "")) for n in _NUMBER.findall(text)]


def numbers_supported(value_numbers: list[float], snippet: str) -> bool:
    """Every number in the value must appear in the snippet (e.g. experience 0–2 needs '0' and '2')."""
    present = set(numbers_in(snippet))
    return all(n in present for n in value_numbers)


def importance_cue(context: str) -> str | None:
    """'preferred' wins over 'mandatory' when both cues are present ("Preferred qualifications")."""
    if _PREFERRED.search(context):
        return "preferred"
    if _MANDATORY.search(context):
        return "mandatory"
    return None
