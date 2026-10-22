import json
from datetime import date
from taste.boards.run import Run, slugify, data_root, vault_root
from taste.boards.models import Candidate


def test_slugify():
    assert slugify("Athens Style — Renovation!") == "athens-style-renovation"
    assert slugify("  ") == "untitled"


def test_create_makes_dated_folder(tmp_path):
    run = Run.create("My Project", date=date(2026, 10, 6), root=tmp_path)
    assert run.path == tmp_path / "runs" / "2026-10-06-my-project"
    assert run.images.is_dir() and run.raw.is_dir()


def test_create_twice_same_day_reuses_folder(tmp_path):
    a = Run.create("x", date=date(2026, 10, 6), root=tmp_path)
    b = Run.create("x", date=date(2026, 10, 6), root=tmp_path)
    assert a.path == b.path


def test_write_read_roundtrip(tmp_path):
    run = Run(tmp_path)
    p = run.write("brief.json", {"summary": "ü"})
    assert p == tmp_path / "brief.json"
    assert json.loads(p.read_text(encoding="utf-8")) == {"summary": "ü"}
    assert run.read("brief.json") == {"summary": "ü"}
    assert run.has("brief.json") and not run.has("nope.json")


def test_env_roots(monkeypatch, tmp_path):
    monkeypatch.setenv("MOODBOARDS_DATA", str(tmp_path / "d"))
    monkeypatch.setenv("MOODBOARDS_VAULT", str(tmp_path / "v"))
    assert data_root() == tmp_path / "d"
    assert vault_root() == tmp_path / "v"


def test_candidate_fields(tmp_path):
    c = Candidate(kind="site", path=tmp_path / "a.png", source_url="https://x", source_note="X", title="X")
    assert c.kind == "site"


def test_clean_text_markdown():
    from taste.boards.run import clean_text
    assert clean_text("Nice  poster\n# Heading ]x(y)[z\\") == "Nice poster # Heading \\]x\\(y\\)\\[z\\\\"


def test_clean_text_plain_and_truncated():
    from taste.boards.run import clean_text
    assert clean_text(" a\n\tb [c] ", markdown=False) == "a b [c]"
    long = clean_text("word " * 60, limit=20, markdown=False)
    assert len(long) == 20 and long.endswith("…")
    assert clean_text(None) == ""
