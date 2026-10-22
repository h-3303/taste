import re

from . import db

TOKEN = re.compile(r"[A-Za-z0-9]+")
OPERATORS = {"AND", "OR", "NOT", "NEAR"}  # uppercase FTS operator words are dropped, not searched


def fts_query(q: str, joiner: str = " ") -> str:
    toks = [t.lower() for t in TOKEN.findall(q or "") if t not in OPERATORS]
    return joiner.join(f'"{t}"*' for t in toks)


def search_with_mode(conn, q: str | None, kind=None, source=None, collection=None, language=None, limit=40) -> tuple[list[dict], str]:
    """Rows plus how they matched: "all" terms, the OR fallback ("any"), or "none"."""
    fts = fts_query(q) if q else ""
    if q and q.strip() and not fts:
        return [], "none"  # query had only operator words / punctuation
    if not fts:
        rows = db.query_items(conn, None, kind, source, collection, language, limit)
        return rows, "all" if rows else "none"
    rows = db.query_items(conn, fts, kind, source, collection, language, limit)
    if rows:
        return rows, "all"
    if " " in fts:
        rows = db.query_items(conn, fts_query(q, " OR "), kind, source, collection, language, limit)
        if rows:
            return rows, "any"
    return [], "none"


def search(conn, q: str | None, kind=None, source=None, collection=None, language=None, limit=40) -> list[dict]:
    return search_with_mode(conn, q, kind, source, collection, language, limit)[0]
