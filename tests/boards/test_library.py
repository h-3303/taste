import pytest
from taste.boards.library import parse_note, load_library

GOOD = """---
type: resource
title: Designspiration
url: https://www.designspiration.com
category: inspiration-galleries
tags:
- inspiration
- colour-search
url_status: verified
resource_type: site
filed_under: '[[Inspiration galleries]]'
---
Design inspiration search by keyword or colour.

## Mentions
- something
"""


def write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_parse_good_note(tmp_path):
    r = parse_note(write(tmp_path, "Designspiration.md", GOOD))
    assert r == {
        "note": "Designspiration",
        "title": "Designspiration",
        "url": "https://www.designspiration.com",
        "category": "inspiration-galleries",
        "filed_under": "Inspiration galleries",
        "tags": ["inspiration", "colour-search"],
        "resource_type": "site",
        "url_status": "verified",
        "summary": "Design inspiration search by keyword or colour.",
    }


def test_category_index_notes_are_skipped(tmp_path):
    assert parse_note(write(tmp_path, "AI tools.md", "---\ntype: category\n---\nx")) is None


@pytest.mark.parametrize("text", [
    "no frontmatter at all",
    "---\ntype: resource\ntitle: Unclosed\n",
    "---\n: : not yaml [\n---\nbody",
    "---\n- a list\n---\nbody",
])
def test_parse_note_odd_frontmatter(tmp_path, text):
    assert parse_note(write(tmp_path, "odd.md", text)) is None


def test_tags_as_string_and_missing_fields_coerced(tmp_path):
    r = parse_note(write(tmp_path, "X.md", "---\ntype: resource\ntags: solo\n---\n"))
    assert r["tags"] == ["solo"]
    assert r["url"] == "" and r["title"] == "X" and r["summary"] == ""


def test_load_library_sorted_and_filtered(tmp_path):
    res = tmp_path / "Resources"
    res.mkdir()
    write(res, "B.md", GOOD.replace("Designspiration", "B"))
    write(res, "A.md", GOOD.replace("Designspiration", "A"))
    write(res, "Index.md", "---\ntype: category\n---\n")
    assert [r["note"] for r in load_library(tmp_path)] == ["A", "B"]


def test_load_library_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_library(tmp_path)
