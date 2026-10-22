import json
import sqlite3
import zipfile

import pytest

from taste import cli, importer, seed
from taste.library import db


def add(conn, thumbs, source, key, iid, page="https://ex.test/p", lic="CC0", coll=None):
    (thumbs / f"{iid}.jpg").write_bytes(b"jpg-" + iid.encode())
    conn.execute("INSERT INTO items(id,key,source,kind,title,page_url,asset_url,thumb,tags,meta,license,added_at,last_seen)"
                 " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 (iid, key, source, "image", f"title {key}", page, "", f"thumbs/{iid}.jpg", "[]", "{}", lic, "t", "t"))
    if coll:
        conn.execute("INSERT OR IGNORE INTO collections(id,slug,source,kind,title) VALUES (?,?,?,?,?)",
                     (coll, coll, source, "image", coll))
        conn.execute("INSERT INTO item_collections(item,collection) VALUES (?,?)", (iid, coll))
    conn.commit()


@pytest.fixture
def src(tmp_path):
    d = tmp_path / "dlib"; (d / "thumbs").mkdir(parents=True)
    conn = db.connect(d / "library.db")
    for s in ("cosmos", "metalforge", "curated"):
        conn.execute("INSERT INTO sources(slug,title,tier,policy) VALUES (?,?,?,?)", (s, s, 1, "sync"))
    add(conn, d / "thumbs", "cosmos", "cos:1", "a1", coll="c1")
    add(conn, d / "thumbs", "metalforge", "mf:1", "a2", page="https://mf.test/x")
    add(conn, d / "thumbs", "curated", "cur:1", "a3")
    conn.close()
    return d


@pytest.fixture
def dest(tmp_path):
    (tmp_path / "dthumbs").mkdir()
    return db.connect(tmp_path / "dest.db"), tmp_path / "dthumbs"


def test_import_library_marks_private_and_seed_excludes(tmp_path, src, dest):
    conn, thumbs = dest
    assert importer.import_library(src, conn, thumbs) == 3
    meta = {r["source"]: json.loads(r["meta"]) for r in conn.execute("select source, meta from items")}
    assert meta["metalforge"]["private"] is True
    assert not meta["cosmos"].get("private") and not meta["curated"].get("private")
    assert sorted(p.name for p in thumbs.iterdir()) == ["a1.jpg", "a2.jpg", "a3.jpg"]
    assert conn.execute("select count(*) from item_collections").fetchone()[0] == 1
    seed.build_seed(conn, thumbs, tmp_path / "s.zip")
    z = zipfile.ZipFile(tmp_path / "s.zip"); z.extract("seed.db", tmp_path)
    got = sorted(r[0] for r in sqlite3.connect(tmp_path / "seed.db").execute("select source from items"))
    assert got == ["cosmos", "curated"]


def test_reimport_changes_nothing(src, dest):
    conn, thumbs = dest
    importer.import_library(src, conn, thumbs)
    snap = [tuple(r) for r in conn.execute("select * from items order by key")]
    importer.import_library(src, conn, thumbs)
    assert [tuple(r) for r in conn.execute("select * from items order by key")] == snap
    assert conn.execute("select count(*) from item_collections").fetchone()[0] == 1


def test_existing_key_keeps_its_id_and_id_collisions_remap(src, dest):
    conn, thumbs = dest
    add(conn, thumbs, "cosmos", "cos:1", "zz")            # same key, different id
    add(conn, thumbs, "curated", "other:9", "a3")         # different key squatting on a source id
    importer.import_library(src, conn, thumbs)
    assert conn.execute("select id from items where key='cos:1'").fetchone()[0] == "zz"
    assert conn.execute("select id from items where key='other:9'").fetchone()[0] == "a3"
    new = conn.execute("select id, thumb from items where key='cur:1'").fetchone()
    assert new["id"] != "a3" and new["thumb"] == f"thumbs/{new['id']}.jpg"
    assert (thumbs / f"{new['id']}.jpg").read_bytes() == b"jpg-a3"
    assert (thumbs / "a3.jpg").read_bytes() == b"jpg-a3"   # untouched dest thumb: same bytes here by fixture
    link = conn.execute("select item from item_collections").fetchone()[0]
    assert link == "zz"
    assert (thumbs / "zz.jpg").is_file()


def test_import_runs_skips_existing(tmp_path):
    s = tmp_path / "mb"
    for n in ("one", "two"):
        (s / "runs" / n).mkdir(parents=True); (s / "runs" / n / "f.txt").write_text(n)
    d = tmp_path / "runs"; (d / "one").mkdir(parents=True); (d / "one" / "f.txt").write_text("mine")
    assert importer.import_runs(s, d) == 1
    assert (d / "one" / "f.txt").read_text() == "mine"
    assert (d / "two" / "f.txt").read_text() == "two"
    assert importer.import_runs(s, d) == 0


def test_import_profile_returns_proposals_writes_nothing(tmp_path):
    runs = tmp_path / "runs"
    for n, doc in (("a", {"traits_liked": ["Warm Wood", "grain"], "traits_disliked": ["chrome"]}),
                   ("b", {"traits_liked": ["warm wood"]}), ("c", {})):
        (runs / n).mkdir(parents=True)
        if doc:
            (runs / n / "taste.json").write_text(json.dumps(doc))
    prof = tmp_path / "profile.md"
    props = importer.import_profile(runs, prof)
    assert [(p["id"], p["section"], p["text"], p["default"]) for p in props] == [
        ("i1", "Liked traits", "Warm Wood", False), ("i2", "Liked traits", "grain", False),
        ("i3", "Disliked traits", "chrome", False)]
    assert not prof.exists()


def test_import_project(tmp_path):
    p = tmp_path / "proj"; (p / "design").mkdir(parents=True)
    assert importer.import_project(p) is None
    (p / "design" / "direction.md").write_text("# dir")
    out = importer.import_project(p)
    assert out == p / "design" / "taste.md" and "direction.md" in out.read_text()
    out.write_text("mine")
    assert importer.import_project(p) is None and out.read_text() == "mine"


def test_cli_import(tmp_path, monkeypatch, src, capsys):
    monkeypatch.setenv("TASTE_DATA", str(tmp_path / "data"))
    mb = tmp_path / "mb"; (mb / "runs" / "r1").mkdir(parents=True)
    (mb / "runs" / "r1" / "taste.json").write_text(json.dumps({"traits_liked": ["grain"]}))
    assert cli.main(["import", "--dlib", str(src), "--moodboards", str(mb)]) == 0
    out = capsys.readouterr().out
    assert "3 library" in out and "1 run" in out and "import-proposals.json" in out
    assert json.loads((tmp_path / "data" / "import-proposals.json").read_text())[0]["text"] == "grain"
    assert cli.main(["import"]) == 0


def test_import_library_opens_the_source_read_only(src, dest):
    conn, thumbs = dest
    lib = src / "library.db"
    raw = sqlite3.connect(lib)
    raw.execute("DROP TABLE cache")          # an older dlib without the cache table: import must not add it
    raw.commit(); raw.close()
    before = lib.read_bytes()
    assert importer.import_library(src, conn, thumbs) == 3
    assert lib.read_bytes() == before
    names = {r[0] for r in sqlite3.connect(lib).execute("select name from sqlite_master")}
    assert "cache" not in names


def test_import_library_requires_library_db(tmp_path, monkeypatch, capsys):
    empty = tmp_path / "nolib"; empty.mkdir()
    with pytest.raises(FileNotFoundError, match="no library.db in"):
        importer.import_library(empty, db.connect(tmp_path / "dest.db"), tmp_path / "t")
    assert not (empty / "library.db").exists()
    monkeypatch.setenv("TASTE_DATA", str(tmp_path / "data"))
    assert cli.main(["import", "--dlib", str(empty)]) == 1
    assert f"no library.db in {empty}" in capsys.readouterr().err
    assert not (empty / "library.db").exists()
