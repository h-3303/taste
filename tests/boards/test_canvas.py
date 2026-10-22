import json
import re

import pytest
from PIL import Image

from taste.boards.canvas import render_canvas


def setup(tmp_path):
    images = tmp_path / "images"; images.mkdir()
    pool = {"images": []}
    for i in range(1, 13):
        iid = f"i{i:03}"
        Image.new("RGB", (800, 600)).save(images / f"{iid}.jpg")
        pool["images"].append({"id": iid, "file": f"{iid}.jpg", "source_url": f"https://src/{i}",
                               "source_note": "Pear" if i == 1 else "Note", "title": "T", "kind": "site"})
    dirs = {"directions": [{
        "id": str(k), "name": f"<Dir {k}>", "rationale": "Why & how.",
        "image_ids": [f"i{j:03}" for j in range(1, 9)] if k < 3 else [f"i{j:03}" for j in range(5, 13)],
        "palette": ["#111111", "#222222", "#333333", "#444444", "#555555"],
        "type": {"display": "Archivo Black", "text": "IBM Plex Sans"},
        "motifs": ["grid", "rule", "dot"], "axes": {},
    } for k in range(1, 5)]}
    return images, pool, dirs


def test_render_canvas(tmp_path):
    images, pool, dirs = setup(tmp_path)
    out = tmp_path / "canvas"
    html = render_canvas(dirs, pool, images, out, "Athens Style").read_text()
    assert html.count('class="board"') == 4
    assert "&lt;Dir 1&gt;" in html and "<Dir 1>" not in html          # escaped
    assert html.count('data-choose="') == 4
    assert 'claude.use("db")' in html and '"picks/current"' in html
    assert "fonts.googleapis.com" in html and "Archivo+Black" in html
    links = re.findall(r'<link rel="stylesheet" href="([^"]+)"', html)
    assert len(links) == 2 and all(u.count("family=") == 1 for u in links)   # one request per family
    for src in re.findall(r'<img src="([^"]+)"', html):
        assert src.startswith("img/")
    assert 'href="https://src/1"' in html and "Pear" in html             # every image traces to source
    files = json.loads((out / "files.json").read_text())
    assert set(files) == {f"img/i{j:03}.jpg" for j in range(1, 13)}
    assert all((out / k).exists() for k in files)
    assert "<title>Athens Style moodboards</title>" in html


@pytest.mark.parametrize("mutate", [
    lambda d: d["palette"].__setitem__(0, "red;background:url(x)"),
    lambda d: d["type"].__setitem__("display", "Bad';color:red"),
    lambda d: d["type"].__setitem__("text", "Bad\"x"),
])
def test_hostile_style_values_rejected(tmp_path, mutate):
    images, pool, dirs = setup(tmp_path)
    mutate(dirs["directions"][1])
    with pytest.raises(ValueError, match="direction 2"):
        render_canvas(dirs, pool, images, tmp_path / "canvas", "T")


def test_db_use_is_guarded(tmp_path):
    images, pool, dirs = setup(tmp_path)
    html = render_canvas(dirs, pool, images, tmp_path / "canvas", "T").read_text()
    assert 'try { db = window.claude ? await window.claude.use("db") : null; } catch (e) { db = null; }' in html


@pytest.mark.browser
@pytest.mark.parametrize("w,h", [(375, 800), (1440, 900)])
def test_no_horizontal_scroll(tmp_path, w, h):
    from playwright.sync_api import sync_playwright
    images, pool, dirs = setup(tmp_path)
    index = render_canvas(dirs, pool, images, tmp_path / "canvas", "T")
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": w, "height": h})
        page.goto(index.as_uri())
        sw, iw = page.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
        b.close()
    assert sw <= iw


def test_rerender_into_same_dir_replaces_output(tmp_path):
    images, pool, dirs = setup(tmp_path)
    out = tmp_path / "canvas"
    render_canvas(dirs, pool, images, out, "T")
    for d in dirs["directions"]:
        d["image_ids"] = [f"i{j:03}" for j in range(1, 9)]
    render_canvas(dirs, pool, images, out, "T")
    files = json.loads((out / "files.json").read_text())
    assert set(files) == {f"img/i{j:03}.jpg" for j in range(1, 9)}
    assert sorted(f"img/{p.name}" for p in (out / "img").iterdir()) == sorted(files)
    assert sorted(p.name for p in out.iterdir()) == ["files.json", "img", "index.html"]


def test_bad_style_leaves_previous_render(tmp_path):
    images, pool, dirs = setup(tmp_path)
    out = tmp_path / "canvas"
    render_canvas(dirs, pool, images, out, "T")
    dirs["directions"][3]["palette"][0] = "nope"
    with pytest.raises(ValueError, match="direction 4"):
        render_canvas(dirs, pool, images, out, "T")
    assert (out / "index.html").exists() and len(list((out / "img").iterdir())) == 12


def test_caption_links_only_for_http(tmp_path):
    images, pool, dirs = setup(tmp_path)
    pool["images"][1].update(source_url="", source_note="inbox")
    pool["images"][2].update(source_url="javascript:alert(1)", source_note="Sneaky")
    html = render_canvas(dirs, pool, images, tmp_path / "canvas", "T").read_text()
    assert 'href=""' not in html and "javascript:" not in html
    assert "<figcaption>inbox · i002</figcaption>" in html
    assert "<figcaption>Sneaky · i003</figcaption>" in html
    assert 'href="https://src/1"' in html
    assert "@media (hover:none){.collage figcaption{opacity:1}}" in html


def test_captions_are_single_short_lines(tmp_path):
    images, pool, dirs = setup(tmp_path)
    pool["images"][0].update(title="Line one\nLine   two", source_note="N" * 300)
    html = render_canvas(dirs, pool, images, tmp_path / "canvas", "T").read_text()
    assert 'alt="Line one Line two"' in html
    assert "N" * 119 + "…" in html and "N" * 120 not in html


def test_heading_counts_the_directions(tmp_path):
    images, pool, dirs = setup(tmp_path)
    dirs["directions"] = dirs["directions"][:3]
    html = render_canvas(dirs, pool, images, tmp_path / "c", "X").read_text()
    assert "3 directions" in html and "four directions" not in html


def test_render_refuses_a_non_empty_out_without_an_earlier_render(tmp_path):
    images, pool, dirs = setup(tmp_path)
    out = tmp_path / "mine"
    out.mkdir()
    (out / "index.html").write_text("my own page")
    with pytest.raises(ValueError, match="not empty"):
        render_canvas(dirs, pool, images, out, "T")
    assert (out / "index.html").read_text() == "my own page"
