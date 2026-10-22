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
