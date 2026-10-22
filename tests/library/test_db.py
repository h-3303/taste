import sqlite3

import pytest

from taste.library import db
from taste.library.models import CollectionDraft, ItemDraft, SourceInfo

SRC = SourceInfo("polyhaven", "Poly Haven", "https://polyhaven.com", 1)


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    db.upsert_source(c, SRC)
    return c


def _item(key="polyhaven:a", title="Aerial Asphalt", tags=("road", "cracked")):
    return ItemDraft(key=key, kind="texture", title=title, page_url="https://polyhaven.com/a/a",
                     asset_url="https://api.polyhaven.com/files/a", thumb_url="https://cdn/x.png",
                     tags=list(tags), meta={"maps": ["Diffuse"], "authors": ["Rob"]}, license="CC0")


def test_schema_has_fts(conn):
    names = {r[0] for r in conn.execute("select name from sqlite_master")}
    assert {"sources", "collections", "items", "item_collections", "items_fts", "cache"} <= names


def test_upsert_collection_is_stable(conn):
    c = CollectionDraft("polyhaven/road", "texture", "Poly Haven: road", languages=["industrial"])
    a = db.upsert_collection(conn, "polyhaven", c)
    b = db.upsert_collection(conn, "polyhaven", c)
    assert a == b
    row = db.get_collection(conn, "polyhaven/road")
    assert row["languages"] == ["industrial"] and row["kind"] == "texture"


def test_upsert_item_once_with_two_memberships(conn):
    c1 = db.upsert_collection(conn, "polyhaven", CollectionDraft("polyhaven/road", "texture", "road"))
    c2 = db.upsert_collection(conn, "polyhaven", CollectionDraft("polyhaven/floor", "texture", "floor"))
    iid, created = db.upsert_item(conn, "polyhaven", _item(), c1, "2026-10-07T00:00:00Z")
    iid2, created2 = db.upsert_item(conn, "polyhaven", _item(title="Aerial Asphalt 01"), c2, "2026-10-08T00:00:00Z")
    assert created and not created2 and iid == iid2
    row = db.get_item(conn, iid)
    assert row["title"] == "Aerial Asphalt 01"            # latest title wins
    assert sorted(row["collections"]) == ["polyhaven/floor", "polyhaven/road"]
    assert row["tags"] == ["road", "cracked"] and row["meta"]["maps"] == ["Diffuse"]
    assert row["last_seen"] == "2026-10-08T00:00:00Z" and row["added_at"] == "2026-10-07T00:00:00Z"


def test_query_items_fts_and_filters(conn):
    c1 = db.upsert_collection(conn, "polyhaven", CollectionDraft("polyhaven/road", "texture", "road"))
    db.upsert_item(conn, "polyhaven", _item(), c1, "t")
    db.upsert_item(conn, "polyhaven", _item(key="polyhaven:b", title="Red Brick", tags=("wall",)), c1, "t")
    hits = db.query_items(conn, '"cracked"')
    assert [h["title"] for h in hits] == ["Aerial Asphalt"]
    assert db.query_items(conn, None, kind="texture", collection="polyhaven/road") and \
        db.query_items(conn, None, kind="font") == []
    assert {h["title"] for h in db.query_items(conn, '"road"')} == {"Aerial Asphalt", "Red Brick"}   # collection slug is searchable


def test_query_collapses_same_hash(conn):
    c1 = db.upsert_collection(conn, "polyhaven", CollectionDraft("polyhaven/road", "texture", "road"))
    a, _ = db.upsert_item(conn, "polyhaven", _item(), c1, "t")
    b, _ = db.upsert_item(conn, "polyhaven", _item(key="polyhaven:dup", title="Aerial Asphalt copy"), c1, "t")
    db.set_thumb(conn, a, "thumbs/a.jpg", "ffff")
    db.set_thumb(conn, b, "thumbs/b.jpg", "ffff")
    assert len(db.query_items(conn, None, kind="texture")) == 1


def test_stats_and_missing_thumbs(conn):
    c1 = db.upsert_collection(conn, "polyhaven", CollectionDraft("polyhaven/road", "texture", "road"))
    a, _ = db.upsert_item(conn, "polyhaven", _item(), c1, "t")
    db.finish_collection(conn, c1, "t")
    s = db.stats(conn)
    assert s["items"] == 1 and s["collections"] == 1 and s["by_kind"] == {"texture": 1}
    assert [r["id"] for r in db.items_without_thumb(conn)] == [a]
    assert db.get_collection(conn, "polyhaven/road")["item_count"] == 1


def test_language_filter(conn):
    c = db.upsert_collection(conn, "polyhaven", CollectionDraft("curated/swiss", "image", "Swiss", languages=["swiss international"]))
    db.upsert_item(conn, "polyhaven", _item(key="k"), c, "t")
    assert len(db.query_items(conn, None, language="swiss international")) == 1
    assert db.query_items(conn, None, language="y2k chrome") == []
    assert [x["slug"] for x in db.list_collections(conn, language="swiss international")] == ["curated/swiss"]
