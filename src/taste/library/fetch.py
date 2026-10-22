import json as _json
import re
import urllib.robotparser
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .. import render as _render
from .paths import BANNED_HOSTS

UA = "taste/0.1 (+https://github.com/h-3303/taste; polite, obeys robots.txt)"
CHALLENGE_TITLES = ("Just a moment", "Attention Required! | Cloudflare", "Access Denied", "Vercel Security Checkpoint")
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)


def is_challenge(html: str) -> bool:
    """Bot-challenge page: judged by <title> and fixed markers, not by words anywhere in the body."""
    head = html[:20000]
    m = _TITLE.search(head)
    if m and any(t in m.group(1) for t in CHALLENGE_TITLES):
        return True
    # Cloudflare's passive detection script (scripts/jsd/) is injected into ordinary pages; only the interactive paths mean a challenge.
    return "<body>Forbidden</body>" in head or "/cdn-cgi/challenge-platform/" in head.replace("/cdn-cgi/challenge-platform/scripts/jsd/", "")


class FetchError(Exception):
    def __init__(self, message: str = "", status: int | None = None):
        super().__init__(message)
        self.status = status   # HTTP status when the failure was an error response


class Blocked(FetchError):
    """429, a 403 on a page, or a bot challenge: the source stops for this run."""


def host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def banned(url: str) -> bool:
    h = host(url)
    return any(h == b or h.endswith("." + b) for b in BANNED_HOSTS)


class RateLimiter:
    def __init__(self, default: float = 1.0, per_host: dict | None = None, sleep=time.sleep, clock=time.monotonic):
        self.default, self.per_host = default, per_host or {"siteinspire.com": 3.0}
        self.sleep, self.clock, self.last = sleep, clock, {}
        self._lock = threading.Lock()

    def _interval(self, h: str) -> float:
        # exact host or its www. form only: a CDN subdomain (r2.siteinspire.com) does not inherit the page host's rule
        for k, v in self.per_host.items():
            if h == k or h == "www." + k:
                return v
        return self.default

    def wait(self, url: str) -> None:
        h = host(url)
        key = h[4:] if h.startswith("www.") else h
        with self._lock:   # claim the next slot under the lock, sleep outside it so other hosts are not held up
            now = self.clock()
            slot = max(now, self.last.get(key, -1e9) + self._interval(h))
            self.last[key] = slot
        if slot > now:
            self.sleep(slot - now)


class Fetcher:
    def __init__(self, renderer=None, limiter: RateLimiter | None = None, client: httpx.Client | None = None):
        self._renderer = renderer   # resolved on first render/screenshot, so plain HTTP never touches Playwright or config
        self.limiter = limiter or RateLimiter()
        self.client = client or httpx.Client(timeout=30.0, follow_redirects=True, headers={"User-Agent": UA})
        self.client.event_hooks["request"] = [*self.client.event_hooks.get("request", []), self._on_request]
        self._origin = threading.local()
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._robots_lock = threading.Lock()

    @staticmethod
    def _site(url: str) -> str:
        h = host(url)
        return h[4:] if h.startswith("www.") else h

    def _check(self, url: str) -> None:
        if banned(url):
            raise FetchError(f"banned host: {url}")
        self._origin.site = self._site(url)
        self.limiter.wait(url)

    def _on_request(self, request: httpx.Request) -> None:
        """Every request the client sends, redirect hops included: refuse banned hosts, pace new hosts."""
        url = str(request.url)
        if banned(url):
            raise FetchError(f"banned host (redirect): {url}")
        if self._site(url) != getattr(self._origin, "site", None):
            self.limiter.wait(url)

    def _get(self, url: str, params=None, headers=None, page=False) -> httpx.Response:
        self._check(url)
        try:
            r = self.client.get(url, params=params, headers=headers)
        except httpx.HTTPError as e:
            raise FetchError(f"{url}: {e}") from e
        if r.status_code == 429 or (page and r.status_code == 403):
            raise Blocked(f"{url}: HTTP {r.status_code}")
        if r.status_code >= 400:
            raise FetchError(f"{url}: HTTP {r.status_code}")
        if page and is_challenge(r.text):
            raise Blocked(f"{url}: bot challenge")
        return r

    def get_json(self, url: str, params=None, headers=None):
        r = self._get(url, params, headers)
        text = r.text
        if text.startswith(")]}'"):          # Google's JSON hijack prefix
            text = text[4:]
        try:
            return _json.loads(text)
        except ValueError as e:
            raise FetchError(f"{url}: not JSON ({e})") from e

    def get_text(self, url: str, headers=None) -> str:
        return self._get(url, headers=headers, page=True).text

    def download(self, url: str, dest: Path, headers=None) -> Path:
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        self._check(url)
        tmp = dest.with_suffix(dest.suffix + ".part")
        try:
            with self.client.stream("GET", url, headers=headers) as r:
                if r.status_code == 429:
                    raise Blocked(f"{url}: HTTP 429")
                if r.status_code >= 400:
                    raise FetchError(f"{url}: HTTP {r.status_code}", status=r.status_code)
                with open(tmp, "wb") as f:
                    for chunk in r.iter_bytes():
                        f.write(chunk)
        except httpx.HTTPError as e:
            tmp.unlink(missing_ok=True)
            raise FetchError(f"{url}: {e}") from e
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
        tmp.replace(dest)
        return dest

    def _robots_ok(self, url: str) -> bool:
        """robots.txt for the URL's origin, fetched once per host through the same client; missing or unreadable means allow."""
        parts = urlparse(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        with self._robots_lock:
            if origin not in self._robots:
                rp = None
                robots_url = origin + "/robots.txt"
                try:
                    self._check(robots_url)
                    r = self.client.get(robots_url)
                    if r.status_code == 200:
                        rp = urllib.robotparser.RobotFileParser()
                        rp.parse(r.text.splitlines())
                except httpx.HTTPError:
                    pass
                self._robots[origin] = rp
            rp = self._robots[origin]
        return rp is None or rp.can_fetch(UA, url)

    def _check_render(self, url: str, obey_robots: bool) -> None:
        self._check(url)
        if obey_robots and not self._robots_ok(url):
            raise FetchError(f"robots.txt disallows {url}")

    @property
    def renderer(self):
        if self._renderer is None:
            self._renderer = _render.get_renderer()
        return self._renderer

    def render(self, url: str, wait: int = 6, stealth: bool = False, obey_robots: bool = True) -> str:
        self._check_render(url, obey_robots)
        kw = {} if obey_robots else {"obey_robots": False}   # only Obscura has a robots switch
        try:
            html = self.renderer.html(url, wait=wait, stealth=stealth, **kw)
        except _render.RenderError as e:
            raise FetchError(str(e)) from e
        if is_challenge(html):
            raise Blocked(f"{url}: bot challenge")
        return html

    def screenshot(self, url: str, dest: Path, wait: int = 6, obey_robots: bool = True) -> Path:
        self._check_render(url, obey_robots)
        try:
            return self.renderer.screenshot(url, Path(dest), wait=wait)
        except _render.RenderError as e:
            raise FetchError(str(e)) from e

    def close(self) -> None:
        self.client.close()


class FakeFetcher:
    """Test double: dicts keyed by URL substring."""

    def __init__(self, json=None, text=None, pages=None, files=None):
        self.json, self.text, self.pages, self.files = json or {}, text or {}, pages or {}, files or {}
        self.calls: list[tuple[str, str]] = []

    def _find(self, table: dict, url: str, what: str):
        for k, v in table.items():
            if k in url:
                return v
        raise FetchError(f"fake: no {what} for {url}")

    def get_json(self, url, params=None, headers=None):
        self.calls.append(("get_json", url))
        if params:
            url = url + "?" + "&".join(f"{k}={v}" for k, v in params.items())
        return self._find(self.json, url, "json")

    def get_text(self, url, headers=None) -> str:
        self.calls.append(("get_text", url))
        return self._find(self.text, url, "text")

    def render(self, url, wait=6, stealth=False, obey_robots=True) -> str:
        self.calls.append(("render", url))
        return self._find(self.pages, url, "page")

    def screenshot(self, url, dest, wait=6) -> Path:
        self.calls.append(("screenshot", url))
        data = self._find(self.files, url, "screenshot")
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(data)
        return Path(dest)

    def download(self, url, dest, headers=None) -> Path:
        self.calls.append(("download", url))
        data = self._find(self.files, url, "file")
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(data)
        return Path(dest)

    def close(self) -> None:
        pass
