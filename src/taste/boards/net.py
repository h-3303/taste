import time
from pathlib import Path

import httpx

from taste.library.fetch import UA, FetchError, RateLimiter, banned


class Http:
    """Plain HTTP for the boards: the same banned-host rule as taste.library.fetch on every request,
    redirect hops included, and the same 1 req/s per host pacing."""

    def __init__(self, timeout: float = 30.0, transport=None, limiter=None):
        self.limiter = limiter or RateLimiter()
        self.client = httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": UA},
                                   transport=transport, event_hooks={"request": [self._on_request]})

    def _on_request(self, request: httpx.Request) -> None:
        url = str(request.url)
        if banned(url):
            raise FetchError(f"banned host: {url}")
        self.limiter.wait(url)

    def _retry(self, fn):
        try:
            return fn()
        except httpx.HTTPError:
            time.sleep(2)
            return fn()

    def get_json(self, url: str, params: dict | None = None) -> dict:
        def go():
            r = self.client.get(url, params=params)
            r.raise_for_status()
            return r.json()
        return self._retry(go)

    def download(self, url: str, dest: Path) -> Path:
        def go():
            r = self.client.get(url)
            r.raise_for_status()
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(r.content)
            return dest
        return self._retry(go)
