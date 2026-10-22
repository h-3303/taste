import json

import pytest
from PIL import Image

from taste import config
from taste.cli import main as taste_main
from taste.connectors import REGISTRY, enabled
from taste.connectors.folders import FolderImages, FolderNotes
from taste.connectors.presets import InstagramMedia, ObsidianResources, parse_note

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


@pytest.fixture(autouse=True)
def data(monkeypatch, tmp_path):
    monkeypatch.setenv("TASTE_DATA", str(tmp_path / "data"))


def write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_enabled_empty_without_config():
    assert enabled() == []


def test_registry_names():
    assert set(REGISTRY) == {"folder-images", "folder-notes", "obsidian-resources", "instagram-media"}


def test_connect_folder_images_lists_tmp_images(tmp_path):
    pics = tmp_path / "pics"
    (pics / "sub").mkdir(parents=True)
    for n in ("a.jpg", "sub/b.png"):
        Image.new("RGB", (4, 4)).save(pics / n)
    (pics / "notes.txt").write_text("x")
    assert taste_main(["connect", "folder-images", "--path", str(pics)]) == 0
    [c] = enabled()
    assert c.name == "folder-images"
    items = c.items()
    assert sorted(i["path"] for i in items) == sorted([str(pics / "a.jpg"), str(pics / "sub" / "b.png")])
    assert items[0]["url"] is None and items[0]["title"] and "note" in items[0] and "source_url" in items[0]


def test_connect_unknown_name_exits_1(capsys):
    assert taste_main(["connect", "nope"]) == 1
    err = capsys.readouterr()
    assert "folder-images" in err.out + err.err
    assert config.load()["connectors"] == {}


def test_connect_obscura_still_allowed():
    assert taste_main(["connect", "obscura", "--bin", "/x/obscura"]) == 0


def test_disabled_connector_not_listed(tmp_path):
    taste_main(["connect", "folder-images", "--path", str(tmp_path)])
    taste_main(["disconnect", "folder-images"])
    assert enabled() == []


def test_missing_path_skipped_with_warning(tmp_path, capsys):
    taste_main(["connect", "folder-images", "--path", str(tmp_path / "gone")])
    assert enabled() == []
    assert "gone" in capsys.readouterr().err


def test_no_path_skipped_with_warning(capsys):
    config.save({"connectors": {"folder-notes": {"enabled": True}}})
    assert enabled() == []
    assert "folder-notes" in capsys.readouterr().err


def test_folder_notes_embed_and_links(tmp_path):
    notes = tmp_path / "notes"
    notes.mkdir()
    Image.new("RGB", (4, 4)).save(notes / "pic.png")
    (notes / "Moods.md").write_text(
        "# Warm moods\n\n![[pic.png]]\n\nsee https://a.example/x and [b](https://b.example/y.jpg).\n")
    items = FolderNotes(notes).items()
    assert len(items) == 3
    assert {i["title"] for i in items} == {"Warm moods"}
    embed = next(i for i in items if i["path"])
    assert embed["path"] == str(notes / "pic.png") and embed["url"] is None
    assert sorted(i["url"] for i in items if i["url"]) == ["https://a.example/x", "https://b.example/y.jpg"]


def test_folder_notes_title_falls_back_to_filename(tmp_path):
    (tmp_path / "plain.md").write_text("https://a.example/x\n")
    [i] = FolderNotes(tmp_path).items()
    assert i["title"] == "plain"


def test_folder_notes_markdown_image_embed(tmp_path):
    Image.new("RGB", (4, 4)).save(tmp_path / "pic.png")
    (tmp_path / "n.md").write_text("![alt](pic.png)\n![r](https://c.example/z.png)\n")
    items = FolderNotes(tmp_path).items()
    assert [i["path"] for i in items if i["path"]] == [str(tmp_path / "pic.png")]
    assert [i["url"] for i in items if i["url"]] == ["https://c.example/z.png"]
    assert len(items) == 2


# ported from boards/test_library.py
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


def test_obsidian_resources_sorted_and_filtered(tmp_path):
    res = tmp_path / "Resources"
    res.mkdir()
    write(res, "B.md", GOOD.replace("Designspiration", "B"))
    write(res, "A.md", GOOD.replace("Designspiration", "A"))
    write(res, "Index.md", "---\ntype: category\n---\n")
    assert [r["note"] for r in ObsidianResources(tmp_path).load()] == ["A", "B"]


def test_obsidian_resources_missing_is_empty(tmp_path):
    assert ObsidianResources(tmp_path).load() == []


def test_obsidian_items_shape(tmp_path):
    res = tmp_path / "Resources"
    res.mkdir()
    write(res, "A.md", GOOD)
    [i] = ObsidianResources(tmp_path).items()
    assert i["url"] == "https://www.designspiration.com" and i["path"] is None and i["title"] == "Designspiration"


# ported from boards/test_vaultmedia.py
def make_media(tmp_path):
    media = tmp_path / "creator"
    media.mkdir(parents=True)
    for n in ("ABC_1.jpg", "ABC_2.png", "ABC.mp4", "XYZ_1.jpg"):
        (media / n).write_bytes(b"x")
    return tmp_path


def test_instagram_media_finds_post_images(tmp_path):
    ig = InstagramMedia(make_media(tmp_path))
    items = ig.for_codes(["ABC", "MISSING"])
    assert sorted(i["path"].rsplit("/", 1)[1] for i in items) == ["ABC_1.jpg", "ABC_2.png"]
    assert {i["note"] for i in items} == {"ig-ABC"}
    assert items[0]["source_url"] == "https://www.instagram.com/p/ABC/"
    assert items[0]["title"] == "@creator ABC"


def test_instagram_media_items_lists_all_images(tmp_path):
    assert len(InstagramMedia(make_media(tmp_path)).items()) == 3


BANNED = "https://cdn.are.na/x.png https://www.artvee.com/y.jpg"


def test_folder_notes_drops_banned_hosts(tmp_path):
    (tmp_path / "n.md").write_text(f"# N\n{BANNED} ![a](https://cdn.are.na/z.png) https://ok.example/p\n")
    assert [i["url"] for i in FolderNotes(tmp_path).items()] == ["https://ok.example/p"]


def test_connector_candidates_never_fetch_banned(tmp_path):
    from taste.boards.cli import connector_candidates

    class Leaky(FolderNotes):   # a connector that fails to filter at the source
        def items(self):
            return [{"path": None, "url": u, "title": "t", "source_url": u, "note": "n"} for u in BANNED.split()]

    class Http:
        def download(self, url, dest):
            raise AssertionError(f"fetched {url}")
    cands, failures = connector_candidates([Leaky(tmp_path)], tmp_path / "raw", Http())
    assert cands == [] and len(failures) == 2 and all("banned host" in f for f in failures)
