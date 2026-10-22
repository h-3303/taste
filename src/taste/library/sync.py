import itertools
import re
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import db, thumbs
from .fetch import Blocked, FetchError
from .paths import SAMPLE_COLLECTIONS, SAMPLE_ITEMS
from .sources import base

_SVG_COMMENT = re.compile(r"^\s*(?:<!--.*?-->\s*)*", re.S)
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif")


@dataclass
class SyncOptions:
    sample: bool = True
    max_collections: int | None = None
    max_items: int | None = None
    snapshot: bool = False
    workers: int = 8
    screenshots: bool = False

    def caps(self) -> tuple[int | None, int | None]:
        if self.sample:
            return (self.max_collections or SAMPLE_COLLECTIONS, self.max_items or SAMPLE_ITEMS)
        return (self.max_collections, self.max_items)


@dataclass
class SyncReport:
    sources: dict = field(default_factory=dict)

    def summary(self) -> str:
        lines = []
        for slug, r in self.sources.items():
            state = "BLOCKED" if r["blocked"] else f"{len(r['failures'])} failures"
            lines.append(f"{slug}: {r['collections']} collections, {r['new']} new, {r['seen']} seen, "
                         f"{r['thumbs']} thumbs, {r['no_thumb']} no-thumb, {state}")
        return "\n".join(lines)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_image_url(url: str | None) -> bool:
    return bool(url) and url.split("?")[0].lower().endswith(IMAGE_EXT)


def make_item_thumb(item: dict, fetch, thumbs_dir: Path, adapter=None, opts: SyncOptions | None = None):
    """Return (thumb relative path, phash), (None, None) when there is nothing to render, or raise FetchError/OSError."""
    thumbs_dir = Path(thumbs_dir)
    dest = thumbs_dir / f"{item['id']}.jpg"
    meta = item.get("meta") or {}
    kind = item["kind"]
    if kind == "palette" and meta.get("colors"):
        thumbs.swatch(meta["colors"], dest)
        return f"thumbs/{dest.name}", None
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        code = _SVG_COMMENT.sub("", meta.get("code", ""))   # Tabler prefixes a metadata comment
        if kind == "icon" and code.startswith("<svg"):
            png = thumbs.svg_to_png(code, tmp / "icon.png")
            if png is None:
                return None, None   # placeholder: no rasteriser. Stay thumb-NULL so a later sync/ensure_thumbs retries once cairosvg exists
            _, h = thumbs.make_thumb(png, dest)
            return f"thumbs/{dest.name}", h
        if kind == "font" and adapter is not None and base.has_font_file(adapter):
            font_path = adapter.font_file(item, fetch, tmp)
            thumbs.specimen(font_path, item["title"], dest)
            return f"thumbs/{dest.name}", None
        url = item.get("thumb_url") or meta.get("thumb_url")
        if not url and _is_image_url(item.get("asset_url")) and kind in ("image", "texture", "site", "icon"):
            url = item["asset_url"]
        if url:
            raw = fetch.download(url, tmp / ("src" + Path(url.split("?")[0]).suffix[:5]))
            _, h = thumbs.make_thumb(raw, dest)
            return f"thumbs/{dest.name}", h
        if kind == "site" and opts is not None and opts.screenshots and item.get("page_url"):
            shot = fetch.screenshot(item["page_url"], tmp / "shot.png")
            _, h = thumbs.make_thumb(shot, dest)
            return f"thumbs/{dest.name}", h
    return None, None   # nothing to render from: not a failure


def _thumb_many(conn, rows: list[dict], fetch, thumbs_dir, adapter, opts, report: dict, log) -> None:
    stop = threading.Event()   # set by the first worker to be Blocked: the rest of the batch is skipped, not failed

    def one(item):
        if stop.is_set():
            return item["id"], (None, None), None, None
        try:
            return item["id"], make_item_thumb(item, fetch, thumbs_dir, adapter, opts), None, None
        except Blocked as e:
            stop.set()
            return item["id"], None, None, e
        except Exception as e:  # one bad item must not abort the source
            return item["id"], None, f"thumb {item['id']} ({item['title'][:40]}): {e}", None
    blocked = None
    with ThreadPoolExecutor(max_workers=max(1, opts.workers)) as pool:
        for iid, result, err, block in pool.map(one, rows):
            if block is not None:
                blocked = blocked or block
            elif err:
                report["failures"].append(err)
                log(f"  ! {err}")
            elif result[0] is None:
                report["no_thumb"] += 1
            else:
                db.set_thumb(conn, iid, result[0], result[1])
                report["thumbs"] += 1
    if blocked is not None:
        raise blocked


def sync(conn, adapters: list, fetch, thumbs_dir: Path, opts: SyncOptions, log=print, now: str | None = None,
         explicit: bool = False) -> SyncReport:
    now = now or _now()
    max_coll, max_items = opts.caps()
    report = SyncReport()
    for adapter in adapters:
        info = adapter.info
        r = report.sources[info.slug] = {"collections": 0, "new": 0, "seen": 0, "thumbs": 0, "no_thumb": 0, "failures": [], "blocked": False}
        db.upsert_source(conn, info)
        if info.tier >= 3 and not opts.snapshot:
            r["failures"].append("tier 3 source skipped: pass --snapshot to catalogue it once")
            continue
        if info.policy == "manual" and not explicit:
            r["failures"].append(f"manual source: run `taste sync {info.slug}` to include it")
            continue
        log(f"{info.slug}: syncing" + (" (sample)" if opts.sample else ""))
        if hasattr(adapter, "max_items"):
            adapter.max_items = max_items
        error = None
        try:
            gen = adapter.collections(fetch)
            for coll, items in itertools.islice(gen, max_coll) if max_coll else gen:
                cid = db.upsert_collection(conn, info.slug, coll)
                r["collections"] += 1
                pending = []
                kept = items[:max_items] if max_items else items
                for d in kept:
                    if d.thumb_url:
                        d.meta = {**d.meta, "thumb_url": d.thumb_url}
                    iid, created = db.upsert_item(conn, info.slug, d, cid, now)
                    r["new" if created else "seen"] += 1
                    row = db.get_item(conn, iid)
                    if not row["thumb"]:
                        row["thumb_url"] = d.thumb_url
                        pending.append(row)
                db.finish_collection(conn, cid, now, coll.error)
                log(f"  {coll.slug}: {len(kept)} items")
                if pending:
                    _thumb_many(conn, pending, fetch, thumbs_dir, adapter, opts, r, log)
        except Blocked as e:
            r["blocked"], error = True, str(e)
            r["failures"].append(str(e))
            log(f"  ! blocked: {e}")
        except (FetchError, OSError, ValueError, KeyError) as e:
            error = str(e)
            r["failures"].append(str(e))
            log(f"  ! {e}")
        db.set_source_error(conn, info.slug, error, now)
    return report


def ensure_thumbs(conn, fetch, thumbs_dir: Path, kind=None, source=None, limit=None, log=print) -> int:
    rows = db.items_without_thumb(conn, kind, source)
    if limit:
        rows = rows[:limit]
    done = 0
    for item in rows:
        adapter = base.REGISTRY.get(item["source"])
        item["thumb_url"] = (item.get("meta") or {}).get("thumb_url")
        try:
            rel, h = make_item_thumb(item, fetch, thumbs_dir, adapter, SyncOptions())
        except Blocked as e:
            log(f"  ! blocked: {e}")
            return done
        except Exception as e:  # one bad item must not stop the run
            log(f"  ! thumb {item['id']}: {e}")
            continue
        if rel is None:
            continue
        db.set_thumb(conn, item["id"], rel, h)
        done += 1
    return done
