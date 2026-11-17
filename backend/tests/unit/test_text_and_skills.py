from app.domain.skills import get_taxonomy
from app.domain.text import chunk_text, clean_text, description_hash, normalize_for_match


def test_normalize_for_match_unifies_dashes_quotes_case_and_space():
    assert normalize_for_match("0–2  Years’ Experience") == "0-2 years' experience"


def test_clean_text_strips_zero_width_and_extra_blank_lines():
    raw = "Title​\r\n\r\n\r\n\r\nLine  two   \n"
    assert clean_text(raw) == "Title\n\nLine two"


def test_description_hash_ignores_case_whitespace_and_punctuation():
    assert description_hash("We need Python!\n\nFastAPI.") == description_hash("we need python fastapi")
    assert description_hash("Python 3 years") != description_hash("Python 5 years")


def test_chunk_text_splits_on_line_boundaries_under_limit():
    text = "\n".join(f"- bullet number {i} with some words" for i in range(60))
    chunks = chunk_text(text, max_chars=300)
    assert len(chunks) > 1
    assert all(len(c) <= 300 for c in chunks)
    assert "".join(c.replace("\n", "") for c in chunks).count("bullet number") == 60


def _names(text):
    return sorted({m.entry.canonical for m in get_taxonomy().find_in_text(text)})


def test_aliases_collapse_to_one_canonical_skill():
    tax = get_taxonomy()
    assert tax.canonicalize("postgres").canonical == "PostgreSQL"
    assert tax.canonicalize("Postgre SQL").canonical == "PostgreSQL"
    assert tax.canonicalize("Retrieval-Augmented Generation").canonical == "RAG"
    assert tax.canonicalize("python 3.11").canonical == "Python"
    assert tax.canonicalize("definitely-not-a-skill") is None


def test_find_in_text_matches_case_insensitive_long_aliases():
    assert _names("Experience with fastapi, langchain and vector databases") == ["FastAPI", "LangChain", "Vector Databases"]


def test_short_acronyms_need_uppercase():
    assert "Artificial Intelligence" in _names("Build AI products")
    assert "Artificial Intelligence" not in _names("she said ai was hype")


def test_ambiguous_words_need_list_context():
    assert "Go" not in _names("Go to market with our team")
    assert "Go" in _names("Languages: Python, Go, Rust")
    assert "REST APIs" not in _names("work with the rest of the team")
    assert "REST APIs" in _names("Design REST and GraphQL APIs")
    assert "C" in _names("Strong in C/C++ and Python")


def test_longest_match_wins_at_same_position():
    names = _names("We use Spring Boot and SQL Server")
    assert "Spring Boot" in names and "SQL Server" in names
    assert "SQL" not in names


def test_parent_relation_and_categories():
    tax = get_taxonomy()
    assert tax.related("LangChain", "LangGraph")
    assert tax.related("LangGraph", "LangChain")
    assert not tax.related("Python", "Java")
    assert tax.canonicalize("pgvector").category == "retrieval_vector_db"


def test_domains_detected_and_adjacency():
    tax = get_taxonomy()
    assert tax.domains_in("We are a fintech building payments infrastructure") == {"fintech"}
    assert tax.domains_adjacent("ai_ml", "data_platforms")
    assert not tax.domains_adjacent("fintech", "gaming")


def test_unambiguous_short_tokens_match_lowercase():
    names = _names("tools: git, aws, sql, dbt")
    assert {"Git", "AWS", "SQL", "dbt"} <= set(names)
    assert "Machine Learning" not in _names("html and xml")
