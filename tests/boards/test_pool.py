import pytest
from PIL import Image

from taste.boards.models import Candidate
from taste.boards.pool import build_pool, dominant_colours


def img(path, size=(800, 600), colour=(200, 30, 30), mode="RGB"):
    im = Image.new("RGB", size, colour)
    if mode != "RGB":
        im = im.convert(mode)
    im.save(path)
    return path


def cand(path, kind="site"):
    return Candidate(kind, path, "https://src", "Note", "T")


def test_dominant_colours():
    im = Image.new("RGB", (100, 100), (255, 0, 0))
    im.paste((0, 0, 255), (0, 0, 30, 100))
    cols = dominant_colours(im, 2)
    assert cols[0] == "#ff0000" and cols[1] == "#0000ff"


def test_build_pool_normalises_and_resizes(tmp_path):
    raw = tmp_path / "raw"; raw.mkdir()
    pool = build_pool([cand(img(raw / "a.png", size=(3200, 1000)))], tmp_path / "images")
    (rec,) = pool["images"]
    assert rec["id"] == "i001" and rec["file"] == "i001.jpg"
    assert (rec["width"], rec["height"]) == (1600, 500)
    out = Image.open(tmp_path / "images" / "i001.jpg")
    assert out.format == "JPEG" and out.size == (1600, 500)
    assert rec["colours"][0] == "#c81e1e"


def test_build_pool_rejects_small_and_duplicates(tmp_path):
    raw = tmp_path / "raw"; raw.mkdir()
    a = img(raw / "a.png")
    b = img(raw / "b.png")                       # identical -> duplicate
    small = img(raw / "s.png", size=(900, 300))  # short side < 400
    pool = build_pool([cand(a), cand(b), cand(small)], tmp_path / "images")
    assert [r["id"] for r in pool["images"]] == ["i001"]
    reasons = sorted(r["reason"] for r in pool["rejected"])
    assert reasons == ["duplicate of i001", "too small (900x300)"]


def test_build_pool_handles_odd_modes_and_junk(tmp_path):
    raw = tmp_path / "raw"; raw.mkdir()
    cmyk = img(raw / "c.jpg", colour=(10, 200, 10), mode="CMYK")
    rgba = raw / "r.png"
    Image.new("RGBA", (800, 800), (0, 0, 255, 0)).save(rgba)
    pal = img(raw / "p.png", colour=(240, 240, 20), mode="P")
    gif = raw / "g.gif"
    frames = [Image.new("RGB", (600, 600), c) for c in ((1, 2, 3), (250, 0, 250))]
    frames[0].save(gif, save_all=True, append_images=frames[1:])
    junk = raw / "blocked.jpg"
    junk.write_text("<html>403</html>")
    pool = build_pool([cand(p) for p in (cmyk, rgba, pal, gif, junk)], tmp_path / "images")
    assert len(pool["images"]) == 4
    assert pool["rejected"] == [{"source": str(junk), "reason": "not an image"}]


def test_build_pool_is_rerunnable(tmp_path):
    raw = tmp_path / "raw"; raw.mkdir()
    images = tmp_path / "images"
    build_pool([cand(img(raw / "a.png")), cand(img(raw / "b.png", colour=(0, 0, 0)))], images)
    pool = build_pool([cand(img(raw / "c.png", colour=(9, 99, 199)))], images)
    assert [r["id"] for r in pool["images"]] == ["i001"]
    assert sorted(p.name for p in images.iterdir()) == ["i001.jpg"]


def test_build_pool_rejects_decompression_bomb(tmp_path, monkeypatch):
    raw = tmp_path / "raw"; raw.mkdir()
    big = img(raw / "big.png", size=(3000, 1000))
    ok = img(raw / "ok.png", colour=(0, 0, 0))
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1_000_000)   # big is over twice the limit
    pool = build_pool([cand(big), cand(ok)], tmp_path / "images")
    assert [r["id"] for r in pool["images"]] == ["i001"]
    assert pool["rejected"] == [{"source": str(big), "reason": "too large"}]


@pytest.mark.filterwarnings("error")
def test_build_pool_loads_big_jpeg_reduced(tmp_path, monkeypatch):
    raw = tmp_path / "raw"; raw.mkdir()
    scan = img(raw / "scan.jpg", size=(4000, 3000))
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 7_000_000)   # over the warning limit, under the error one
    pool = build_pool([cand(scan)], tmp_path / "images")
    assert pool["rejected"] == []
    assert (pool["images"][0]["width"], pool["images"][0]["height"]) == (1600, 1200)


def test_build_pool_carries_style(tmp_path):
    raw = tmp_path / "raw"; raw.mkdir()
    c = cand(img(raw / "a.png"))
    c.style = "3"
    pool = build_pool([c, cand(img(raw / "b.png", colour=(0, 0, 0)))], tmp_path / "images")
    assert [r["style"] for r in pool["images"]] == ["3", None]


def test_build_pool_records_the_original_file_name(tmp_path):
    raw = tmp_path / "raw"; raw.mkdir()
    pool = build_pool([cand(img(raw / "inbox-scout-1-5-03.jpg"))], tmp_path / "images")
    assert pool["images"][0]["origin"] == "inbox-scout-1-5-03.jpg"
