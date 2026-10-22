import json
from datetime import date, datetime, timedelta, timezone

import pytest

from taste import profile, rounds
from taste.boards.run import Run
from taste.cli import main
from taste.pages import render_round

TODAY = date.today().isoformat()


def _proposals(run, items=None):
    items = items or [
        {"id": "p1", "section": "Liked traits", "text": "Warm paper grounds", "default": True},
        {"id": "p2", "section": "Rules", "text": "Never use gradients", "default": False},
    ]
    run.write("proposals.json", items)
    return items


def _directions(run):
    run.write("directions.json", {"directions": [
        {"id": "1", "name": "Swiss grid"}, {"id": "2", "name": "Riso zine"},
        {"id": "m1", "name": "Grid zine", "from": {"palette": "2", "type": "1", "imagery": "2",
                                                  "texture": "2", "components": "1"},
         "from_round": 1, "note": "keep the grain"}]})


def _brief(dest, name="Grid zine", project="shop"):
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "direction.md").write_text(f"# Design direction: {name}\n\nProject: {project} · chosen {TODAY}\n",
                                       encoding="utf-8")


def _render(run):
    n = rounds.next_n(run, "review")
    render_round(run, "review", "Shop", run.path / f"page-{n}")
    return n


def _ingest(run, n, votes, note=None):
    items = {k: {"vote": v, "note": note or ""} for k, v in votes.items()}
    later = (datetime.now(timezone.utc) + timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return rounds.ingest(run, "review", n, {"items": items, "at": later})


def _review(run, votes, note=None):
    return _ingest(run, _render(run), votes, note)


@pytest.fixture
def run(tmp_path):
    r = Run(tmp_path / "runs" / "2026-10-22-shop")
    r.path.mkdir(parents=True)
    return r


def test_sections():
    assert profile.SECTIONS == ("Liked traits", "Disliked traits", "Rules", "References", "Projects")


def test_missing_profile_reads_empty(tmp_path):
    assert profile.read_profile(tmp_path / "nope.md") == {s: [] for s in profile.SECTIONS}


def test_round_trip_keeps_hand_added_section(tmp_path):
    p = tmp_path / "profile.md"
    data = {"Rules": ["One accent only"], "Liked traits": ["Grain"], "Fonts I own": ["Söhne"]}
    profile.write_profile(p, data)
    text = p.read_text(encoding="utf-8")
    assert text.startswith("# Taste profile\n")
    assert text.index("## Liked traits") < text.index("## Rules") < text.index("## Projects") < text.index("## Fonts I own")
    assert "- One accent only" in text and "- Söhne" in text
    back = profile.read_profile(p)
    assert back["Fonts I own"] == ["Söhne"] and back["Rules"] == ["One accent only"]
    assert back["Liked traits"] == ["Grain"] and back["References"] == []
    p.write_text(text + "- Founders Grotesk\n", encoding="utf-8")
    assert profile.read_profile(p)["Fonts I own"] == ["Söhne", "Founders Grotesk"]


def test_apply_review_writes_ticked_only_plus_projects_line(run, tmp_path):
    _proposals(run)
    _directions(run)
    _brief(run.path)
    _review(run, {"p1": "pick", "p2": None})
    out = tmp_path / "profile.md"
    res = profile.apply_review(run, 1, out)
    data = profile.read_profile(out)
    assert data["Liked traits"] == ["Warm paper grounds"]
    assert data["Rules"] == []
    assert "Never use gradients" not in out.read_text(encoding="utf-8")
    assert data["Projects"] == [f"{TODAY} shop: Grid zine"]
    assert res["added"]["Liked traits"] == ["Warm paper grounds"]


def test_apply_review_twice_adds_nothing(run, tmp_path):
    _proposals(run)
    _brief(run.path)
    _review(run, {"p1": "pick", "p2": "pick"})
    out = tmp_path / "profile.md"
    profile.apply_review(run, 1, out)
    first = out.read_text(encoding="utf-8")
    res = profile.apply_review(run, 1, out)
    assert out.read_text(encoding="utf-8") == first
    assert not any(res["added"].values())


def test_apply_review_dedupes_case_and_space(run, tmp_path):
    out = tmp_path / "profile.md"
    profile.write_profile(out, {"Liked traits": ["warm   PAPER grounds"]})
    _proposals(run)
    _brief(run.path)
    _review(run, {"p1": "pick"})
    profile.apply_review(run, 1, out)
    assert profile.read_profile(out)["Liked traits"] == ["warm PAPER grounds"]


def test_apply_review_escapes_untrusted_text(run, tmp_path):
    _proposals(run, [{"id": "p1", "section": "References", "text": "see\n[link](x) <img src=y>", "default": True}])
    _brief(run.path, name="<b>Bold</b>")
    _review(run, {"p1": "pick"})
    out = tmp_path / "profile.md"
    profile.apply_review(run, 1, out)
    text = out.read_text(encoding="utf-8")
    assert "- see \\[link\\]\\(x\\) &lt;img src=y>" in text
    assert "<img" not in text and "<b>" not in text
    assert profile.read_profile(out)["References"] == ["see \\[link\\]\\(x\\) &lt;img src=y>"]


def test_apply_review_uses_project_and_says_when_no_pick(run, tmp_path):
    _proposals(run)
    proj = tmp_path / "myproj"
    profile.write_project_taste(run, proj)
    _review(run, {})
    out = tmp_path / "profile.md"
    profile.apply_review(run, 1, out)
    assert profile.read_profile(out)["Projects"] == [f"{TODAY} myproj: no direction picked yet"]


def test_apply_review_refuses_before_ingest(run, tmp_path, capsys):
    _proposals(run)
    _render(run)
    with pytest.raises(ValueError, match="ingest"):
        profile.apply_review(run, 1, tmp_path / "profile.md")
    assert not (tmp_path / "profile.md").exists()


def test_check_proposals_rejects_bad_sections_and_ids():
    bad = [{"id": "p1", "section": "Projects", "text": "x", "default": True},
           {"id": "p1", "section": "Rules", "text": "y", "default": False},
           {"id": "p3", "section": "Rules", "text": " ", "default": False}]
    errs = profile.check_proposals(bad)
    assert any("Projects" in e for e in errs)
    assert any("duplicate" in e for e in errs)
    assert any("p3" in e for e in errs)
    assert profile.check_proposals([{"id": "p1", "section": "Rules", "text": "x", "default": False}]) == []


def test_write_project_taste_head_and_keeps_refine_passes(run, tmp_path):
    _directions(run)
    proj = tmp_path / "proj"
    _brief(proj / "design")
    run.write("taste.json", {"likes": ["s001"], "dislikes": ["s002"], "note": "less shiny <i>",
                             "traits_liked": ["grain", "[x](y)"], "traits_disliked": ["chrome"]})
    r = rounds.start(run, "broad", ["s001", "s002"], rendered_at="2026-01-01T00:00:00Z")
    rounds.ingest(run, "broad", r.n, {"items": {"s001": {"vote": "like", "note": "the grain\nhere"}},
                                       "note": "more paper", "at": "2026-01-02T00:00:00Z"})
    taste = proj / "design" / "taste.md"
    taste.write_text("# old head\n\nstale\n\n## Refine pass 1 (2026-10-01)\n\n- ground: Paper\n", encoding="utf-8")
    out = profile.write_project_taste(run, proj)
    assert out == taste
    text = taste.read_text(encoding="utf-8")
    assert "stale" not in text and "# old head" not in text
    assert text.endswith("## Refine pass 1 (2026-10-01)\n\n- ground: Paper\n")
    head = text.split("## Refine pass 1")[0]
    assert "Grid zine" in head and "palette from 2" in head and "type from 1" in head and "keep the grain" in head
    assert "grain" in head and "\\[x\\]\\(y\\)" in head and "chrome" in head
    assert "less shiny &lt;i>" in head
    assert "the grain here" in head and "more paper" in head and "broad 1" in head
    assert "<i>" not in text


def test_write_project_taste_without_pick_or_project(run):
    out = profile.write_project_taste(run, None)
    assert out == run.path / "taste.md"
    assert "No direction picked yet" in out.read_text(encoding="utf-8")


def test_refine_pass_after_project_taste_keeps_head(run, tmp_path):
    from taste import refine
    proj = tmp_path / "proj"
    _brief(proj / "design")
    profile.write_project_taste(run, proj)
    head = (proj / "design" / "taste.md").read_text(encoding="utf-8")
    (run.path / "refine").mkdir()
    run.write("refine/1-options.json", {"kind": "ui", "layers": {}})
    r = rounds.start(run, "refine", [], rendered_at="2026-01-01T00:00:00Z")
    rounds.ingest(run, "refine", r.n, {"items": {}, "note": "fine", "at": "2026-01-02T00:00:00Z"})
    refine.apply_pass(run, 1, proj)
    text = (proj / "design" / "taste.md").read_text(encoding="utf-8")
    assert text.startswith(head.rstrip("\n")) and "## Refine pass 1" in text
    profile.write_project_taste(run, proj)
    assert "## Refine pass 1" in (proj / "design" / "taste.md").read_text(encoding="utf-8")


def test_cli_profile_show_project_apply(run, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TASTE_DATA", str(tmp_path / "data"))
    assert main(["profile", "show"]) == 0
    assert "no profile yet" in capsys.readouterr().out.lower()
    _proposals(run)
    proj = tmp_path / "proj"
    assert main(["profile", "project", str(run.path), "--project", str(proj)]) == 0
    assert (proj / "design" / "taste.md").is_file()
    capsys.readouterr()
    _render(run)
    assert main(["profile", "apply", str(run.path), "1"]) == 1
    assert "ingest" in capsys.readouterr().err
    _review(run, {"p1": "pick"})
    assert main(["profile", "apply", str(run.path), "2"]) == 0
    capsys.readouterr()
    assert main(["profile", "show"]) == 0
    shown = capsys.readouterr().out
    assert "# Taste profile" in shown and "Warm paper grounds" in shown
    assert (tmp_path / "data" / "profile.md").is_file()


def test_apply_review_uses_what_the_page_showed(run, tmp_path):
    _proposals(run)
    n = _render(run)
    assert json.loads((run.path / "review" / f"{n}-proposals.json").read_text())[0]["text"] == "Warm paper grounds"
    _proposals(run, [{"id": "p1", "section": "Disliked traits", "text": "REWORDED", "default": True},
                     {"id": "p2", "section": "Rules", "text": "Never use gradients", "default": False}])
    _ingest(run, n, {"p1": "pick"})
    out = tmp_path / "profile.md"
    profile.apply_review(run, n, out)
    data = profile.read_profile(out)
    assert data["Liked traits"] == ["Warm paper grounds"] and data["Disliked traits"] == []
    assert "REWORDED" not in out.read_text(encoding="utf-8")


def test_apply_review_refuses_without_snapshot(run, tmp_path, capsys):
    _proposals(run)
    n = _render(run)
    _ingest(run, n, {"p1": "pick"})
    (run.path / "review" / f"{n}-proposals.json").unlink()
    with pytest.raises(ValueError, match="review/1-proposals.json"):
        profile.apply_review(run, n, tmp_path / "profile.md")
    assert main(["profile", "apply", str(run.path), str(n)]) == 1
    assert "proposals" in capsys.readouterr().err
    assert not (tmp_path / "profile.md").exists()


HAND = """Some preamble I wrote
before any heading.

# Taste profile

## Liked traits

- Grain
  - nested detail
* star bullet
Wrapped prose that runs
over two lines.

### Sub heading

1. numbered
> a quote

```
## not a heading
- not a bullet
```

## Fonts I own

- Söhne

## Rules

- One accent only
"""


def _subsequence(old: list[str], new: list[str]) -> bool:
    it = iter(new)
    return all(any(x == y for y in it) for x in old)


def test_apply_review_is_append_only(run, tmp_path):
    _proposals(run, [{"id": "p1", "section": "Liked traits", "text": "Warm paper", "default": True},
                     {"id": "p2", "section": "Rules", "text": "No gradients", "default": True},
                     {"id": "p3", "section": "References", "text": "Swiss archive", "default": True},
                     {"id": "p4", "section": "Rules", "text": "one   ACCENT only", "default": True}])
    _brief(run.path)
    _review(run, {"p1": "pick", "p2": "pick", "p3": "pick", "p4": "pick"})
    out = tmp_path / "profile.md"
    out.write_text(HAND, encoding="utf-8")
    profile.apply_review(run, 1, out)
    new = out.read_text(encoding="utf-8")
    old_lines, new_lines = HAND.splitlines(), new.splitlines()
    assert _subsequence(old_lines, new_lines)
    assert len(new_lines) == len(old_lines) + 10   # 2 bullets + 2 new sections of 4 lines each
    # new lines sit at the end of their sections
    assert new_lines.index("- Warm paper") == new_lines.index("```", new_lines.index("```") + 1) + 1
    assert new_lines.index("- No gradients") == new_lines.index("- One accent only") + 1
    assert new.count("ACCENT") == 0
    assert new_lines.index("## References") < new_lines.index("## Projects")
    assert new_lines[-1] == f"- {TODAY} shop: Grid zine"
    assert new.startswith("Some preamble I wrote\nbefore any heading.\n")
    assert "- not a bullet" in new and new.count("- Warm paper") == 1
