from pathlib import Path

from PIL import Image, ImageFont

from taste.library import thumbs


def test_make_thumb_resizes_and_hashes(tmp_path):
    src = tmp_path / "big.png"
    Image.new("RGB", (1600, 800), (200, 30, 30)).save(src)
    out, h = thumbs.make_thumb(src, tmp_path / "t.jpg")
    with Image.open(out) as im:
        assert im.size == (400, 200) and im.format == "JPEG"
    assert len(h) == 16 and all(c in "0123456789abcdef" for c in h)
    _, h2 = thumbs.make_thumb(src, tmp_path / "t2.jpg")
    assert h == h2


def test_make_thumb_flattens_alpha(tmp_path):
    src = tmp_path / "a.png"
    Image.new("RGBA", (500, 500), (0, 0, 0, 0)).save(src)
    out, _ = thumbs.make_thumb(src, tmp_path / "t.jpg")
    with Image.open(out) as im:
        assert im.getpixel((10, 10)) == (255, 255, 255)


def test_swatch(tmp_path):
    out = thumbs.swatch(["#ff0000", "#00ff00", "#0000ff"], tmp_path / "s.jpg")
    with Image.open(out) as im:
        assert im.size == (400, 120)
        assert im.getpixel((10, 60))[0] > 200 and im.getpixel((390, 60))[2] > 200


def test_specimen_renders_text(tmp_path):
    path = getattr(ImageFont.load_default(), "path", None)   # a BytesIO on Pillow 12: then use the default font
    font = Path(path) if isinstance(path, (str, Path)) else None
    out = thumbs.specimen(font, "Fallback Sans", tmp_path / "f.jpg")
    with Image.open(out) as im:
        assert im.size == (400, 220)
        assert min(im.convert("L").getextrema()) < 120   # dark text was drawn


def test_specimen_corrupt_font_falls_back(tmp_path):
    bad = tmp_path / "bad.ttf"
    bad.write_bytes(b"not a font")
    out = thumbs.specimen(bad, "Broken", tmp_path / "f.jpg")
    with Image.open(out) as im:
        assert im.size == (400, 220)
        assert min(im.convert("L").getextrema()) < 120


def test_svg_tile(tmp_path):
    out = thumbs.svg_to_png('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M0 0h24v24H0z"/></svg>',
                            tmp_path / "i.png")
    if out is not None:
        with Image.open(out) as im:
            assert im.size[0] >= 24


def test_svg_to_png_returns_none_when_rasteriser_fails(tmp_path, monkeypatch):
    import sys
    import types

    def boom(**kw):
        raise ValueError("malformed svg")

    monkeypatch.setitem(sys.modules, "cairosvg", types.SimpleNamespace(svg2png=boom))
    assert thumbs.svg_to_png("<svg", tmp_path / "x.png") is None


def test_svg_to_png_returns_none_when_cairo_lib_missing(tmp_path, monkeypatch):
    import builtins

    real = builtins.__import__

    def fake(name, *a, **k):
        if name == "cairosvg":
            raise OSError("no library called cairo")
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake)
    assert thumbs.svg_to_png("<svg/>", tmp_path / "x.png") is None
