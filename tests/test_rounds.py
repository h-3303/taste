import json

import pytest

from taste import cli, rounds
from taste.boards import survey
from taste.boards.run import Run


@pytest.fixture
def run(tmp_path):
    r = Run(tmp_path / "run")
    r.path.mkdir()
    return r


def doc(items, note="", at="2999-01-01T00:00:00Z", **extra):
    return {"items": {k: {"vote": v[0], "note": v[1]} for k, v in items.items()}, "note": note, "at": at, **extra}


def test_repeat_links_and_numbers(run):
    a = rounds.start(run, "broad", ["s001", "s002"])
    b = rounds.start(run, "broad", ["s003"], repeat_of=a.n)
    assert (a.n, b.n, b.repeat_of) == (1, 2, 1)
    assert rounds.next_n(run, "broad") == 3 and rounds.next_n(run, "boards") == 1
    assert rounds.load(run, "broad", 2).shown == ["s003"]
    assert [r.n for r in rounds.all_rounds(run, "broad")] == [1, 2]
    assert a.rendered_at.endswith("Z")


def test_stale_doc_refused(run):
    r = rounds.start(run, "broad", ["s001"])
    with pytest.raises(rounds.StalePage):
        rounds.ingest(run, "broad", r.n, {"items": {}, "at": "2000-01-01T00:00:00Z"})


def test_ingest_validates_stage_and_n(run):
    with pytest.raises(ValueError):
        rounds.ingest(run, "nope", 1, doc({}))
    with pytest.raises(ValueError):
        rounds.ingest(run, "broad", 7, doc({}))


def test_no_note_dropped_across_repeats(run):
    rounds.start(run, "broad", ["s001", "s002"])
    rounds.ingest(run, "broad", 1, doc({"s001": ("like", "warmer"), "s002": (None, "why this?")}, note="more print"))
    rounds.start(run, "broad", ["s003"], repeat_of=1)
    rounds.ingest(run, "broad", 2, doc({"s003": ("dislike", "")}, note=""))
    texts = [n["text"] for n in rounds.steering(run)["notes"]]
    assert texts == ["warmer", "why this?", "more print"]
    st = rounds.steering(run)
    assert st["likes"] == ["s001"] and st["dislikes"] == ["s003"]


def test_unknown_ids_dropped_and_notes_cleaned(run):
    rounds.start(run, "broad", ["s001"])
    r = rounds.ingest(run, "broad", 1, doc({"s001": ("like", "a\n<b>" + "x" * 700), "zzz": ("like", "no")}))
    assert list(r.items) == ["s001"]
    assert "\n" not in r.items["s001"].note and len(r.items["s001"].note) <= 600
    assert r.items["s001"].note.startswith("a <b>")
    assert r.at == "2999-01-01T00:00:00Z"


def test_later_vote_wins_but_none_does_not_erase(run):
    rounds.start(run, "broad", ["s001", "s002"])
    rounds.ingest(run, "broad", 1, doc({"s001": ("like", ""), "s002": ("like", "")}))
    rounds.start(run, "broad", ["s001", "s002"], repeat_of=1)
    rounds.ingest(run, "broad", 2, doc({"s001": ("dislike", ""), "s002": (None, "")}))
    st = rounds.steering(run)
    assert st["likes"] == ["s002"] and st["dislikes"] == ["s001"]


def test_keep_drop_combos_prompts_requests(run):
    rounds.start(run, "boards", ["i001", "i002"])
    rounds.ingest(run, "boards", 1, doc(
        {"i001": ("keep", ""), "i002": ("drop", "")},
        combos=[{"name": "mix", "parts": {"type": "1"}, "note": "n"}], prompts=["make it warmer"],
        requests=[{"type": "more-like", "id": "i001"}, {"type": "bogus"}]))
    st = rounds.steering(run)
    assert st["kept"] == ["i001"] and st["dropped"] == ["i002"]
    assert st["combos"][0]["name"] == "mix" and st["prompts"] == ["make it warmer"]
    assert st["requests"] == [{"type": "more-like", "id": "i001"}]


def test_final_comments_become_notes(run):
    rounds.record_final(run, [{"text": "logo smaller", "anchor": "header"}])
    assert rounds.steering(run)["notes"][-1]["text"] == "logo smaller"
    r = rounds.load(run, "final", 1)
    assert list(r.items) == ["pin-1"]


def test_final_rendered_at_from_demo_at(run):
    run.write("published.json", {"demo_at": "2026-01-02T03:04:05Z"})
    assert rounds.record_final(run, [{"text": "x", "anchor": ""}]).rendered_at == "2026-01-02T03:04:05Z"


def make_survey(run, tags):
    items = [{"id": f"s{i + 1:03d}", "tag": t} for i, t in enumerate(tags)]
    (run.path / "survey").mkdir()
    (run.path / "survey" / "items.json").write_text(json.dumps(items))
    return items


def test_gaps_lists_kinds_without_likes(run):
    make_survey(run, ["ui", "type", "palette", "texture"])
    rounds.start(run, "broad", ["s001", "s002"])
    rounds.ingest(run, "broad", 1, doc({"s001": ("like", ""), "s002": ("dislike", "")}))
    assert rounds.gaps(run) == [
        "Nothing liked in textures yet: add some, or ask for more",
        "Nothing liked in fonts yet: add some, or ask for more",
        "Nothing liked in palettes yet: add some, or ask for more"]


def test_gaps_item_kind_field_wins(run):
    items = make_survey(run, ["ui", "ui", "ui", "ui"])
    items[0]["kind"] = "font"
    (run.path / "survey" / "items.json").write_text(json.dumps(items))
    rounds.start(run, "broad", ["s001"])
    rounds.ingest(run, "broad", 1, doc({"s001": ("like", "")}))
    assert "Nothing liked in fonts yet: add some, or ask for more" not in rounds.gaps(run)
    assert "Nothing liked in images yet: add some, or ask for more" in rounds.gaps(run)


def test_gaps_thin_direction_and_no_rounds(run):
    run.write("pool.json", {"images": [{"id": f"i{k}", "style": "2"} for k in range(5)]
                            + [{"id": f"j{k}", "style": "1"} for k in range(9)]})
    assert rounds.gaps(run) == ["Direction 2 is thin (5 images)"]


def test_gaps_empty(run):
    assert rounds.gaps(run) == []


def test_cli_round_ingest_steer_final_gaps(run, tmp_path, capsys):
    rounds.start(run, "broad", ["s001"])
    d = tmp_path / "d.json"
    d.write_text(json.dumps(doc({"s001": ("like", "warm")})))
    assert cli.main(["round", "ingest", str(run.path), "broad", "1", str(d)]) == 0
    capsys.readouterr()
    assert cli.main(["round", "steer", str(run.path)]) == 0
    assert json.loads(capsys.readouterr().out)["likes"] == ["s001"]
    d.write_text(json.dumps({"items": {}, "at": "2000-01-01T00:00:00Z"}))
    assert cli.main(["round", "ingest", str(run.path), "broad", "1", str(d)]) == 1
    assert "older version" in capsys.readouterr().err
    assert cli.main(["round", "ingest", str(run.path), "nope", "1", str(d)]) == 1
    c = tmp_path / "c.json"
    c.write_text(json.dumps([{"text": "bigger", "anchor": "a"}]))
    assert cli.main(["round", "final", str(run.path), str(c)]) == 0
    assert cli.main(["gaps", str(run.path)]) == 0
