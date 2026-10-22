import json
import sqlite3
import tempfile
import zipfile
from types import SimpleNamespace

import pytest

from taste import cli, seed
from taste.library import db, paths


def add(conn, source, key, thumbs=None, meta=None, page="https://ex.test/p", asset="", lic="CC0", coll=None):
    iid = key.replace(":", "")
    thumb = None
    if thumbs is not None:
        thumb = f"thumbs/{iid}.jpg"
        (thumbs / f"{iid}.jpg").write_bytes(b"jpg-" + iid.encode())
    conn.execute("INSERT INTO items(id,key,source,kind,title,page_url,asset_url,thumb,tags,meta,license,added_at,last_seen)"
                 " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 (iid, key, source, "image", f"title {key}", page, asset, thumb, '["wood"]',
                  json.dumps(meta or {}), lic, "t", "t"))
    if coll:
        conn.execute("INSERT OR IGNORE INTO collections(id,slug,source,kind,title) VALUES (?,?,?,?,?)",
                     (coll, coll, source, "image", coll))
        conn.execute("INSERT INTO item_collections(item,collection) VALUES (?,?)", (iid, coll))
    conn.commit()
    return iid


@pytest.fixture
def lib(tmp_path):
    thumbs = tmp_path / "thumbs"; thumbs.mkdir()
    conn = db.connect(tmp_path / "lib.db")
    for slug in ("polyhaven", "cosmos", "metalforge", "mine"):
        conn.execute("INSERT INTO sources(slug, title, tier, policy) VALUES (?,?,?,?)", (slug, slug, 1, "sync"))
    ph = add(conn, "polyhaven", "ph:1", thumbs, coll="ph-coll")
    add(conn, "cosmos", "cos:1", thumbs, coll="cos-coll")
    add(conn, "metalforge", "mf:1", thumbs)
    add(conn, "mine", "me:1", thumbs)
    add(conn, "polyhaven", "ph:2", thumbs, meta={"private": True}, coll="priv-coll")
    return SimpleNamespace(conn=conn, thumbs=thumbs, ph=ph)


def extract(z, name):
    return z.extract(name, tempfile.mkdtemp())


def test_seed_ships_files_links_and_nothing_else(tmp_path, lib):
    rep = seed.build_seed(lib.conn, lib.thumbs, tmp_path / "s.zip")
    assert (rep.files, rep.links, rep.skipped) == (1, 1, 3)
    z = zipfile.ZipFile(tmp_path / "s.zip")
    assert [n for n in z.namelist() if n.startswith("thumbs/")] == ["thumbs/ph1.jpg"]
    c = sqlite3.connect(extract(z, "seed.db"))
    rows = c.execute("select source, thumb, meta from items").fetchall()
    assert sorted((s, t) for s, t, _ in rows) == [("cosmos", None), ("polyhaven", "thumbs/ph1.jpg")]
    assert json.loads(next(m for s, _, m in rows if s == "cosmos"))["shipping"] == "link"
    assert [r[0] for r in c.execute("select slug from collections order by slug")] == ["cos-coll", "ph-coll"]
    assert c.execute("select count(*) from item_collections").fetchone()[0] == 2


def test_install_keeps_user_rows_and_thumbs(tmp_path, lib):
    seed.build_seed(lib.conn, lib.thumbs, tmp_path / "s.zip")
    mine_thumbs = tmp_path / "t2"; mine_thumbs.mkdir()
    conn = db.connect(tmp_path / "user.db")
    add(conn, "mine", "me:9", mine_thumbs)
    add(conn, "cosmos", "cos:1", mine_thumbs)     # user already has this one, with their own thumb
    n = seed.install_seed(tmp_path / "s.zip", conn, mine_thumbs)
    assert n == 2
    assert conn.execute("select count(*) from items where source='mine'").fetchone()[0] == 1
    assert conn.execute("select thumb from items where key='cos:1'").fetchone()[0] == "thumbs/cos1.jpg"
    assert (mine_thumbs / "ph1.jpg").read_bytes() == b"jpg-ph1"
    assert conn.execute("select thumb from items where key='ph:1'").fetchone()[0] == "thumbs/ph1.jpg"
    assert not seed.library_is_empty(conn)
    # FTS finds seeded items, and a second install is harmless
    hits = db.query_items(conn, "wood", source="polyhaven")
    assert [h["key"] for h in hits] == ["ph:1"]
    assert hits[0]["collections"] == ["ph-coll"]
    assert db.get_item(conn, hits[0]["id"])["title"] == "title ph:1"      # sources row came along
    seed.install_seed(tmp_path / "s.zip", conn, mine_thumbs)
    assert conn.execute("select count(*) from items").fetchone()[0] == 3


def test_library_is_empty(tmp_path):
    conn = db.connect(tmp_path / "x.db")
    assert seed.library_is_empty(conn)


def test_seed_install_without_path_downloads(tmp_path, lib, monkeypatch, capsys):
    monkeypatch.setenv("TASTE_DATA", str(tmp_path / "data"))
    seed.build_seed(lib.conn, lib.thumbs, tmp_path / "s.zip")
    got = []
    def fake(url, dest):
        got.append(url); dest.write_bytes((tmp_path / "s.zip").read_bytes())
    monkeypatch.setattr(seed, "download", fake)
    assert cli.main(["seed", "install"]) == 0
    assert got == [seed.SEED_URL]
    assert seed.SEED_URL == "https://github.com/h-3303/taste/releases/latest/download/taste-seed.zip"
    conn = db.connect(paths.db_path())
    assert not seed.library_is_empty(conn)


def test_maintainer_seed_build(tmp_path, lib, monkeypatch):
    monkeypatch.setenv("TASTE_DATA", str(tmp_path / "data"))
    paths.ensure_dirs()
    c = db.connect(paths.db_path())
    add(c, "polyhaven", "ph:1")
    c.close()
    assert cli.main(["maintainer", "seed-build", str(tmp_path / "o.zip")]) == 0
    assert zipfile.is_zipfile(tmp_path / "o.zip")


def test_new_refuses_empty_library(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TASTE_DATA", str(tmp_path / "data"))
    assert cli.main(["new", "demo"]) == 1
    assert "Your library is empty: run `taste seed install` first (or `taste add` your own)" in capsys.readouterr().err
    assert not (tmp_path / "data" / "runs").exists() or not list((tmp_path / "data" / "runs").iterdir())


def test_link_rows_are_scrubbed(tmp_path, lib):
    meta = {"origin": "/home/x/.taste/a.svg", "code": "<svg>scraped</svg>", "css": "a{}", "path": "/p", "file": "/f",
            "images": ["https://ok.test/1.jpg"], "reference_images": ["https://images.are.na/x.jpg"],
            "nested": {"refs": ["https://images.are.na/x.jpg", "/home/x/y.png", "data:image/png;base64,AAA",
                                "https://fine.test/z"], "local": "/etc/passwd"},
            "palette": "warm"}
    add(lib.conn, "curated", "cur:k1", None, meta=meta, asset="/home/x/.taste/cache/curated/k1.svg")
    lib.conn.execute("UPDATE items SET hash='ffee', search_text='origin /home/x/.taste/a.svg' WHERE key='cur:k1'")
    add(lib.conn, "cosmos", "cos:2", None, asset="https://images.are.na/y.jpg")
    add(lib.conn, "cosmos", "cos:3", None, asset="https://cdn.test/ok.jpg")
    lib.conn.commit()
    seed.build_seed(lib.conn, lib.thumbs, tmp_path / "s.zip")
    z = zipfile.ZipFile(tmp_path / "s.zip")
    c = sqlite3.connect(extract(z, "seed.db"))
    dump = "\n".join(str(v) for r in c.execute("select * from items where source != 'polyhaven'") for v in r)
    for bad in ("/home/x", "scraped", "are.na", "/etc/passwd", "data:image", "ffee", "a{}"):
        assert bad not in dump, bad
    r = c.execute("select asset_url, hash, meta from items where key='cur:k1'").fetchone()
    assert r[0] == "" and r[1] is None
    m = json.loads(r[2])
    assert m["shipping"] == "link" and m["palette"] == "warm" and m["nested"] == {"refs": ["https://fine.test/z"]}
    assert c.execute("select asset_url from items where key='cos:3'").fetchone()[0] == "https://cdn.test/ok.jpg"
    assert c.execute("select 1 from items where key='cos:2'").fetchone() is None   # banned asset: never
    assert c.execute("select count(*) from items_fts where items_fts match 'warm'").fetchone()[0] == 1


def test_install_normalises_crafted_thumb(tmp_path):
    src = tmp_path / "seed.db"
    c = db.connect(src)
    c.execute("INSERT INTO sources(slug,title,tier,policy) VALUES ('polyhaven','p',1,'sync')")
    c.execute("INSERT INTO items(id,key,source,kind,title,thumb) VALUES ('a','k:a','polyhaven','image','t','/etc/x')")
    c.commit(); c.close()
    with zipfile.ZipFile(tmp_path / "s.zip", "w") as z:
        z.write(src, "seed.db"); z.writestr("thumbs/x", b"1")
    conn = db.connect(tmp_path / "u.db")
    seed.install_seed(tmp_path / "s.zip", conn, tmp_path / "th")
    assert conn.execute("select thumb from items where key='k:a'").fetchone()[0] == "thumbs/x"
    assert (tmp_path / "th" / "x").read_bytes() == b"1"
