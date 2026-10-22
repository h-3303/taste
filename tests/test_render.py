import subprocess
from pathlib import Path

import pytest

from taste import config, render
from taste.boards import scout
from taste.library import fetch


@pytest.fixture(autouse=True)
def home(monkeypatch, tmp_path):
    monkeypatch.setenv("TASTE_CONFIG", str(tmp_path / "cfg" / "config.json"))
    monkeypatch.setenv("TASTE_DATA", str(tmp_path / "data"))
    monkeypatch.setattr("shutil.which", lambda *_: None)


def fake_bin(tmp_path):
    b = tmp_path / "obscura"
    b.write_text("#!/bin/sh\n")
    b.chmod(0o755)
    return b


def test_default_is_playwright():
    assert isinstance(render.get_renderer(), render.PlaywrightRenderer)


def test_connector_selects_obscura(tmp_path):
    b = fake_bin(tmp_path)
    config.save({"connectors": {"obscura": {"enabled": True, "bin": str(b)}}})
    r = render.get_renderer()
    assert isinstance(r, render.ObscuraRenderer) and r.bin == str(b)


def test_missing_bin_falls_back_to_playwright(tmp_path):
    config.save({"connectors": {"obscura": {"enabled": True, "bin": str(tmp_path / "gone")}}})
    assert isinstance(render.get_renderer(), render.PlaywrightRenderer)


def test_renderer_missing_message():
    assert str(render.RendererMissing()) == (
        "Chromium is missing: run `playwright install chromium` "
        "(or `uv tool run --from taste playwright install chromium`)")


class Fake:
    name = "fake"

    def __init__(self):
        self.calls = []

    def html(self, url, wait=6, stealth=False):
        self.calls.append(url)
        return f"<html>{url}</html>"

    def screenshot(self, url, dest, wait=6):
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(b"png")
        return Path(dest)


def quick():
    return fetch.RateLimiter(sleep=lambda s: None)


def test_fetcher_banned_host_never_reaches_renderer():
    fake = Fake()
    f = fetch.Fetcher(renderer=fake, limiter=quick())
    with pytest.raises(fetch.FetchError, match="banned"):
        f.render("https://banned.are.na/x")
    assert fake.calls == []
    f.close()


def test_fetcher_render_delegates():
    fake = Fake()
    f = fetch.Fetcher(renderer=fake, limiter=quick())
    assert f.render("https://x.test/a") == "<html>https://x.test/a</html>"
    f.close()


def test_fetcher_render_detects_challenge():
    fake = Fake()
    fake.html = lambda url, wait=6, stealth=False: "<html><title>Just a moment...</title></html>"
    f = fetch.Fetcher(renderer=fake, limiter=quick())
    with pytest.raises(fetch.Blocked):
        f.render("https://x.test")
    f.close()


def test_fetcher_screenshot_delegates(tmp_path):
    f = fetch.Fetcher(renderer=Fake(), limiter=quick())
    dest = tmp_path / "sub" / "s.png"
    assert f.screenshot("https://x.test", dest) == dest and dest.read_bytes() == b"png"
    f.close()


def test_fetcher_resolves_renderer_lazily(monkeypatch):
    def boom():
        raise AssertionError("resolved too early")
    monkeypatch.setattr(render, "get_renderer", boom)
    f = fetch.Fetcher(limiter=quick())   # construction and plain http never resolve it
    f.close()


def test_fetcher_wraps_render_errors():
    fake = Fake()
    def bad(url, wait=6, stealth=False):
        raise render.RenderError("boom")
    fake.html = bad
    f = fetch.Fetcher(renderer=fake, limiter=quick())
    with pytest.raises(fetch.FetchError, match="boom"):
        f.render("https://x.test")
    f.close()


def test_scout_render_page_uses_get_renderer(monkeypatch):
    seen = {}
    class R(Fake):
        def html(self, url, wait=6, stealth=False):
            seen.update(url=url, wait=wait)
            return "<html>ok</html>"
    monkeypatch.setattr(render, "get_renderer", lambda: R())
    assert scout.render_page("https://cosmos.so/x", settle_ms=4000) == "<html>ok</html>"
    assert seen == {"url": "https://cosmos.so/x", "wait": 4}


def runner_for(stdout="<html>hi</html>", code=0, stderr="", seen=None, write=None):
    def run(argv, **kw):
        if seen is not None:
            seen["argv"] = argv
        if write:
            Path(argv[argv.index("-s") + 1]).write_bytes(b"png")
        return subprocess.CompletedProcess(argv, code, stdout=stdout, stderr=stderr)
    return run


def test_obscura_html_argv():
    seen = {}
    r = render.ObscuraRenderer("/bin/obscura", runner=runner_for(seen=seen))
    assert r.html("https://c.test/x", wait=8) == "<html>hi</html>"
    a = seen["argv"]
    assert a[:1] == ["/bin/obscura"] and "--obey-robots" in a and "--stealth" not in a
    assert a[a.index("fetch") + 1] == "https://c.test/x"
    assert a[a.index("--wait") + 1] == "8" and a[a.index("--dump") + 1] == "html" and "--quiet" in a
    r.html("https://c.test/x", stealth=True)
    assert "--stealth" in seen["argv"]


def test_obscura_html_failure():
    r = render.ObscuraRenderer("/bin/obscura", runner=runner_for(code=1, stdout="", stderr="boom"))
    with pytest.raises(render.RenderError, match="boom"):
        r.html("https://x.test")


def test_obscura_timeout():
    def run(argv, **kw):
        raise subprocess.TimeoutExpired(argv, 1)
    with pytest.raises(render.RenderError, match="timed out"):
        render.ObscuraRenderer("/bin/obscura", runner=run).html("https://x.test")


def test_obscura_screenshot(tmp_path):
    seen = {}
    r = render.ObscuraRenderer("/bin/obscura", runner=runner_for(stdout="", seen=seen, write=True))
    dest = tmp_path / "a" / "s.png"
    assert r.screenshot("https://x.test", dest) == dest and dest.read_bytes() == b"png"
    assert "--obey-robots" in seen["argv"]
    bad = render.ObscuraRenderer("/bin/obscura", runner=runner_for(stdout="", code=1, stderr="boom"))
    with pytest.raises(render.RenderError):
        bad.screenshot("https://x.test", tmp_path / "n.png")
    nofile = render.ObscuraRenderer("/bin/obscura", runner=runner_for(stdout=""))
    with pytest.raises(render.RenderError):
        nofile.screenshot("https://x.test", tmp_path / "m.png")


def test_renderer_missing_maps_to_exit_2(monkeypatch, capsys):
    from taste.boards import cli as bcli
    def boom(*a, **k):
        raise render.RendererMissing()
    monkeypatch.setattr(bcli, "cmd_sheet", boom)
    assert bcli.main(["sheet", "x"]) == 2
    assert "Chromium is missing" in capsys.readouterr().out
