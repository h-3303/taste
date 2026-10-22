import json

import pytest

from taste.library import cli, db
from taste.library.fetch import FakeFetcher
from taste.library.models import CollectionDraft, ItemDraft, SourceInfo
from taste.library.sources import base


class Demo:
    info = SourceInfo("demo", "Demo", "https://demo.test", 1)

    def collections(self, fetch):
        yield CollectionDraft("demo/all", "palette", "Demo palettes"), [
            ItemDraft("demo:1", "palette", "Rust", "https://demo.test/1", "https://demo.test/1.hex", meta={"colors": ["#230000", "#e18866"]}),
            ItemDraft("demo:2", "palette", "Mint", "https://demo.test/2", "https://demo.test/2.hex", meta={"colors": ["#00ff88"]})]


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("TASTE_DATA", str(tmp_path))
    monkeypatch.setattr(base, "REGISTRY", {"demo": Demo()})
    monkeypatch.setattr(cli, "_fetcher", lambda: FakeFetcher())
    return tmp_path


def test_sync_then_search_and_status(env, capsys):
    assert cli.main(["sync"]) == 0
    out = capsys.readouterr().out
    assert "demo: 1 collections, 2 new" in out
    assert cli.main(["--json", "search", "rust"]) == 0
    hits = json.loads(capsys.readouterr().out)["results"]
    assert hits[0]["title"] == "Rust" and hits[0]["id"]
    assert cli.main(["--json", "status"]) == 0
    s = json.loads(capsys.readouterr().out)
    assert s["items"] == 2 and s["by_kind"] == {"palette": 2}
    assert cli.main(["collections"]) == 0
    assert "demo/all" in capsys.readouterr().out
    assert cli.main(["show", hits[0]["id"]]) == 0
    assert "#230000" in capsys.readouterr().out


def test_search_sheet_writes_pngs(env, capsys):
    cli.main(["sync"])
    assert cli.main(["search", "", "--kind", "palette", "--sheet", str(env / "sheets")]) == 0
    out = capsys.readouterr().out
    assert "sheet-1.png" in out and (env / "sheets" / "sheet-1.png").exists()


def test_unknown_source_is_user_error(env, capsys):
    assert cli.main(["sync", "nope"]) == 1
    assert "unknown source" in capsys.readouterr().err


def test_show_missing_item(env, capsys):
    assert cli.main(["show", "zzzzzz"]) == 1


def test_missing_obscura_exits_2(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("TASTE_DATA", str(tmp_path))
    monkeypatch.setattr("shutil.which", lambda *_: None)
    monkeypatch.setattr(base, "REGISTRY", {"demo": Demo()})
    assert cli.main(["sync"]) == 2
    assert "obscura not found" in capsys.readouterr().err


def test_unusable_data_dir_exits_2(monkeypatch, tmp_path, capsys):
    f = tmp_path / "file"; f.write_text("x")
    monkeypatch.setenv("TASTE_DATA", str(f / "sub"))
    assert cli.main(["status"]) == 2
    assert "data directory not usable" in capsys.readouterr().err


def test_usage_error_exits_1():
    with pytest.raises(SystemExit) as e:
        cli.main(["--nope"])
    assert e.value.code == 1


def test_manual_source_skipped_by_bare_sync_but_synced_when_named(env, monkeypatch, capsys):
    class Manual(Demo):
        info = SourceInfo("man", "Manual", "https://man.test", 1, policy="manual")

        def collections(self, fetch):
            yield CollectionDraft("man/all", "palette", "Man"), [
                ItemDraft("man:1", "palette", "One", "https://man.test/1", "https://man.test/1.hex", meta={"colors": ["#111111"]})]
    monkeypatch.setattr(base, "REGISTRY", {"man": Manual()})
    assert cli.main(["--json", "sync"]) == 0
    r = json.loads(capsys.readouterr().out)
    assert r["man"]["new"] == 0 and "manual source" in r["man"]["failures"][0]
    assert cli.main(["--json", "sync", "man"]) == 0
    assert json.loads(capsys.readouterr().out)["man"]["new"] == 1


def test_pluck_cli_prints_hex(env, capsys):
    cli.main(["sync"]); capsys.readouterr()
    cli.main(["--json", "search", "rust"]); iid = json.loads(capsys.readouterr().out)["results"][0]["id"]
    assert cli.main(["pluck", iid, "--out", str(env / "o")]) == 0
    out = capsys.readouterr().out
    assert "#230000" in out and f"{iid}.hex" in out


def test_pluck_cli_unknown_id(env, capsys):
    assert cli.main(["pluck", "zzzzzz"]) == 1


def test_collection_new_and_add(env, capsys, tmp_path):
    from PIL import Image
    Image.new("RGB", (500, 500)).save(tmp_path / "p.png")
    assert cli.main(["collection", "new", "swiss", "--kind", "image", "--language", "swiss international"]) == 0
    assert cli.main(["add", "curated/swiss", str(tmp_path / "p.png"), "--title", "Poster"]) == 0
    iid = capsys.readouterr().out.strip().splitlines()[-1]
    assert cli.main(["--json", "search", "poster", "--language", "swiss international"]) == 0
    assert json.loads(capsys.readouterr().out)["results"][0]["id"] == iid


def test_search_any_term_match_is_flagged(env, capsys):
    cli.main(["sync"]); capsys.readouterr()
    assert cli.main(["--json", "search", "rust"]) == 0
    assert json.loads(capsys.readouterr().out)["match"] == "all"
    assert cli.main(["--json", "search", "rust mint"]) == 0          # no palette has both words
    out = json.loads(capsys.readouterr().out)
    assert out["match"] == "any" and {r["title"] for r in out["results"]} == {"Rust", "Mint"}
    assert cli.main(["search", "rust mint"]) == 0
    assert capsys.readouterr().out.splitlines()[0] == "no item matches all terms; showing any-term matches"
    assert cli.main(["search", "rust"]) == 0
    assert "any-term" not in capsys.readouterr().out
    assert cli.main(["--json", "search", "qqqq"]) == 0
    assert json.loads(capsys.readouterr().out) == {"match": "none", "results": []}


def test_pluck_cli_oserror_keeps_earlier_results(env, capsys, monkeypatch):
    cli.main(["sync"]); capsys.readouterr()
    cli.main(["--json", "search", "rust"]); iid = json.loads(capsys.readouterr().out)["results"][0]["id"]
    real = cli.pluck_mod.pluck
    def flaky(conn, i, *a, **k):
        if i == "bad000":
            raise OSError("disk full")
        return real(conn, i, *a, **k)
    monkeypatch.setattr(cli.pluck_mod, "pluck", flaky)
    assert cli.main(["pluck", iid, "bad000", "--out", str(env / "o")]) == 1
    cap = capsys.readouterr()
    assert "#230000" in cap.out and "bad000: disk full" in cap.err


def test_add_cli_valueerror_is_an_error_exit(env, capsys, monkeypatch):
    cli.main(["collection", "new", "swiss", "--kind", "image"]); capsys.readouterr()
    def bad(*a, **k):
        raise ValueError("cannot thumbnail x.png: nope")
    monkeypatch.setattr(cli.curated, "add", bad)
    assert cli.main(["add", "curated/swiss", "x.png"]) == 1
    assert "error: x.png: cannot thumbnail" in capsys.readouterr().err
