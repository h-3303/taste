"""Big boards: sections, palette variants with contrast, font pairings, components."""
import json
import re

import pytest
from PIL import Image

from taste.boards.canvas import contrast, render_canvas
from taste.boards.directions import style_errors


def setup(tmp_path, n=20):
    images = tmp_path / "images"; images.mkdir()
    pool = {"images": []}
    for i in range(1, n + 1):
        iid = f"i{i:03}"
        Image.new("RGB", (600, 400)).save(images / f"{iid}.jpg")
        pool["images"].append({"id": iid, "file": f"{iid}.jpg", "source_url": f"https://src/{i}",
                               "source_note": "Cosmos", "title": "T", "kind": "inbox", "style": "1"})
    d = {"id": "1", "name": "Lacquer Red", "rationale": "Warm.", "image_ids": [f"i{j:03}" for j in range(1, n + 1)],
         "palette": ["#5a0f12", "#f3e6d0", "#c8a24a", "#1a0b0b", "#e34a2f"],
         "type": {"display": "Playfair Display", "text": "Source Serif 4"}, "motifs": ["a", "b", "c"], "axes": {},
         "sections": {"ui": ["i001", "i002"], "graphic": ["i003", "i004", "i005"], "texture": ["i006"]},
         "palettes": {"light": {"bg": "#f3e6d0", "text": "#1a0b0b", "accent": "#9b1c1c"},
                      "dark": {"bg": "#1a0b0b", "text": "#f3e6d0", "accent": "#e34a2f"},
                      "sunlight": {"bg": "#ffffff", "text": "#000000", "accent": "#8a0000"}},
         "fonts": [{"display": "Playfair Display", "text": "Source Serif 4", "mono": "IBM Plex Mono",
                    "licence": "OFL", "urls": ["https://fonts.google.com/specimen/Playfair+Display"]}],
         "components": [{"name": "Haze", "kind": "compose", "licence": "Apache-2.0",
                         "url": "https://github.com/chrisbanes/haze", "note": "blur"},
                        {"name": "Evil", "kind": "web", "licence": "MIT", "url": "javascript:alert(1)", "note": ""}]}
    return images, pool, {"directions": [d]}


def test_contrast_matches_wcag():
    assert contrast("#000000", "#ffffff") == pytest.approx(21.0)
    assert contrast("#777777", "#ffffff") == pytest.approx(4.48, abs=0.01)


def test_board_renders_sections_palettes_fonts_components(tmp_path):
    images, pool, dirs = setup(tmp_path)
    html = render_canvas(dirs, pool, images, tmp_path / "c", "waymark").read_text()
    for label in ("UI", "Graphic", "Texture", "Light", "Dark", "Sunlight", "Components"):
        assert f">{label}<" in html
    assert "21.0" in html                                         # sunlight text/bg ratio shown
    assert "IBM+Plex+Mono" in html and "Source+Serif+4" in html    # every pairing face loaded
    assert 'href="https://github.com/chrisbanes/haze"' in html
    assert "javascript:" not in html                               # non-http links dropped
    assert html.count('<img src="img/') == 20                      # every image still shown once


def test_plain_board_still_renders_as_collage(tmp_path):
    images, pool, dirs = setup(tmp_path, n=10)
    d = dirs["directions"][0]
    for k in ("sections", "palettes", "fonts", "components"):
        d.pop(k)
    html = render_canvas(dirs, pool, images, tmp_path / "c", "w").read_text()
    assert 'class="collage"' in html and ">Sunlight<" not in html


@pytest.mark.parametrize("mutate,needle", [
    (lambda d: d["palettes"]["dark"].__setitem__("bg", "red;x"), "palettes"),
    (lambda d: d["fonts"][0].__setitem__("mono", "Bad';x"), "bad font name"),
    (lambda d: d["sections"].__setitem__("ui", ["i999"]), "section ui"),
    (lambda d: d["sections"].__setitem__("misc", ["i001"]), "section misc"),
])
def test_extras_are_validated(tmp_path, mutate, needle):
    _, _, dirs = setup(tmp_path)
    d = dirs["directions"][0]
    mutate(d)
    assert any(needle in e for e in style_errors(d))


def test_canvas_ships_web_sized_copies(tmp_path):
    images, pool, dirs = setup(tmp_path, n=8)
    for r in pool["images"]:
        Image.new("RGB", (2400, 1600), (90, 20, 20)).save(images / r["file"])
    out = tmp_path / "c"
    render_canvas(dirs, pool, images, out, "w")
    for f in json.loads((out / "files.json").read_text()):
        assert max(Image.open(out / f).size) <= 1000
