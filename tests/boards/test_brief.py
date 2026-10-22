import pytest
from PIL import Image

from taste.boards.brief import write_brief


def fixture(tmp_path):
    images = tmp_path / "images"; images.mkdir()
    pool = {"images": []}
    for i in (1, 2):
        Image.new("RGB", (800, 600)).save(images / f"i00{i}.jpg")
        pool["images"].append({"id": f"i00{i}", "file": f"i00{i}.jpg", "title": f"Ref {i}",
                               "source_url": f"https://ex/{i}", "source_note": "Pear", "kind": "site"})
    dirs = {"directions": [{"id": "2", "name": "Warm Editorial", "rationale": "Soft and bookish.",
                            "image_ids": ["i001", "i002"], "palette": ["#111111", "#eeeeee", "#aa3300", "#ccbbaa", "#334455"],
                            "type": {"display": "Fraunces", "text": "Inter"}, "motifs": ["paper", "margin notes", "drop caps"],
                            "axes": {}}]}
    return images, pool, dirs


def test_write_brief(tmp_path):
    images, pool, dirs = fixture(tmp_path)
    dest = tmp_path / "proj" / "design"
    p = write_brief(dirs, pool, images, "2", "use 3's palette", dest, "athens-style")
    md = p.read_text()
    assert p == dest / "direction.md"
    assert md.startswith("# Design direction: Warm Editorial\n")
    assert "use 3's palette" in md and "#aa3300" in md and "Fraunces" in md
    assert "- [Ref 1](https://ex/1) · library: [[Pear]] · `refs/i001.jpg`" in md
    assert sorted(x.name for x in (dest / "refs").iterdir()) == ["i001.jpg", "i002.jpg"]


def test_write_brief_refuses_overwrite(tmp_path):
    images, pool, dirs = fixture(tmp_path)
    dest = tmp_path / "d"
    write_brief(dirs, pool, images, "2", "", dest, "p")
    with pytest.raises(FileExistsError):
        write_brief(dirs, pool, images, "2", "", dest, "p")
    write_brief(dirs, pool, images, "2", "again", dest, "p", force=True)
    assert "again" in (dest / "direction.md").read_text()


def test_write_brief_unknown_pick(tmp_path):
    images, pool, dirs = fixture(tmp_path)
    with pytest.raises(KeyError):
        write_brief(dirs, pool, images, "9", "", tmp_path / "d", "p")


def test_write_brief_cleans_titles(tmp_path):
    images, pool, dirs = fixture(tmp_path)
    pool["images"][0]["title"] = "Evil](https://bad)\n# Injected heading"
    md = write_brief(dirs, pool, images, "2", "", tmp_path / "d", "p").read_text()
    assert "\n# Injected" not in md
    assert "- [Evil\\]\\(https://bad\\) # Injected heading](https://ex/1)" in md


def test_write_brief_force_clears_refs(tmp_path):
    images, pool, dirs = fixture(tmp_path)
    dest = tmp_path / "d"
    write_brief(dirs, pool, images, "2", "", dest, "p")
    dirs["directions"][0]["image_ids"] = ["i002"]
    write_brief(dirs, pool, images, "2", "", dest, "p", force=True)
    assert [x.name for x in (dest / "refs").iterdir()] == ["i002.jpg"]
