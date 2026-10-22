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
    assert main(["round", "render", str(run.path), "final", "--title", "Shop", "--out", str(tmp_path / "o2")]) == 1
    assert "stage final has no page yet" in capsys.readouterr().err


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


def _boards_run(tmp_path, n_dirs=3):
    from PIL import Image as _I
    run = Run(tmp_path / "brun")
    run.images.mkdir(parents=True, exist_ok=True)
    pool = {"images": []}
    for i in range(1, 13):
        iid = f"i{i:03}"
        _I.new("RGB", (800, 600)).save(run.images / f"{iid}.jpg")
        pool["images"].append({"id": iid, "file": f"{iid}.jpg", "source_url": f"https://src/{i}",
                               "source_note": "Note", "title": "T", "kind": "site"})
    dirs = {"directions": [{
        "id": str(k), "name": f"Dir {k}", "rationale": "Why.",
        "image_ids": [f"i{j:03}" for j in range(1, 9)],
        "palette": ["#111111", "#222222", "#333333", "#444444", "#555555"],
        "type": {"display": "Archivo Black", "text": "IBM Plex Sans"},
        "motifs": ["grid", "rule", "dot"], "axes": {},
        **({"sections": {"ui": ["i001", "i002"], "graphic": ["i003"]},
            "palettes": {"light": {"bg": "#ffffff", "text": "#000000", "accent": "#8a0000"}}} if k == 3 else {})}
        for k in range(1, n_dirs + 1)]}
    (run.path / "directions.json").write_text(json.dumps(dirs)); (run.path / "pool.json").write_text(json.dumps(pool))
    return run


def test_boards_page_has_board_and_image_items_with_notes(tmp_path):
    run = _boards_run(tmp_path)
    out = tmp_path / "bo"
    html = render_round(run, "boards", "Shop", out).read_text(encoding="utf-8")
    assert len(re.findall(r'data-id="d\d"', html)) == 3
    assert len(re.findall(r'data-id="\d/i\d{3}"', html)) == 24
    assert len(re.findall(r'<textarea[^>]*class="item-note"', html)) == 27
    assert 'data-votes="keep drop"' in html and "rounds/boards-1" in html
    assert "Choose this" not in html and "data-choose" not in html and "picks/current" not in html
    assert "Palettes" in html and "Light" in html
    rec = rounds.load(run, "boards", 1)
    assert rec.shown[:2] == ["d1", "1/i001"] and len(rec.shown) == 27 and "d3" in rec.shown
    files = json.loads((out / "files.json").read_text())
    assert files and all((out / k).exists() for k in files)


def test_boards_drop_with_note_reaches_steering(tmp_path):
    run = _boards_run(tmp_path)
    render_round(run, "boards", "Shop", tmp_path / "bo")
    rounds.ingest(run, "boards", 1, {"at": "2999-01-01T00:00:00+00:00", "items": {
        "1/i004": {"vote": "drop", "note": "too glossy"}, "d2": {"vote": "keep"}}})
    s = rounds.steering(run)
    assert "1/i004" in s["dropped"] and "d2" in s["kept"]
    assert any(n["id"] == "1/i004" and n["text"] == "too glossy" for n in s["notes"])


def test_canvas_still_exposes_board_builder(tmp_path):
    from taste.boards.canvas import build_boards
    run = _boards_run(tmp_path)
    (tmp_path / "x" / "img").mkdir(parents=True)
    boards, files, font_urls = build_boards(run.read("directions.json"), run.read("pool.json"), run.images, tmp_path / "x")
    assert [b["id"] for b in boards] == ["1", "2", "3"] and font_urls
