from PIL import Image

from taste.boards.sheet import contact_sheets


def test_contact_sheets_paginate(tmp_path):
    images = tmp_path / "images"; images.mkdir()
    recs = []
    for i in range(1, 24):
        Image.new("RGB", (800, 600), (i * 10, 0, 0)).save(images / f"i{i:03}.jpg")
        recs.append({"id": f"i{i:03}", "file": f"i{i:03}.jpg"})
    sheets = contact_sheets({"images": recs}, images, tmp_path / "sheets")
    assert [p.name for p in sheets] == ["sheet-x-1.png", "sheet-x-2.png"]
    assert Image.open(sheets[0]).size == (1500, 1200)   # 5 cols x 4 rows of 300px
    assert Image.open(sheets[1]).size == (1500, 300)    # 3 left -> 1 row


def test_contact_sheets_clears_old_sheets(tmp_path):
    images = tmp_path / "images"; images.mkdir()
    Image.new("RGB", (800, 600)).save(images / "i001.jpg")
    out = tmp_path / "sheets"; out.mkdir()
    Image.new("RGB", (10, 10)).save(out / "sheet-7.png")
    (out / "keep.txt").write_text("x")
    contact_sheets({"images": [{"id": "i001", "file": "i001.jpg"}]}, images, out)
    assert sorted(p.name for p in out.iterdir()) == ["keep.txt", "sheet-x-1.png"]


def test_contact_sheets_grouped_by_style(tmp_path):
    images = tmp_path / "images"; images.mkdir()
    recs = []
    for i, style in enumerate(["1", "2", "1", None], 1):
        Image.new("RGB", (800, 600)).save(images / f"i{i:03}.jpg")
        recs.append({"id": f"i{i:03}", "file": f"i{i:03}.jpg", "style": style})
    sheets = contact_sheets({"images": recs}, images, tmp_path / "sheets")
    assert [p.name for p in sheets] == ["sheet-1-1.png", "sheet-2-1.png", "sheet-x-1.png"]
    assert Image.open(sheets[0]).size == (1500, 300)
