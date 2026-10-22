import time
from pathlib import Path

import httpx

UA = "moodboards/0.1 (personal moodboard research tool)"


class Http:
    def __init__(self, timeout: float = 30.0):
        self.client = httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": UA})

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
