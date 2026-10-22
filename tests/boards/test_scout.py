import functools
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from PIL import Image

from taste.boards import scout

FIX = Path(__file__).parent / "fixtures"
COSMOS_HTML = (FIX / "cosmos_search.html").read_text()
DSP_HTML = (FIX / "designspiration_search.html").read_text()


def test_parse_cosmos_keeps_result_images_only():
    urls = scout.parse_cosmos(COSMOS_HTML)
    assert len(urls) == 6                                     # 6 results, repeat and avatar dropped
    assert all(u.startswith("https://cdn.cosmos.so/") and u.endswith("?format=jpeg&w=1600") for u in urls)
    assert not any("avatar" in u for u in urls)


def test_parse_designspiration_upsizes_to_692():
    urls = scout.parse_designspiration(DSP_HTML)
    assert len(urls) == 5
    assert all(u.startswith("https://dspncdn.com/a1/media/692x/") for u in urls)


def fake_render(pages):
    def render(url):
        for key, html in pages.items():
            if key in url:
                return html
        return "<html></html>"
    return render


def fake_download(url, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    Image.effect_noise((700, 500), 80).convert("RGB").save(dest, "JPEG")
    return dest


def test_scout_downloads_numbers_and_sheets(tmp_path):
    res = scout.scout(tmp_path, "2", cosmos="neumorphic ui", designspiration=None,
                      render=fake_render({"cosmos.so": COSMOS_HTML}), download=fake_download)
    folder = tmp_path / "scout" / "2"
    assert sorted(p.name[:2] for p in folder.glob("*.jpg")) == [f"{n:02d}" for n in range(1, 7)]
    assert (tmp_path / "scout" / "sheet-2-1.png").exists()
    saved = json.loads((folder / "scout.json").read_text())
    assert saved == res
    first = res["items"][0]
    assert first["n"] == "01" and first["note"] == "Cosmos"
    assert first["source"] == "https://www.cosmos.so/search/elements/neumorphic%20ui"
    assert first["image_url"].startswith("https://cdn.cosmos.so/")


def test_scout_falls_back_to_designspiration(tmp_path):
    res = scout.scout(tmp_path, "4", cosmos="blueprint", designspiration="blueprint",
                      render=fake_render({"designspiration": DSP_HTML}), download=fake_download)
    assert [i["note"] for i in res["items"]] == ["Designspiration"] * 5
    assert any("Cosmos returned nothing" in n for n in res["notes"])


def test_scout_combines_both_and_limits(tmp_path):
    res = scout.scout(tmp_path, "1", cosmos="swiss", designspiration="swiss", limit=8,
                      render=fake_render({"cosmos.so": COSMOS_HTML, "designspiration": DSP_HTML}),
                      download=fake_download)
    assert [i["note"] for i in res["items"]] == ["Cosmos"] * 6 + ["Designspiration"] * 2


def test_scout_rerun_replaces_previous(tmp_path):
    render = fake_render({"cosmos.so": COSMOS_HTML})
    scout.scout(tmp_path, "2", cosmos="a", designspiration=None, render=render, download=fake_download)
    scout.scout(tmp_path, "2", cosmos="a", designspiration=None, limit=2, render=render, download=fake_download)
    assert len(list((tmp_path / "scout" / "2").glob("*.jpg"))) == 2


def test_scout_records_failed_downloads(tmp_path):
    def flaky(url, dest):
        if url.endswith("w=1600") and "d190" not in url:
            raise OSError("boom")
        return fake_download(url, dest)
    res = scout.scout(tmp_path, "2", cosmos="a", designspiration=None,
                      render=fake_render({"cosmos.so": COSMOS_HTML}), download=flaky)
    assert len(res["items"]) <= 1 and any("boom" in n for n in res["notes"])


def test_keep_moves_chosen_into_inbox(tmp_path):
    scout.scout(tmp_path, "2", cosmos="neu", designspiration=None,
                render=fake_render({"cosmos.so": COSMOS_HTML}), download=fake_download)
    inbox = tmp_path / "inbox"
    kept = scout.keep(tmp_path, "2", ["01", "3"], inbox)
    assert len(kept) == 2
    files = sorted(p.name for p in (inbox / "2").iterdir())
    assert len(files) == 3 and "sources.txt" in files
    lines = (inbox / "2" / "sources.txt").read_text().splitlines()
    assert lines[0].split("\t")[1:] == ["https://www.cosmos.so/search/elements/neu", "Cosmos", "Cosmos · neu #01"]
    assert lines[1].split("\t")[3] == "Cosmos · neu #03"


def test_keep_rejects_unknown_numbers(tmp_path):
    scout.scout(tmp_path, "2", cosmos="neu", designspiration=None,
                render=fake_render({"cosmos.so": COSMOS_HTML}), download=fake_download)
    with pytest.raises(ValueError, match="99"):
        scout.keep(tmp_path, "2", ["99"], tmp_path / "inbox")


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.mark.browser
def test_render_page_returns_rendered_html(tmp_path):
    (tmp_path / "page.html").write_text(
        "<html><body><div id=x></div><script>document.getElementById('x').innerHTML="
        "'<img data-testid=\"element-image-img\" src=\"https://cdn.cosmos.so/abc?w=400\">'</script></body></html>")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(tmp_path)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        html = scout.render_page(f"http://127.0.0.1:{httpd.server_port}/page.html", settle_ms=200)
    finally:
        httpd.shutdown()
    assert scout.parse_cosmos(html) == ["https://cdn.cosmos.so/abc?format=jpeg&w=1600"]


def test_keep_files_into_dlib(tmp_path):
    run = tmp_path / "run"; (run / "scout" / "1").mkdir(parents=True)
    (run / "brief.json").write_text(json.dumps({"styles": [{"id": "1", "name": "Swiss International"}]}))
    Image.new("RGB", (500, 500)).save(run / "scout" / "1" / "01.jpg")
    (run / "scout" / "1" / "scout.json").write_text(json.dumps({"style": "1", "items": [
        {"n": "01", "file": "01.jpg", "image_url": "https://cdn/x.jpg", "source": "https://www.cosmos.so/search/elements/swiss", "note": "Cosmos"}], "notes": []}))
    calls = []
    kept = scout.keep(run, "1", ["01"], tmp_path / "inbox", dlib_add=lambda path, src, lang: calls.append((path.name, src, lang)))
    assert calls == [(kept[0].name, "https://www.cosmos.so/search/elements/swiss", "Swiss International")]


def test_scout_accepts_the_survey_target(tmp_path):
    res = scout.scout(tmp_path, "survey", cosmos="editorial layout", designspiration=None,
                      render=fake_render({"cosmos.so": COSMOS_HTML}), download=fake_download)
    assert len(res["items"]) == 6 and (tmp_path / "scout" / "sheet-survey-1.png").exists()


def test_scout_accepts_any_numbered_style_but_not_names(tmp_path):
    res = scout.scout(tmp_path, "10", cosmos="x", designspiration=None,
                      render=fake_render({"cosmos.so": COSMOS_HTML}), download=fake_download)
    assert len(res["items"]) == 6
    with pytest.raises(ValueError):
        scout.scout(tmp_path, "misc", cosmos="x", designspiration=None,
                    render=fake_render({}), download=fake_download)


def test_keep_after_a_second_scout_never_overwrites(tmp_path):
    render = fake_render({"cosmos.so": COSMOS_HTML})
    inbox = tmp_path / "inbox"
    scout.scout(tmp_path, "3", cosmos="a", designspiration=None, render=render, download=fake_download)
    first = scout.keep(tmp_path, "3", ["01"], inbox)[0]
    before = first.read_bytes()
    scout.scout(tmp_path, "3", cosmos="b", designspiration=None, render=render, download=fake_download)
    second = scout.keep(tmp_path, "3", ["01"], inbox)[0]
    assert second != first and first.read_bytes() == before
    assert len([p for p in (inbox / "3").iterdir() if p.suffix == ".jpg"]) == 2
