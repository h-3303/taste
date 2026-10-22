"""Lazy thumbnails for seed "link" rows: fetch on first use, mark gone images dead."""
import json
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image, UnidentifiedImageError

from .library import db, sync
from .library.fetch import Blocked, FetchError, is_challenge

_GONE = (404, 410)


class _Sniffing:
    """Wraps a fetcher: a downloaded body that is a bot-challenge page raises Blocked (a 200 can carry one)."""

    def __init__(self, fetch):
        self._fetch = fetch

    def __getattr__(self, name):
        return getattr(self._fetch, name)

    def download(self, url, dest, headers=None):
        path = self._fetch.download(url, dest, headers)
        with open(path, "rb") as f:
            head = f.read(4096)
        if is_challenge(head.decode("utf-8", "replace")):
            raise Blocked(f"{url}: bot challenge")
        return path


def _host(item: dict) -> str:
    url = item.get("thumb_url") or (item.get("meta") or {}).get("thumb_url") or item.get("asset_url") or ""
    return (urlparse(url).hostname or "").lower()


def _mark_dead(conn, item: dict) -> None:
    meta = {**(item.get("meta") or {}), "dead": True}
    conn.execute("UPDATE items SET meta = ? WHERE id = ?", (json.dumps(meta, ensure_ascii=False), item["id"]))
    conn.commit()


def ensure_item_thumbs(conn, ids: list[str], fetch, thumbs_dir: Path) -> dict[str, Path | None]:
    """Thumbnail the given items that have none. Returns id -> thumb path, or None when there is none (yet).

    Dead (HTTP 404/410, or a body that is not an image) sets meta.dead. Timeouts, 5xx, 429 and challenges leave the
    row alone; 429/challenge also skip the rest of that host for this call. No usable image URL is not dead."""
    thumbs_dir = Path(thumbs_dir)
    out: dict[str, Path | None] = {}
    fetch = _Sniffing(fetch)
    blocked: set[str] = set()
    for iid in ids:
        item = db.get_item(conn, iid)
        out[iid] = None
        if item is None:
            continue
        if item["thumb"]:
            out[iid] = thumbs_dir / Path(item["thumb"]).name
            continue
        if item["meta"].get("dead") or _host(item) in blocked:
            continue
        try:
            rel, h = sync.make_item_thumb(item, fetch, thumbs_dir)
        except Blocked:
            blocked.add(_host(item))
            continue
        except FetchError as e:
            if e.status in _GONE:
                _mark_dead(conn, item)
            continue
        except (UnidentifiedImageError, Image.DecompressionBombError):   # the body was not a usable image
            _mark_dead(conn, item)
            continue
        except OSError:   # local I/O trouble (disk, permissions): says nothing about the link
            continue
        if rel is None:
            continue
        db.set_thumb(conn, iid, rel, h)
        out[iid] = thumbs_dir / Path(rel).name
    return out
