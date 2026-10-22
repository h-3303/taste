import json as _json
import re
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .paths import BANNED_HOSTS, obscura_bin

UA = "dlib/0.1 (+h's personal design library; polite, obeys robots.txt)"
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
    pass


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
    def __init__(self, obscura: str | None = None, limiter: RateLimiter | None = None, runner=subprocess.run,
                 client: httpx.Client | None = None):
        self.obscura = obscura if obscura is not None else obscura_bin()
        self.limiter = limiter or RateLimiter()
        self.runner = runner
        self.client = client or httpx.Client(timeout=30.0, follow_redirects=True, headers={"User-Agent": UA})
        self.client.event_hooks["request"] = [*self.client.event_hooks.get("request", []), self._on_request]
        self._origin = threading.local()

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
                    raise FetchError(f"{url}: HTTP {r.status_code}")
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

    def _obscura(self, args: list[str], timeout: int) -> subprocess.CompletedProcess:
        if not self.obscura:
            raise FetchError("obscura not found: install it to ~/.local/bin or enable the obscura connector in config.json")
        try:
            return self.runner([self.obscura, *args], capture_output=True, text=True, timeout=timeout + 30)
        except subprocess.TimeoutExpired as e:
            raise FetchError(f"obscura timed out: {e}") from e

    def render(self, url: str, wait: int = 6, stealth: bool = False, obey_robots: bool = True, timeout: int = 40) -> str:
        self._check(url)
        flags = (["--stealth"] if stealth else []) + (["--obey-robots"] if obey_robots else [])
        p = self._obscura([*flags, "fetch", url, "--timeout", str(timeout), "--wait", str(wait), "--dump", "html",
                           "--quiet"], timeout)
        if p.returncode != 0:
            raise FetchError(f"obscura fetch {url}: {p.stderr.strip()[:300]}")
        html = p.stdout
        if is_challenge(html):
            raise Blocked(f"{url}: bot challenge")
        return html

    def screenshot(self, url: str, dest: Path, wait: int = 6, stealth: bool = False, timeout: int = 40) -> Path:
        self._check(url)
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        flags = (["--stealth"] if stealth else []) + ["--obey-robots"]
        p = self._obscura([*flags, "fetch", url, "--timeout", str(timeout), "--wait", str(wait), "-s", str(dest),
                           "--quiet"], timeout)
        if p.returncode != 0 or not dest.exists():
            raise FetchError(f"obscura screenshot {url}: {p.stderr.strip()[:300]}")
        return dest

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

    def render(self, url, wait=6, stealth=False, obey_robots=True, timeout=40) -> str:
        self.calls.append(("render", url))
        return self._find(self.pages, url, "page")

    def screenshot(self, url, dest, wait=6, stealth=False, timeout=40) -> Path:
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
