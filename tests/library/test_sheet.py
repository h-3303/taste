from PIL import Image

from taste.library import sheet


def test_contact_sheets_label_and_placeholder(tmp_path):
    thumbs = tmp_path / "thumbs"; thumbs.mkdir()
    Image.new("RGB", (400, 300), (0, 0, 255)).save(thumbs / "aaaaaa.jpg")
    items = [{"id": "aaaaaa", "title": "Blue", "thumb": "thumbs/aaaaaa.jpg"},
             {"id": "bbbbbb", "title": "No thumb yet", "thumb": None}] + \
            [{"id": f"c{i:05d}", "title": "x", "thumb": None} for i in range(40)]
    paths = sheet.contact_sheets(items, tmp_path, tmp_path / "out", per_sheet=35)
    assert [p.name for p in paths] == ["sheet-1.png", "sheet-2.png"]
    with Image.open(paths[0]) as im:
        assert im.size == (5 * 300, 7 * 300)
        assert im.getpixel((150, 150))[2] > 200         # the blue thumb landed in cell 1
        assert im.getpixel((450, 150)) == (60, 60, 60)   # placeholder grey in cell 2
