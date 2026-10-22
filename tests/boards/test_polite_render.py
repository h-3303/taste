"""Scout and site capture go through the polite rules: banned hosts and robots.txt are checked before any render."""
from contextlib import contextmanager

import httpx

from taste.boards import capture, scout
from taste.library import fetch as lfetch

DISALLOW_ALL = "User-agent: *\nDisallow: /\n"


class Limiter:
    def wait(self, url):
        pass


def fetcher(robots: dict, renderer=None):
    """A Fetcher whose robots.txt per host comes from `robots` (missing host: 404, so allowed)."""
    def handle(request):
        if request.url.path == "/robots.txt" and request.url.host in robots:
            return httpx.Response(200, text=robots[request.url.host])
        return httpx.Response(404)
    client = httpx.Client(transport=httpx.MockTransport(handle), follow_redirects=True)
    return lfetch.Fetcher(renderer=renderer, client=client, limiter=Limiter())


class FakeRenderer:
    def __init__(self, html="<html></html>"):
        self.html_calls, self.visits, self._html = [], [], html

    def html(self, url, wait=6, stealth=False, **_):
        self.html_calls.append(url)
        return self._html

    @contextmanager
    def browser(self):
        r = self

        class Page:
            def set_default_timeout(self, ms): pass
            def goto(self, url, **k): r.visits.append(url)
            def wait_for_load_state(self, *a, **k): pass
            def wait_for_timeout(self, ms): pass
            def get_by_role(self, *a, **k): raise capture.PwError("no banner")
            def evaluate(self, js): pass
            def screenshot(self, path): open(path, "wb").write(b"png")

        class Ctx:
            def new_page(self): return Page()
            def close(self): pass

        class Browser:
            def new_context(self, **k): return Ctx()
        yield Browser()


def test_render_page_obeys_robots(monkeypatch):
    rend = FakeRenderer()
    f = fetcher({"www.cosmos.so": DISALLOW_ALL}, rend)
    monkeypatch.setattr(lfetch, "Fetcher", lambda *a, **k: f)
    notes = []
    assert scout._parse(scout.render_page, "https://www.cosmos.so/search/elements/x", scout.parse_cosmos, notes) == []
    assert rend.html_calls == [] and len(notes) == 1 and "robots.txt" in notes[0]


def test_render_page_refuses_banned_hosts(monkeypatch):
    rend = FakeRenderer()
    f = fetcher({}, rend)
    monkeypatch.setattr(lfetch, "Fetcher", lambda *a, **k: f)
    notes = []
    scout._parse(scout.render_page, "https://www.are.na/search/x", scout.parse_cosmos, notes)
    assert rend.html_calls == [] and "banned" in notes[0]


def test_render_page_renders_when_allowed(monkeypatch):
    rend = FakeRenderer("<html>ok</html>")
    f = fetcher({}, rend)
    monkeypatch.setattr(lfetch, "Fetcher", lambda *a, **k: f)
    assert scout.render_page("https://www.cosmos.so/search/elements/x", settle_ms=1000) == "<html>ok</html>"
    assert rend.html_calls == ["https://www.cosmos.so/search/elements/x"]


def test_capture_skips_sites_whose_robots_disallow(tmp_path):
    rend = FakeRenderer()
    f = fetcher({"no.example": DISALLOW_ALL}, rend)
    sites = [{"url": "https://no.example/", "note": "No", "title": "No"},
             {"url": "https://yes.example/", "note": "Yes", "title": "Yes"}]
    cands, failures = capture.capture_sites(sites, tmp_path / "raw", fetcher=f, renderer=rend)
    assert rend.visits == ["https://yes.example/"]
    assert [c.source_url for c in cands] == ["https://yes.example/"] * 2
    assert len(failures) == 1 and failures[0].startswith("skipped No:") and "robots.txt" in failures[0]


def test_capture_launches_no_browser_when_every_site_is_refused(tmp_path):
    class NoBrowser(FakeRenderer):
        def browser(self):
            raise AssertionError("browser launched")
    f = fetcher({"no.example": DISALLOW_ALL})
    cands, failures = capture.capture_sites([{"url": "https://no.example/a", "note": "No"}], tmp_path / "raw",
                                            fetcher=f, renderer=NoBrowser())
    assert cands == [] and len(failures) == 1
