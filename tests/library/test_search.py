from taste.library import db, search
from taste.library.models import CollectionDraft, ItemDraft, SourceInfo


def seed(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.upsert_source(conn, SourceInfo("s", "S", "https://s", 1))
    c = db.upsert_collection(conn, "s", CollectionDraft("s/grain-texture", "texture", "grain"))
    for k, t, tags in [("1", "Risograph grain overlay", ["grain", "riso"]), ("2", "Clean paper", ["paper"]),
                       ("3", "Grainy concrete", ["concrete"])]:
        db.upsert_item(conn, "s", ItemDraft(f"s:{k}", "texture", t, "https://s/p", "https://s/a.jpg", tags=tags), c, "t")
    return conn


def test_fts_query_quotes_and_prefixes():
    assert search.fts_query('"swiss" OR grain-texture') == '"swiss"* "grain"* "texture"*'
    assert search.fts_query("   ") == ""


def test_search_quotes_operators(tmp_path):
    conn = seed(tmp_path)
    assert search.search(conn, 'risograph OR "grain"')          # must not raise, finds the riso item
    assert isinstance(search.search(conn, "NEAR("), list)
    assert search.search(conn, "OR") == []                      # operator-only query matches nothing


def test_search_and_then_or(tmp_path):
    conn = seed(tmp_path)
    titles = [r["title"] for r in search.search(conn, "risograph grain")]
    assert titles[0] == "Risograph grain overlay"
    titles = [r["title"] for r in search.search(conn, "risograph paper")]      # no item has both → OR fallback
    assert set(titles) == {"Risograph grain overlay", "Clean paper"}


def test_search_prefix_matches_grainy(tmp_path):
    conn = seed(tmp_path)
    assert {r["title"] for r in search.search(conn, "grain")} >= {"Risograph grain overlay", "Grainy concrete"}


def test_search_with_mode_reports_all_any_none(tmp_path):
    conn = seed(tmp_path)
    rows, mode = search.search_with_mode(conn, "risograph grain")
    assert mode == "all" and rows[0]["title"] == "Risograph grain overlay"
    rows, mode = search.search_with_mode(conn, "risograph paper")
    assert mode == "any" and {r["title"] for r in rows} == {"Risograph grain overlay", "Clean paper"}
    assert search.search_with_mode(conn, "zzzz qqqq") == ([], "none")
    assert search.search_with_mode(conn, "OR") == ([], "none")
