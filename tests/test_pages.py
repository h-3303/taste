import json
import re

from PIL import Image

from taste import rounds
from taste.boards import survey
from taste.boards.run import Run
from taste.cli import main
from taste.library import db
from taste.library.models import CollectionDraft, ItemDraft, SourceInfo
from taste.pages import render_library, render_round


def _img(path):
    Image.new("RGB", (400, 300), (90, 60, 30)).save(path)
    return path


def _run(tmp_path, titles=("Swiss poster", "Riso zine", "Brutalist site")):
    run = Run(tmp_path / "run")
    for k, t in enumerate(titles):
        survey.add(run.path, str(_img(tmp_path / f"src{k}.png")), title=t, source=f"https://ref.test/{k}",
                   why="notable", tag="web")
    return run


def test_broad_page_has_items_votes_notes_doc_and_files(tmp_path):
    run = _run(tmp_path)
    out = tmp_path / "out"
    page = render_round(run, "broad", "Shop", out)
    assert page == out / "index.html"
    html = page.read_text(encoding="utf-8")
    for sid in ("s001", "s002", "s003"):
        assert f'id="{sid}"' in html
    assert 'data-votes="like dislike"' in html
    assert len(re.findall(r'<textarea[^>]*class="item-note"', html)) == 3
    assert 'id="page-note"' in html
    assert "rounds/broad-1" in html
    assert 'id="add-url"' in html and "more-like" in html and "Saved." in html
    assert "repeat of pass" not in html
    files = json.loads((out / "files.json").read_text())
    assert set(files) == {f"img/{it['file']}" for it in survey.load(run.path)}
    assert all((out / k).exists() for k in files)
    rec = rounds.load(run, "broad", 1)
    assert rec.shown == ["s001", "s002", "s003"] and rec.repeat_of is None


def test_repeat_render_targets_next_pass(tmp_path):
    run = _run(tmp_path)
    render_round(run, "broad", "Shop", tmp_path / "o1")
    html = render_round(run, "broad", "Shop", tmp_path / "o2", repeat_of=1).read_text(encoding="utf-8")
    assert "rounds/broad-2" in html and "rounds/broad-1" not in html
    assert "repeat of pass 1" in html
    assert rounds.load(run, "broad", 2).repeat_of == 1


def test_fields_are_autoescaped(tmp_path):
    run = _run(tmp_path, titles=("<script>x</script>",))
    html = render_round(run, "broad", "<b>T</b>", tmp_path / "out").read_text(encoding="utf-8")
    assert "<script>x</script>" not in html and "&lt;script&gt;x&lt;/script&gt;" in html
    assert "<b>T</b>" not in html


def test_no_person_specific_text(tmp_path):
    html = render_round(_run(tmp_path), "broad", "Shop", tmp_path / "out").read_text(encoding="utf-8")
    assert not re.search(r"\bh\b(?!=)", re.sub(r"<[^>]+>", " ", html.split("<script>")[0]))


def _library(tmp_path):
    conn = db.connect(tmp_path / "lib.db")
    db.upsert_source(conn, SourceInfo("gal", "Gal", "https://g.test", 1))
    cid = db.upsert_collection(conn, "gal", CollectionDraft("gal/all", "site", "All"))
    ids = {}
    for key, meta in (("alive", {}), ("dead", {"dead": True})):
        ids[key], _ = db.upsert_item(conn, "gal", ItemDraft(f"gal:{key}", "image", f"Garden {key}",
                                                            f"https://g.test/{key}", f"https://cdn.g.test/{key}.jpg",
                                                            meta=meta, license="CC0"), cid, "2026-01-01")
    conn.commit()
    return conn, ids


def test_library_page_lists_only_live_items(tmp_path):
    conn, ids = _library(tmp_path)
    html = render_library(conn, tmp_path / "out", thumbs_dir=tmp_path / "thumbs").read_text(encoding="utf-8")
    assert "Garden alive" in html and "Garden dead" not in html
    assert f'id="{ids["alive"]}"' in html
    assert 'data-votes=""' in html and 'class="item-note"' in html and 'id="add-url"' in html
    assert "CC0" in html and "https://g.test/alive" in html
    assert (tmp_path / "out" / "files.json").exists()


def test_cli_round_render_and_unknown_stage(tmp_path, capsys):
    run = _run(tmp_path)
    assert main(["round", "render", str(run.path), "broad", "--title", "Shop", "--out", str(tmp_path / "o")]) == 0
    assert (tmp_path / "o" / "index.html").exists()
    assert main(["round", "render", str(run.path), "boards", "--title", "Shop", "--out", str(tmp_path / "o2")]) == 1
    assert "stage boards has no page yet" in capsys.readouterr().err


def test_cli_library_page(tmp_path, monkeypatch):
    monkeypatch.setenv("TASTE_DATA", str(tmp_path / "data"))
    from taste.library import paths
    conn = db.connect(paths.db_path())
    db.upsert_source(conn, SourceInfo("gal", "Gal", "https://g.test", 1))
    cid = db.upsert_collection(conn, "gal", CollectionDraft("gal/all", "site", "All"))
    db.upsert_item(conn, "gal", ItemDraft("gal:a", "font", "Grotesk A", "https://g.test/a", "https://g.test/a.zip"),
                   cid, "2026-01-01")
    conn.commit()
    conn.close()
    out = tmp_path / "lp"
    assert main(["library-page", "--out", str(out), "--kind", "font", "--no-fetch"]) == 0
    assert "Grotesk A" in (out / "index.html").read_text(encoding="utf-8")
