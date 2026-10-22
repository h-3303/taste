import json

import pytest

from taste import cli, config
from taste.boards import cli as boards_cli


def _png(p):
    from PIL import Image
    Image.new("RGB", (8, 8), "red").save(p)


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("TASTE_DATA", str(tmp_path))
    return tmp_path


def test_version(capsys):
    assert cli.main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == "taste 0.1.0"


def test_lib_search_json_on_empty_library(env, capsys):
    assert cli.main(["lib", "search", "grain", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"match": "none", "results": []}


def test_lib_does_not_expose_sync_or_timer(env, capsys):
    for sub in ("sync", "install-timer"):
        assert cli.main(["lib", sub]) == 1


def test_sync_tier2_slug_is_maintainer_only(env, capsys):
    assert cli.main(["sync", "cosmos"]) == 1
    assert "cosmos needs a renderer: maintainer only (taste maintainer sync)" in capsys.readouterr().err


def test_sync_runs_only_tier1_adapters(env, monkeypatch, capsys):
    from taste.library import cli as lib_cli
    from taste.library.fetch import FakeFetcher
    from taste.library.models import CollectionDraft, ItemDraft, SourceInfo
    from taste.library.sources import base

    class T1:
        info = SourceInfo("t1", "T1", "https://t1.test", 1)
        def collections(self, fetch):
            yield CollectionDraft("t1/all", "palette", "T1"), [ItemDraft("t1:1", "palette", "A", "https://t1.test/1", "https://t1.test/1.hex", meta={"colors": ["#000000"]})]

    class T2:
        info = SourceInfo("t2", "T2", "https://t2.test", 2)
        def collections(self, fetch):
            raise AssertionError("tier 2 must not run")

    monkeypatch.setattr(base, "REGISTRY", {"t1": T1(), "t2": T2()})
    monkeypatch.setattr(lib_cli, "_fetcher", lambda: FakeFetcher())
    assert cli.main(["sync", "--json"]) == 0
    assert cli.main(["lib", "search", "A", "--json"]) == 0


def test_maintainer_sync_reaches_dlib_sync(env, monkeypatch):
    seen = []
    from taste.library import cli as lib_cli
    monkeypatch.setattr(lib_cli, "main", lambda argv=None: seen.append(argv) or 0)
    assert cli.main(["maintainer", "sync", "--full", "cosmos"]) == 0
    assert seen == [["sync", "--full", "cosmos"]]


def test_connect_disconnect_connectors(env, capsys):
    assert cli.main(["connect", "obscura", "--bin", "/x"]) == 0
    assert config.connector("obscura")["bin"] == "/x"
    assert config.connector("obscura")["enabled"] is True
    assert cli.main(["disconnect", "obscura"]) == 0
    c = config.load()["connectors"]["obscura"]
    assert c["enabled"] is False and c["bin"] == "/x"
    capsys.readouterr()
    assert cli.main(["connectors"]) == 0
    assert "obscura" in capsys.readouterr().out


def test_connect_path(env):
    assert cli.main(["connect", "vault", "--path", "/v"]) == 0
    assert config.connector("vault")["path"] == "/v"


def test_boards_commands_at_top_level(env, capsys):
    assert cli.main(["new", "demo"]) == 0
    assert "run:" in capsys.readouterr().out


def test_dlib_pluck_needs_no_dlib_binary(env, monkeypatch, tmp_path):
    monkeypatch.setattr("shutil.which", lambda *_: None)
    assert boards_cli.dlib_pluck("zzzzzz", tmp_path / "out") is None
    from taste.library import curated, db, fetch, paths
    url = "https://src.test/g.png"
    png = tmp_path / "g.png"; _png(png)
    fake = fetch.FakeFetcher(files={url: png.read_bytes()})
    paths.ensure_dirs()
    conn = db.connect(paths.db_path())
    curated.new_collection(conn, "curated/x", "image", "x", [])
    iid = curated.add(conn, "curated/x", url, fake, paths.thumbs_dir(), "Grid", [], "https://src/x", None)
    monkeypatch.setattr(fetch, "Fetcher", lambda: fake)
    got = boards_cli.dlib_pluck(iid, tmp_path / "out")
    assert got and got["title"] == "Grid" and got["page_url"] == "https://src/x"
    assert (tmp_path / "out").exists() and got["path"].startswith(str(tmp_path / "out"))


def test_default_dlib_add_files_without_binary(env, monkeypatch, tmp_path):
    from taste.boards import scout
    monkeypatch.setattr("shutil.which", lambda *_: None)
    img = tmp_path / "k.png"; _png(img)
    scout._default_dlib_add(img, "https://src/k", "Swiss Grid")
    from taste.library import db, paths
    rows = db.connect(paths.db_path()).execute("select count(*) from items").fetchone()[0]
    assert rows == 1


def test_default_dlib_add_respects_no_dlib(env, monkeypatch, tmp_path):
    from taste.boards import scout
    monkeypatch.setenv("MOODBOARDS_NO_DLIB", "1")
    img = tmp_path / "k.png"; _png(img)
    scout._default_dlib_add(img, "https://src/k", "Swiss Grid")
    from taste.library import paths
    assert not paths.db_path().exists()
