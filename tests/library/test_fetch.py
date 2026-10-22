import subprocess
from pathlib import Path

import httpx
import pytest

from taste.library import fetch


def test_banned_hosts():
    assert fetch.banned("https://www.are.na/x") and fetch.banned("https://images.are.na/abc")
    assert fetch.banned("https://artvee.com/dl/") and not fetch.banned("https://www.cosmos.so/search")


def test_rate_limiter_waits_per_host():
    waits, t = [], [0.0]
    rl = fetch.RateLimiter(default=1.0, per_host={"siteinspire.com": 3.0}, sleep=waits.append, clock=lambda: t[0])
    rl.wait("https://a.com/1"); rl.wait("https://a.com/2"); rl.wait("https://www.siteinspire.com/w")
    t[0] = 1.0
    rl.wait("https://siteinspire.com/w2")
    assert waits == [1.0, 2.0]          # a.com/2 waits the default 1 s; siteinspire's second call at t=1 waits 2 s more


def test_get_json_and_download(tmp_path):
    def handler(req):
        if req.url.path == "/j":
            return httpx.Response(200, json={"ok": True})
        if req.url.path == "/img":
            return httpx.Response(200, content=b"\x89PNGdata", headers={"content-type": "image/png"})
        return httpx.Response(404)
    f = fetch.Fetcher(client=httpx.Client(transport=httpx.MockTransport(handler)),
                      limiter=fetch.RateLimiter(sleep=lambda s: None))
    assert f.get_json("https://x.test/j") == {"ok": True}
    p = f.download("https://x.test/img", tmp_path / "a.png")
    assert p.read_bytes() == b"\x89PNGdata"
    with pytest.raises(fetch.FetchError):
        f.download("https://x.test/missing", tmp_path / "b.png")
    assert not (tmp_path / "b.png").exists()
    f.close()


def test_http_429_is_blocked():
    f = fetch.Fetcher(client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(429))),
                      limiter=fetch.RateLimiter(sleep=lambda s: None))
    with pytest.raises(fetch.Blocked):
        f.get_text("https://x.test/p")
    f.close()


def test_banned_url_refused(tmp_path):
    f = fetch.Fetcher(client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200))),
                      limiter=fetch.RateLimiter(sleep=lambda s: None))
    with pytest.raises(fetch.FetchError):
        f.get_text("https://www.are.na/search/x")
    f.close()


def test_render_builds_obscura_argv_and_returns_html():
    seen = {}
    def runner(argv, **kw):
        seen["argv"] = argv
        return subprocess.CompletedProcess(argv, 0, stdout="<html><body>hi</body></html>", stderr="")
    f = fetch.Fetcher(obscura="/bin/obscura", runner=runner, limiter=fetch.RateLimiter(sleep=lambda s: None))
    html = f.render("https://www.cosmos.so/search/elements/x", wait=8)
    assert html.startswith("<html>")
    a = seen["argv"]
    assert a[:1] == ["/bin/obscura"] and "--obey-robots" in a and "--stealth" not in a
    assert a[a.index("fetch") + 1] == "https://www.cosmos.so/search/elements/x"
    assert a[a.index("--wait") + 1] == "8" and a[a.index("--dump") + 1] == "html" and "--quiet" in a
    f.render("https://codepen.io/x", stealth=True, obey_robots=False)
    assert "--stealth" in seen["argv"] and "--obey-robots" not in seen["argv"]
    f.close()


def test_render_detects_challenge():
    def runner(argv, **kw):
        return subprocess.CompletedProcess(argv, 0, stdout="<html><title>Just a moment...</title></html>", stderr="")
    f = fetch.Fetcher(obscura="/bin/obscura", runner=runner, limiter=fetch.RateLimiter(sleep=lambda s: None))
    with pytest.raises(fetch.Blocked):
        f.render("https://codepen.io/search")
    f.close()


def test_render_without_obscura_raises():
    f = fetch.Fetcher(obscura=None, limiter=fetch.RateLimiter(sleep=lambda s: None))
    with pytest.raises(fetch.FetchError, match="obscura"):
        f.render("https://x.test")
    f.close()


def test_render_nonzero_exit_raises():
    def runner(argv, **kw):
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="boom")
    f = fetch.Fetcher(obscura="/bin/obscura", runner=runner, limiter=fetch.RateLimiter(sleep=lambda s: None))
    with pytest.raises(fetch.FetchError, match="boom"):
        f.render("https://x.test")
    f.close()


def test_fake_fetcher_records_calls(tmp_path):
    f = fetch.FakeFetcher(json={"/assets": {"a": 1}}, pages={"cosmos.so": "<html/>"}, files={"cdn/x.png": b"img"})
    assert f.get_json("https://api/assets") == {"a": 1}
    assert f.render("https://www.cosmos.so/search") == "<html/>"
    assert f.download("https://cdn/x.png", tmp_path / "x.png").read_bytes() == b"img"
    with pytest.raises(fetch.FetchError):
        f.get_text("https://nowhere")
    assert f.calls[0] == ("get_json", "https://api/assets")


def _fetcher(handler):
    return fetch.Fetcher(client=httpx.Client(transport=httpx.MockTransport(handler)),
                         limiter=fetch.RateLimiter(sleep=lambda s: None))


class _Boom(httpx.SyncByteStream):
    def __iter__(self):
        yield b"partial"
        raise httpx.ReadError("connection dropped")


def test_download_midstream_failure_leaves_no_files(tmp_path):
    f = _fetcher(lambda r: httpx.Response(200, stream=_Boom()))
    with pytest.raises(fetch.FetchError):
        f.download("https://x.test/img", tmp_path / "a.png")
    assert list(tmp_path.iterdir()) == []
    f.close()


def test_download_429_is_blocked_and_leaves_no_files(tmp_path):
    f = _fetcher(lambda r: httpx.Response(429))
    with pytest.raises(fetch.Blocked):
        f.download("https://x.test/img", tmp_path / "a.png")
    assert list(tmp_path.iterdir()) == []
    f.close()


def test_get_json_strips_hijack_prefix():
    f = _fetcher(lambda r: httpx.Response(200, text=")]}'\n{\"a\": 1}"))
    assert f.get_json("https://x.test/j") == {"a": 1}
    f.close()


def test_403_blocks_pages_but_not_json():
    f = _fetcher(lambda r: httpx.Response(403))
    with pytest.raises(fetch.Blocked):
        f.get_text("https://x.test/p")
    with pytest.raises(fetch.FetchError) as ei:
        f.get_json("https://x.test/j")
    assert not isinstance(ei.value, fetch.Blocked)
    f.close()


def test_get_text_challenge_page_is_blocked():
    f = _fetcher(lambda r: httpx.Response(200, text="<html><title>Just a moment...</title></html>"))
    with pytest.raises(fetch.Blocked):
        f.get_text("https://x.test/p")
    f.close()


def test_is_challenge_uses_title_not_body_text():
    assert not fetch.is_challenge("<html><title>Poster</title><body>Access Denied is our band</body></html>")
    assert fetch.is_challenge("<html><title>Just a moment...</title></html>")
    assert fetch.is_challenge("<title>Access Denied</title>")
    assert fetch.is_challenge("<title>Attention Required! | Cloudflare</title>")
    assert fetch.is_challenge("<html><body>Forbidden</body></html>")
    assert fetch.is_challenge("<script src='/cdn-cgi/challenge-platform/x.js'></script>")
    assert not fetch.is_challenge("<html><body>cf-chl- is just a class</body></html>")


def test_render_does_not_block_page_mentioning_access_denied():
    def runner(argv, **kw):
        return subprocess.CompletedProcess(argv, 0, stdout="<html><title>Nice</title><body>Access Denied</body></html>", stderr="")
    f = fetch.Fetcher(obscura="/bin/obscura", runner=runner, limiter=fetch.RateLimiter(sleep=lambda s: None))
    assert "Access Denied" in f.render("https://codepen.io/x")
    f.close()


def test_rate_limiter_folds_www():
    waits = []
    rl = fetch.RateLimiter(sleep=waits.append, clock=lambda: 0.0)
    rl.wait("https://www.a.com/1"); rl.wait("https://a.com/2")
    assert waits == [1.0]


def test_screenshot_argv_and_failures(tmp_path):
    seen = {}
    def ok(argv, **kw):
        seen["argv"] = argv
        Path(argv[argv.index("-s") + 1]).write_bytes(b"png")
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
    f = fetch.Fetcher(obscura="/bin/obscura", runner=ok, limiter=fetch.RateLimiter(sleep=lambda s: None))
    dest = tmp_path / "sub" / "s.png"
    assert f.screenshot("https://x.test", dest) == dest and dest.read_bytes() == b"png"
    assert "--obey-robots" in seen["argv"] and "--stealth" not in seen["argv"]
    f.screenshot("https://x.test", dest, stealth=True)
    assert "--stealth" in seen["argv"]
    bad = fetch.Fetcher(obscura="/bin/obscura", limiter=fetch.RateLimiter(sleep=lambda s: None),
                        runner=lambda argv, **kw: subprocess.CompletedProcess(argv, 1, stdout="", stderr="boom"))
    with pytest.raises(fetch.FetchError):
        bad.screenshot("https://x.test", tmp_path / "n.png")
    nofile = fetch.Fetcher(obscura="/bin/obscura", limiter=fetch.RateLimiter(sleep=lambda s: None),
                           runner=lambda argv, **kw: subprocess.CompletedProcess(argv, 0, stdout="", stderr=""))
    with pytest.raises(fetch.FetchError):
        nofile.screenshot("https://x.test", tmp_path / "m.png")
    for x in (f, bad, nofile):
        x.close()


def test_vercel_checkpoint_is_a_challenge():
    from taste.library.fetch import is_challenge
    assert is_challenge("<html><head><title>Vercel Security Checkpoint</title></head><body></body></html>")


def test_cloudflare_passive_jsd_script_is_not_a_challenge():
    # Cloudflare injects its passive bot-detection script into ordinary pages (seen on cari.institute)
    page = "<html><head><title>CARI | Aesthetic | Diner Kitsch</title></head><body><script>a.src='/cdn-cgi/challenge-platform/scripts/jsd/main.js'</script></body></html>"
    assert not fetch.is_challenge(page)
    assert fetch.is_challenge("<script src='/cdn-cgi/challenge-platform/h/b/orchestrate/chl_page/v1'></script>")


def test_rate_limiter_is_thread_safe_on_one_host():
    import threading, time
    rl = fetch.RateLimiter(default=0.2)
    start = time.monotonic()
    ts = [threading.Thread(target=rl.wait, args=("https://one.test/x",)) for _ in range(8)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert time.monotonic() - start >= 1.35      # 8 callers → 7 intervals of 0.2 s


def test_siteinspire_slow_rule_does_not_cover_its_cdn():
    rl = fetch.RateLimiter(default=1.0)
    assert rl._interval("siteinspire.com") == 3.0
    assert rl._interval("r2.siteinspire.com") == 1.0


def test_redirect_to_banned_host_is_refused():
    seen = []
    def handler(req):
        seen.append(str(req.url))
        if req.url.host == "ok.test":
            return httpx.Response(302, headers={"location": "https://www.are.na/y"})
        return httpx.Response(200, text="should never be fetched")
    f = fetch.Fetcher(client=httpx.Client(follow_redirects=True, transport=httpx.MockTransport(handler)),
                      limiter=fetch.RateLimiter(sleep=lambda s: None))
    with pytest.raises(fetch.FetchError):
        f.get_text("https://ok.test/x")
    assert seen == ["https://ok.test/x"]
    f.close()


def test_redirect_to_other_host_waits_on_the_limiter():
    waited = []
    class RL(fetch.RateLimiter):
        def wait(self, url):
            waited.append(url)
    def handler(req):
        if req.url.host == "a.test":
            return httpx.Response(302, headers={"location": "https://b.test/y"})
        return httpx.Response(200, text="<html><title>hi</title></html>")
    f = fetch.Fetcher(client=httpx.Client(follow_redirects=True, transport=httpx.MockTransport(handler)), limiter=RL())
    assert "hi" in f.get_text("https://a.test/x")
    assert waited == ["https://a.test/x", "https://b.test/y"]
    f.close()
