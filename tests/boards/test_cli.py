import pytest
import json

from PIL import Image

from taste.boards.cli import main

from .conftest import fill_library


def vault(tmp_path):
    res = tmp_path / "vault" / "Resources"
    res.mkdir(parents=True)
    (res / "Pear.md").write_text("---\ntype: resource\nurl: https://pear.example\n---\nRenaissance.\n")
    media = tmp_path / "vault" / "Sources" / "media" / "c"
    media.mkdir(parents=True)
    for k in range(1, 5):    # one post per style, 9 noise images each (all distinct for the duplicate check)
        for i in range(1, 10):
            Image.effect_noise((800, 600), 80).convert("RGB").save(media / f"S{k}_{i}.png")
    return tmp_path / "vault"


def styles_refs(sites=()):
    return {"styles": [{"id": str(k), "name": f"Style {k}", "sites": list(sites) if k == 1 else [],
                        "archive_queries": [], "vault_posts": [f"S{k}"]} for k in range(1, 5)]}


def make_dirs(pool, font="Inter", skip=0):
    axes = [("a", "a", "a", "a"), ("b", "b", "b", "b"), ("c", "c", "c", "c"), ("d", "d", "d", "d")]
    by_style = {str(k): [r["id"] for r in pool["images"] if r["style"] == str(k)][skip:skip + 8] for k in range(1, 5)}
    return {"directions": [{
        "id": str(k + 1), "name": f"D{k}", "rationale": "r",
        "image_ids": by_style[str(k + 1)], "palette": ["#000000"] * 5,
        "type": {"display": font, "text": "Inter"}, "motifs": ["a", "b", "c"],
        "axes": dict(zip(("palette", "density", "type", "imagery"), axes[k])),
    } for k in range(4)]}


def gathered_run(tmp_path, monkeypatch):
    monkeypatch.setenv("TASTE_DATA", str(tmp_path / "data"))
    fill_library()
    assert main(["new", "Test Project"]) == 0
    run = next((tmp_path / "data" / "runs").iterdir())
    (run / "refs.json").write_text(json.dumps(styles_refs()))
    assert main(["gather", str(run), "--no-sites"]) == 0
    return run, json.loads((run / "pool.json").read_text())


@pytest.mark.xfail(reason="connector, Task 15")
def test_new_gather_sheet_canvas_brief(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TASTE_DATA", str(tmp_path / "data"))
    fill_library()
    assert main(["new", "Test Project"]) == 0
    run = next((tmp_path / "data" / "runs").iterdir())
    assert json.loads((run / "library.json").read_text())[0]["note"] == "Pear"

    (run / "refs.json").write_text(json.dumps(styles_refs()))
    assert main(["gather", str(run), "--no-sites"]) == 0
    pool = json.loads((run / "pool.json").read_text())
    assert len(pool["images"]) >= 24 and pool["failures"] == []

    assert {r["style"] for r in pool["images"]} == {"1", "2", "3", "4"}
    assert main(["sheet", str(run)]) == 0
    assert sorted(p.name for p in (run / "sheets").iterdir()) == [f"sheet-{k}-1.png" for k in range(1, 5)]

    (run / "directions.json").write_text(json.dumps(make_dirs(pool)))
    assert main(["validate", str(run)]) == 0
    assert main(["canvas", str(run), "--title", "Test"]) == 0
    assert (run / "canvas" / "index.html").exists()

    proj = tmp_path / "proj"
    assert main(["brief", str(run), "--pick", "2", "--note", "n", "--project", str(proj)]) == 0
    assert (proj / "design" / "direction.md").exists()
    assert main(["brief", str(run), "--pick", "2", "--project", str(proj)]) == 2   # refuses overwrite
    assert main(["brief", str(run), "--pick", "99", "--project", str(tmp_path / "p2")]) == 1   # unknown pick


def test_canvas_bad_font_exits_1(tmp_path, monkeypatch, capsys):
    run, pool = gathered_run(tmp_path, monkeypatch)
    (run / "directions.json").write_text(json.dumps(make_dirs(pool, font="Bad;Font")))
    capsys.readouterr()
    assert main(["validate", str(run)]) == 1                 # "directions ok" guarantees the canvas renders
    assert "font" in capsys.readouterr().out.lower()
    assert main(["canvas", str(run), "--title", "T"]) == 1
    assert "font" in capsys.readouterr().out.lower()


def test_gather_reports_missing_chromium(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TASTE_DATA", str(tmp_path / "data"))
    fill_library()
    assert main(["new", "X"]) == 0
    run = next((tmp_path / "data" / "runs").iterdir())
    (run / "refs.json").write_text(json.dumps(styles_refs(sites=[{"url": "https://a.example", "note": "A"}])))

    def boom(sites, dest):
        from taste.render import RendererMissing
        raise RendererMissing()
    monkeypatch.setattr("taste.boards.capture.capture_sites", boom)
    assert main(["gather", str(run)]) == 2
    assert "Chromium is missing" in capsys.readouterr().out


def test_validate_reports_errors(tmp_path, capsys):
    (tmp_path / "pool.json").write_text(json.dumps({"images": [], "rejected": [], "failures": []}))
    (tmp_path / "directions.json").write_text(json.dumps({"directions": []}))
    assert main(["validate", str(tmp_path)]) == 1
    assert "at least 1 direction" in capsys.readouterr().out


@pytest.mark.xfail(reason="connector, Task 15")
def test_canvas_out_twice_does_not_nest(tmp_path, monkeypatch, capsys):
    run, pool = gathered_run(tmp_path, monkeypatch)
    out = tmp_path / "scratch" / "moodboards-x"
    (run / "directions.json").write_text(json.dumps(make_dirs(pool)))
    assert main(["canvas", str(run), "--title", "T", "--out", str(out)]) == 0
    second = make_dirs(pool, skip=1)
    (run / "directions.json").write_text(json.dumps(second))
    assert main(["canvas", str(run), "--title", "T", "--out", str(out)]) == 0
    assert sorted(p.name for p in out.iterdir()) == ["files.json", "img", "index.html"]
    files = json.loads((out / "files.json").read_text())
    want = {f"img/{i}.jpg" for d in second["directions"] for i in d["image_ids"]}
    assert set(files) == want
    assert {f"img/{p.name}" for p in (out / "img").iterdir()} == want
    assert not (run / "canvas").exists()
    assert str(out / "index.html") in capsys.readouterr().out


def noise_inbox(inbox, names, sources):
    inbox.mkdir(parents=True, exist_ok=True)
    for n in names:
        Image.effect_noise((800, 600), 80).convert("RGB").save(inbox / n)
    (inbox / "sources.txt").write_text("".join(f"{n}\thttps://ex/{n}\n" for n in sources))


def test_regather_keeps_earlier_inbox_images(tmp_path, monkeypatch):
    monkeypatch.setenv("TASTE_DATA", str(tmp_path / "data"))
    fill_library()
    assert main(["new", "Inbox"]) == 0
    run = next((tmp_path / "data" / "runs").iterdir())
    (run / "refs.json").write_text(json.dumps({"styles": []}))
    inbox = tmp_path / "data" / "inbox"
    noise_inbox(inbox, ["a.png", "b.png", "c.png"], ["a.png", "b.png", "c.png"])
    assert main(["gather", str(run), "--no-sites"]) == 0
    noise_inbox(inbox, ["d.png", "e.png"], ["d.png"])
    assert main(["gather", str(run), "--no-sites"]) == 0
    pool = json.loads((run / "pool.json").read_text())
    by_title = {r["title"]: r["source_url"] for r in pool["images"]}
    assert by_title == {"a": "https://ex/a.png", "b": "https://ex/b.png", "c": "https://ex/c.png",
                        "d": "https://ex/d.png", "e": ""}


def test_gather_needs_styles(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TASTE_DATA", str(tmp_path / "data"))
    fill_library()
    assert main(["new", "Old"]) == 0
    run = next((tmp_path / "data" / "runs").iterdir())
    (run / "refs.json").write_text(json.dumps({"sites": [], "archive_queries": [], "vault_posts": ["S1"]}))
    assert main(["gather", str(run), "--no-sites"]) == 1
    assert "styles" in capsys.readouterr().out


@pytest.mark.xfail(reason="connector, Task 15")
def test_gather_prints_counts_per_style(tmp_path, monkeypatch, capsys):
    run, pool = gathered_run(tmp_path, monkeypatch)
    out = capsys.readouterr().out
    assert "style 1 (Style 1): 9" in out and "style 4 (Style 4): 9" in out


class FakeHttp:
    def download(self, url, dest):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"img")
        return dest


def test_inbox_add_downloads_into_style_folder(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TASTE_DATA", str(tmp_path / "data"))
    monkeypatch.setattr("taste.boards.net.Http", FakeHttp)
    url = "https://cdn.mobbin.com/screens/abc.webp?sig=1"
    assert main(["inbox-add", "2", url, "--source", "https://mobbin.com/screens/abc", "--note", "Mobbin"]) == 0
    assert main(["inbox-add", "2", url, "--source", "https://mobbin.com/screens/abc2", "--note", "Mobbin"]) == 0
    folder = tmp_path / "data" / "inbox" / "2"
    assert sorted(p.name for p in folder.iterdir()) == ["abc-2.webp", "abc.webp", "sources.txt"]
    assert (folder / "sources.txt").read_text().splitlines() == [
        "abc.webp\thttps://mobbin.com/screens/abc\tMobbin\tMobbin · abc",
        "abc-2.webp\thttps://mobbin.com/screens/abc2\tMobbin\tMobbin · abc2"]


def test_inbox_add_rejects_bad_style(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TASTE_DATA", str(tmp_path / "data"))
    assert main(["inbox-add", "misc", "https://x/a.jpg", "--source", "https://x"]) == 1


def test_scout_and_keep_commands(tmp_path, monkeypatch, capsys):
    from pathlib import Path
    fix = (Path(__file__).parent / "fixtures" / "cosmos_search.html").read_text()
    monkeypatch.setenv("TASTE_DATA", str(tmp_path / "data"))
    monkeypatch.setattr("taste.boards.scout.render_page", lambda url: fix if "cosmos" in url else "")

    def dl(url, dest):
        dest.parent.mkdir(parents=True, exist_ok=True)
        Image.effect_noise((700, 500), 80).convert("RGB").save(dest, "JPEG")
        return dest
    monkeypatch.setattr("taste.boards.scout._download", dl)
    run = tmp_path / "data" / "runs" / "r"
    run.mkdir(parents=True)
    assert main(["scout", str(run), "2", "--cosmos", "neumorphic ui"]) == 0
    out = capsys.readouterr().out
    assert "6 candidates" in out and "sheet-2-1.png" in out
    assert main(["keep", str(run), "2", "1", "4"]) == 0
    assert len(list((tmp_path / "data" / "inbox" / "2").glob("*.jpg"))) == 2
    assert main(["keep", str(run), "2", "99"]) == 1
    assert main(["scout", str(run), "2"]) == 1          # needs at least one search


def test_gather_pulls_dlib_ids(monkeypatch, tmp_path, capsys):
    from taste.boards import cli
    from taste.boards.run import Run
    monkeypatch.setenv("TASTE_DATA", str(tmp_path / "data"))
    run = Run.create("x", root=tmp_path / "data" / "runs")
    run.write("refs.json", {"styles": [{"id": "1", "name": "Swiss", "sites": [], "archive_queries": [], "vault_posts": [], "dlib_ids": ["abc123"]}]})
    img = tmp_path / "plucked.jpg"; Image.new("RGB", (500, 500)).save(img)
    monkeypatch.setattr(cli, "dlib_pluck", lambda iid, out: {"path": str(img), "title": "Grid", "page_url": "https://src/x"})
    assert cli.main(["gather", str(run.path), "--no-sites"]) == 0
    pool = run.read("pool.json")
    assert pool["images"] and pool["images"][0]["kind"] == "library" and pool["images"][0]["style"] == "1"
