import json

import pytest

from taste import combine, rounds
from taste.boards.directions import validate
from taste.boards.run import Run
from taste.cli import main

AXES = [{"palette": "cool light", "density": "sparse", "type": "grotesk", "imagery": "print"},
        {"palette": "warm dark", "density": "dense", "type": "serif", "imagery": "photo"},
        {"palette": "neon", "density": "dense", "type": "display", "imagery": "3d"}]


def _dirs():
    out = []
    for k in range(3):
        ids = [f"i{k * 10 + j:03}" for j in range(1, 11)]
        out.append({
            "id": str(k + 1), "name": f"D{k + 1}", "rationale": "Short reason.", "image_ids": ids,
            "palette": [f"#{k}{k}{k}{k}{k}{j}" for j in range(5)],
            "palettes": {"light": {"bg": "#ffffff", "text": f"#00000{k}"}},
            "type": {"display": f"Display {k + 1}", "text": f"Text {k + 1}"},
            "fonts": [{"display": f"Display {k + 1}", "text": f"Text {k + 1}", "licence": "OFL"}],
            "components": [{"name": f"Comp {k + 1}", "kind": "ui", "licence": "MIT"}],
            "sections": {"texture": ids[:3], "ui": ids[3:5]},
            "motifs": [f"m{k}a", f"m{k}b", f"m{k}c"], "axes": AXES[k]})
    return out


POOL = {"images": [{"id": f"i{i:03}", "file": f"i{i:03}.jpg", "style": str((i - 1) // 10 + 1),
                    "source_url": f"https://src.test/{i}", "source_note": "n", "title": "t"} for i in range(1, 31)]}
ALL1 = {p: "1" for p in combine.PARTS}


@pytest.fixture
def dirs():
    return _dirs()


@pytest.fixture
def run_with_dirs(tmp_path):
    run = Run(tmp_path / "run")
    run.write("directions.json", {"directions": _dirs()})
    run.write("pool.json", POOL)
    return run


def ingest_with_combo(run, combos=None):
    rounds.start(run, "directions", ["1", "2", "3"], rendered_at="2000-01-01T00:00:00Z")
    combos = combos or [{"name": "Plate + grid", "note": "try it",
                         "parts": {"palette": "1", "type": "2", "texture": "2", "components": "1", "imagery": "1"}}]
    return rounds.ingest(run, "directions", 1, {"at": "2999-01-01T00:00:00Z", "combos": combos})


def test_combine_takes_each_part_from_its_source(dirs):
    m = combine.combine(dirs, {"palette": "1", "type": "2", "texture": "2", "components": "1", "imagery": "1"}, "Plate + grid")
    assert m["id"] == "m1" and m["palette"] == dirs[0]["palette"] and m["type"] == dirs[1]["type"]
    assert m["from"]["type"] == "2"


def test_combine_copies_part_extras(dirs):
    m = combine.combine(dirs, {"palette": "1", "type": "2", "texture": "3", "components": "2", "imagery": "1"}, "Mix", "n")
    assert m["palettes"] == dirs[0]["palettes"] and m["fonts"] == dirs[1]["fonts"]
    assert m["components"] == dirs[1]["components"] and m["note"] == "n" and m["name"] == "Mix"
    assert m["sections"]["texture"] == ["i021", "i022", "i023"]
    assert set(m["image_ids"]) == {"i021", "i022", "i023"} | {f"i{j:03}" for j in range(4, 11)}
    assert m["sections"]["ui"] == ["i004", "i005"]


def test_combine_next_free_id(dirs):
    dirs.append({**combine.combine(dirs, ALL1, "a"), "id": "m2"})
    assert combine.combine(dirs, ALL1, "b")["id"] == "m3"


def test_combine_rejects_unknown_direction(dirs):
    with pytest.raises(ValueError):
        combine.combine(dirs, {"palette": "9"}, "x")


@pytest.mark.parametrize("parts,name", [
    ({**ALL1, "palette": "9"}, "x"), ({**ALL1, "sound": "1"}, "x"),
    ({k: v for k, v in ALL1.items() if k != "type"}, "x"), (ALL1, "  ")])
def test_combine_rejects_bad_input(dirs, parts, name):
    with pytest.raises(ValueError):
        combine.combine(dirs, parts, name)


def test_mix_passes_validate(run_with_dirs):
    rnd = ingest_with_combo(run_with_dirs)
    out = combine.apply_combos(run_with_dirs, rnd)
    assert [d["id"] for d in out] == ["m1"]
    saved = run_with_dirs.read("directions.json")
    assert [d["id"] for d in saved["directions"]] == ["1", "2", "3", "m1"]
    assert validate(saved, run_with_dirs.read("pool.json")) == []


def test_two_mixes_pass_validate(run_with_dirs):
    rnd = ingest_with_combo(run_with_dirs, [
        {"name": "A", "parts": {"palette": "1", "type": "2", "texture": "2", "components": "1", "imagery": "1"}},
        {"name": "B", "parts": {"palette": "3", "type": "1", "texture": "1", "components": "3", "imagery": "1"}}])
    assert [d["id"] for d in combine.apply_combos(run_with_dirs, rnd)] == ["m1", "m2"]
    assert validate(run_with_dirs.read("directions.json"), POOL) == []


def test_bad_combo_writes_nothing(run_with_dirs):
    rnd = ingest_with_combo(run_with_dirs, [{"name": "A", "parts": {**ALL1, "type": "2"}},
                                            {"name": "B", "parts": {**ALL1, "type": "7"}}])
    with pytest.raises(ValueError):
        combine.apply_combos(run_with_dirs, rnd)
    assert len(run_with_dirs.read("directions.json")["directions"]) == 3


def _with_mix(dirs, **change):
    m = combine.combine(dirs, {**ALL1, "type": "2"}, "Mix")
    m.update(change)
    return {"directions": dirs + [m]}


@pytest.mark.parametrize("change,needle", [
    ({"id": "m2"}, "ids must be"),
    ({"id": "x1"}, "ids must be"),
    ({"from": {}}, "from"),
    ({"from": {**ALL1, "type": "9"}}, "from"),
    ({"from": {**ALL1, "sound": "1"}}, "from"),
    ({"image_ids": ["i001"] * 3}, "8-60 images"),
    ({"name": ""}, "name"),
    ({"image_ids": [f"i{j:03}" for j in range(1, 8)] + ["i025", "i026"]}, "not in its source"),
])
def test_validate_checks_mixes(dirs, change, needle):
    errs = validate(_with_mix(dirs, **change), POOL)
    assert any(needle in e for e in errs), errs


def test_validate_rejects_from_on_plain_direction(dirs):
    dirs[0]["from"] = ALL1
    assert any("from" in e for e in validate({"directions": dirs}, POOL))


def test_validate_rejects_mix_before_numbered(dirs):
    d = _with_mix(dirs)
    d["directions"].insert(0, d["directions"].pop())
    assert any("ids must be" in e for e in validate(d, POOL))


def test_gaps_skip_mixes(run_with_dirs):
    combine.apply_combos(run_with_dirs, ingest_with_combo(run_with_dirs))
    assert not any("m1" in g for g in rounds.gaps(run_with_dirs))


def test_cli_combine(run_with_dirs, capsys):
    ingest_with_combo(run_with_dirs)
    assert main(["combine", str(run_with_dirs.path), "--from-round", "1"]) == 0
    assert "m1" in capsys.readouterr().out
    assert main(["combine", str(run_with_dirs.path), "--from-round", "5"]) == 1
    assert "no directions round 5" in capsys.readouterr().err
