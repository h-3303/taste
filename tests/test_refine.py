import json
from datetime import date

import pytest
from PIL import Image

from taste import refine, rounds
from taste.boards.brief import write_brief
from taste.boards.run import Run
from taste.cli import main


def _still(run, name):
    p = run.path / "refine" / "stills" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (320, 200), (40, 80, 120)).save(p)
    return f"refine/stills/{name}"


def _options(run, n=1, kind="ui", layers=None):
    layers = layers or {
        "ground": [("paper", "Paper", "warm off-white, faint grain"), ("slate", "Slate", "cool grey ground")],
        "type": [("serif", "Serif", "Fraunces display"), ("grotesk", "Grotesk", "tight sans"),
                 ("mono", "Mono", "monospace labels")],
    }
    doc = {"kind": kind, "layers": {
        layer: [{"id": i, "label": lab, "still": _still(run, f"{n}-{layer}-{i}.png"), "detail": det}
                for i, lab, det in opts] for layer, opts in layers.items()}}
    run.write(f"refine/{n}-options.json", doc)
    return doc


def _opt(run, i):
    return {"id": i, "label": i.title(), "still": _still(run, f"{i}.png"), "detail": ""}


@pytest.fixture
def run(tmp_path):
    return Run(tmp_path / "run")


def test_layers():
    assert refine.LAYERS == {"ui": ("ground", "cards", "depth", "ui", "type", "accent"),
                             "graphic": ("ground", "type", "accent", "imagery", "texture")}


def test_check_options_valid(run):
    assert refine.check_options(_options(run), root=run.path) == []


def test_check_options_too_few_and_too_many(run):
    doc = {"kind": "ui", "layers": {"ground": [_opt(run, "a")],
                                    "cards": [_opt(run, f"c{k}") for k in range(7)]}}
    errs = refine.check_options(doc, root=run.path)
    assert any("ground" in e and "2" in e for e in errs)
    assert any("cards" in e and "6" in e for e in errs)


def test_check_options_duplicate_ids(run):
    doc = {"kind": "ui", "layers": {"ground": [_opt(run, "a"), _opt(run, "a")]}}
    assert any("duplicate" in e and "a" in e for e in refine.check_options(doc, root=run.path))


def test_check_options_missing_still(run):
    doc = {"kind": "ui", "layers": {"ground": [_opt(run, "a"), {**_opt(run, "b"), "still": "refine/nope.png"}]}}
    assert any("refine/nope.png" in e for e in refine.check_options(doc, root=run.path))


def test_check_options_still_outside_run(run, tmp_path):
    Image.new("RGB", (4, 4)).save(tmp_path / "out.png")
    doc = {"kind": "ui", "layers": {"ground": [_opt(run, "a"), {**_opt(run, "b"), "still": "../out.png"}]}}
    assert any("../out.png" in e for e in refine.check_options(doc, root=run.path))


def test_check_options_unknown_layer_and_kind(run):
    doc = {"kind": "ui", "layers": {"floor": [_opt(run, "a"), _opt(run, "b")]}}
    assert any("floor" in e for e in refine.check_options(doc, root=run.path))
    assert any("kind" in e for e in refine.check_options({"kind": "print", "layers": {}}))


def test_graphic_layers_differ_from_ui(run):
    doc = {"kind": "graphic", "layers": {"cards": [_opt(run, "a"), _opt(run, "b")]}}
    assert any("cards" in e for e in refine.check_options(doc, root=run.path))


DIRECTION = ("# Design direction: Warm Editorial\n\nSoft.\n\n## Palette\n\n- `#111111`\n\n"
             "## Current finish\n\nNot refined yet.\n\n## References\n\n- a ref\n")


def _project(tmp_path):
    proj = tmp_path / "proj"
    (proj / "design").mkdir(parents=True)
    (proj / "design" / "direction.md").write_text(DIRECTION, encoding="utf-8")
    (proj / "other.txt").write_text("untouched", encoding="utf-8")
    return proj


def _pass(run, n, picks, notes=None, prompts=(), note="", layers=None):
    _options(run, n, layers=layers)
    shown = refine.shown_ids(run.read(f"refine/{n}-options.json"))
    r = rounds.start(run, "refine", shown, rendered_at="2026-01-01T00:00:00Z")
    assert r.n == n
    items = {i: {"vote": "pick", "note": ""} for i in picks}
    for i, t in (notes or {}).items():
        items[i] = {**items.get(i, {"vote": None}), "note": t}
    rounds.ingest(run, "refine", n, {"items": items, "prompts": list(prompts), "note": note,
                                     "at": "2026-01-02T00:00:00Z"})


def _outside(md):
    head, rest = md.split("## Current finish\n", 1)
    return head + rest[rest.index("\n## "):]


def test_apply_pass_writes_taste_and_current_finish(run, tmp_path):
    proj = _project(tmp_path)
    _pass(run, 1, ["ground:paper", "type:serif"], notes={"type": "bigger x-height", "ground:paper": "less grain"},
          prompts=["try a darker accent"], note="getting close")
    out = refine.apply_pass(run, 1, proj)
    assert out == proj / "design" / "taste.md"
    md = out.read_text(encoding="utf-8")
    assert f"## Refine pass 1 ({date.today().isoformat()})" in md
    assert "- ground: Paper" in md and "less grain" in md
    assert "- type: Serif" in md and "bigger x-height" in md
    assert "try a darker accent" in md and "getting close" in md
    d = (proj / "design" / "direction.md").read_text(encoding="utf-8")
    assert _outside(d) == _outside(DIRECTION)
    finish = d.split("## Current finish\n", 1)[1].split("\n## ")[0]
    assert "Not refined yet" not in finish
    assert "- ground: Paper — warm off-white, faint grain" in finish
    assert "- type: Serif — Fraunces display" in finish
    assert (proj / "other.txt").read_text() == "untouched"
    assert sorted(p.name for p in (proj / "design").iterdir()) == ["direction.md", "taste.md"]


def test_unpicked_layer_only_with_note(run, tmp_path):
    proj = _project(tmp_path)
    _pass(run, 1, ["ground:slate"], notes={"type": "none of these"})
    md = refine.apply_pass(run, 1, proj).read_text(encoding="utf-8")
    assert "- type: (no pick)" in md and "none of these" in md
    _pass(run, 2, ["ground:paper"])
    md = refine.apply_pass(run, 2, proj).read_text(encoding="utf-8")
    sec2 = md.split("## Refine pass 2")[1]
    assert "- ground: Paper" in sec2 and "type" not in sec2


def test_hostile_note_stays_in_one_escaped_line(run, tmp_path):
    proj = _project(tmp_path)
    _pass(run, 1, ["ground:paper"], notes={"ground": "## hijack\n[x](y) <script>alert(1)</script>"},
          prompts=["## p\n[a](b) <img src=x onerror=alert(2)>"], note="# n\n(z) <iframe src=y>")
    md = refine.apply_pass(run, 1, proj).read_text(encoding="utf-8")
    direction = (proj / "design" / "direction.md").read_text(encoding="utf-8")
    assert "\n## hijack" not in md and "\n# n" not in md and "\n## p" not in md
    line = next(x for x in md.splitlines() if "hijack" in x)
    assert line.startswith("- ground: Paper") and "\\[x\\]\\(y\\)" in line
    assert "[x](y)" not in md and "[a](b)" not in md
    for doc in (md, direction):
        assert "<script" not in doc and "<img" not in doc and "<iframe" not in doc
    assert "&lt;script>" in md


def test_two_passes_give_two_sections_in_order(run, tmp_path):
    proj = _project(tmp_path)
    _pass(run, 1, ["ground:paper"])
    refine.apply_pass(run, 1, proj)
    _pass(run, 2, ["ground:slate"])
    md = refine.apply_pass(run, 2, proj).read_text(encoding="utf-8")
    assert md.index("## Refine pass 1 (") < md.index("## Refine pass 2 (")
    assert md.count("## Refine pass") == 2
    finish = (proj / "design" / "direction.md").read_text().split("## Current finish\n", 1)[1]
    assert "Slate" in finish and "Paper" not in finish


def test_reapplying_a_pass_does_not_duplicate(run, tmp_path):
    proj = _project(tmp_path)
    _pass(run, 1, ["ground:paper"])
    refine.apply_pass(run, 1, proj)
    md = refine.apply_pass(run, 1, proj).read_text(encoding="utf-8")
    assert md.count("## Refine pass 1 (") == 1


def test_apply_without_project_uses_run_folder(run, tmp_path):
    run.path.mkdir(parents=True, exist_ok=True)
    (run.path / "direction.md").write_text(DIRECTION, encoding="utf-8")
    _pass(run, 1, ["ground:paper"])
    assert refine.apply_pass(run, 1, None) == run.path / "taste.md"
    assert "Paper" in (run.path / "direction.md").read_text()


def test_apply_needs_an_ingested_pass_and_a_brief(run, tmp_path):
    proj = _project(tmp_path)
    _options(run, 1)
    rounds.start(run, "refine", refine.shown_ids(run.read("refine/1-options.json")))
    with pytest.raises(ValueError, match="ingest"):
        refine.apply_pass(run, 1, proj)
    with pytest.raises(ValueError, match="direction.md"):
        _pass(run, 2, ["ground:paper"])
        refine.apply_pass(run, 2, tmp_path / "empty")
    assert not (tmp_path / "empty" / "design" / "taste.md").exists()


def test_apply_takes_one_pick_per_layer(run, tmp_path):
    proj = _project(tmp_path)
    _pass(run, 1, ["ground:paper", "ground:slate"])
    md = refine.apply_pass(run, 1, proj).read_text(encoding="utf-8")
    assert md.count("- ground:") == 1


def test_apply_adds_current_finish_to_old_brief(run, tmp_path):
    proj = tmp_path / "proj"
    (proj / "design").mkdir(parents=True)
    old = "# Design direction: X\n\n## References\n\n- a\n"
    (proj / "design" / "direction.md").write_text(old, encoding="utf-8")
    _pass(run, 1, ["ground:paper"])
    refine.apply_pass(run, 1, proj)
    d = (proj / "design" / "direction.md").read_text()
    assert d.startswith(old) and "## Current finish" in d and "Paper" in d


def test_brief_has_current_finish_section(tmp_path):
    images = tmp_path / "images"; images.mkdir()
    Image.new("RGB", (8, 8)).save(images / "i1.jpg")
    pool = {"images": [{"id": "i1", "file": "i1.jpg", "title": "R", "source_url": "https://e/1", "source_note": "N"}]}
    dirs = {"directions": [{"id": "1", "name": "W", "rationale": "r", "image_ids": ["i1"], "palette": ["#000000"],
                            "type": {"display": "A", "text": "B"}, "motifs": ["m"]}]}
    md = write_brief(dirs, pool, images, "1", "", tmp_path / "d", "p").read_text()
    assert "\n## Current finish\n\nNot refined yet.\n" in md


def test_cli_check_and_apply(run, tmp_path, capsys):
    proj = _project(tmp_path)
    _pass(run, 1, ["ground:paper"])
    assert main(["refine", "check", str(run.path), "1"]) == 0
    assert main(["refine", "apply", str(run.path), "1", "--project", str(proj)]) == 0
    assert str(proj / "design" / "taste.md") in capsys.readouterr().out
    bad = run.read("refine/1-options.json")
    bad["layers"]["floor"] = bad["layers"].pop("ground")
    run.write("refine/1-options.json", bad)
    assert main(["refine", "check", str(run.path), "1"]) == 1
    assert "floor" in capsys.readouterr().err
    assert main(["refine", "check", str(run.path), "9"]) == 1
