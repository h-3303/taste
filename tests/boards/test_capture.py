import functools
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest
from PIL import Image

from taste.boards.capture import allowed, capture_sites

PAGE = """<html><body style="margin:0">
<div style="height:900px;background:#c33"></div><div style="height:900px;background:#33c"></div>
<div id="cookie"><button onclick="this.parentNode.remove()">Accept all</button></div>
{extra}</body></html>"""


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture
def served(tmp_path):
    """Serve tmp_path on localhost: capture only visits http(s) URLs."""
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(tmp_path)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()
    httpd.server_close()


def site(tmp_path, base, name, extra=""):
    (tmp_path / f"{name}.html").write_text(PAGE.format(extra=extra))
    return {"url": f"{base}/{name}.html", "note": f"Note {name}", "title": name}


@pytest.fixture
def no_browser(monkeypatch):
    def boom():
        raise AssertionError("browser launched")
    monkeypatch.setattr("taste.boards.capture.sync_playwright", boom)


@pytest.mark.parametrize("url,reason", [
    ("https://www.are.na/block/1", "site forbids automated access"),
    ("https://are.na/", "site forbids automated access"),
    ("http://artvee.com/?s=x", "site forbids automated access"),
    ("https://www.emuseum.ch/search/x", "site forbids automated access"),
    ("https://gurafiku.tumblr.com/", "site forbids automated access"),
    ("https://designreviewed.com/", "site forbids automated access"),
    ("file:///etc/passwd", "not an http(s) URL"),
    ("javascript:alert(1)", "not an http(s) URL"),
    ("https://notare.na/", None),
    ("https://www.tumblr.com/", None),
    ("https://www.cosmos.so/search/x", None),
])
def test_allowed(url, reason):
    assert allowed(url) == reason


def test_forbidden_sites_skipped_without_browser(tmp_path, no_browser):
    sites = [{"url": "https://www.are.na/block/1", "note": "Arena"},
             {"url": "file:///etc/passwd", "note": "Local"}]
    cands, failures = capture_sites(sites, tmp_path / "raw")
    assert cands == []
    assert failures == ["skipped Arena: site forbids automated access", "skipped Local: not an http(s) URL"]


def test_existing_shots_reused_without_visit(tmp_path, no_browser):
    raw = tmp_path / "raw"; raw.mkdir()
    for i in (1, 2):
        Image.new("RGB", (1440, 900)).save(raw / f"site-note-a-{i}.png")
    s = {"url": "https://a.example/", "note": "Note a", "title": "A"}
    cands, failures = capture_sites([s], raw)
    assert failures == []
    assert [c.path for c in cands] == [raw / "site-note-a-1.png", raw / "site-note-a-2.png"]
    assert all(c.kind == "site" and c.source_url == "https://a.example/" and c.title == "A" for c in cands)


@pytest.mark.browser
def test_capture_two_shots(tmp_path, served):
    cands, failures = capture_sites([site(tmp_path, served, "a")], tmp_path / "raw")
    assert failures == []
    assert [c.path.name for c in cands] == ["site-note-a-1.png", "site-note-a-2.png"]
    top = Image.open(cands[0].path).convert("RGB").getpixel((10, 10))
    below = Image.open(cands[1].path).convert("RGB").getpixel((10, 10))
    assert top[0] > 150 and below[2] > 150          # red top, blue after scroll
    assert Image.open(cands[0].path).size == (1440, 900)


@pytest.mark.browser
def test_capture_survives_never_idle_page(tmp_path, served):
    # unroutable address keeps a request pending, so networkidle never fires
    s = site(tmp_path, served, "busy", extra='<img src="http://10.255.255.1/x.png">')
    cands, failures = capture_sites([s], tmp_path / "raw", idle_timeout_ms=1500)
    assert len(cands) == 2 and failures == []


@pytest.mark.browser
def test_capture_failure_is_recorded(tmp_path):
    bad = {"url": "http://127.0.0.1:9/", "note": "Dead", "title": "Dead"}
    cands, failures = capture_sites([bad], tmp_path / "raw")
    assert cands == [] and len(failures) == 1 and "Dead" in failures[0]
