import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from . import db, paths, thumbs
from .models import CollectionDraft, ItemDraft, SourceInfo
from .sources import base

SOURCE = SourceInfo("curated", "Curated keepers", "", 1, policy="manual", notes="taste add / taste keep")
KIND_BY_EXT = {".svg": "icon", ".ttf": "font", ".otf": "font", ".woff": "font", ".woff2": "font", ".css": "snippet", ".js": "snippet",
               ".jsx": "snippet", ".tsx": "snippet", ".ts": "snippet", ".glsl": "snippet", ".html": "snippet",
               ".jpg": "image", ".jpeg": "image", ".png": "image", ".webp": "image", ".gif": "image"}
TEXT_KINDS = ("snippet", "icon")


class CuratedAdapter:
    info = SOURCE

    def collections(self, fetch):
        yield from ()


base.register(CuratedAdapter())


def _slug(slug: str) -> str:
    return slug if slug.startswith("curated/") else f"curated/{slug}"


def new_collection(conn, slug: str, kind: str, title: str | None = None, languages: list[str] | None = None) -> str:
    db.upsert_source(conn, SOURCE)
    slug = _slug(slug)
    existing = db.get_collection(conn, slug)
    langs = list(dict.fromkeys([*(existing["languages"] if existing else []), *(languages or [])]))
    return db.upsert_collection(conn, "curated", CollectionDraft(slug, kind, title or (existing["title"] if existing else slug.split("/", 1)[1]),
                                                                 languages=langs, policy="manual"))


def add(conn, collection_slug: str, src: str, fetch, thumbs_dir: Path, title: str = "", tags: list[str] | None = None,
        page_url: str = "", language: str | None = None, now: str | None = None) -> str:
    coll = db.get_collection(conn, _slug(collection_slug))
    if not coll:
        raise KeyError(f"no collection {collection_slug}; create it with: taste lib collection new {collection_slug.split('/')[-1]} --kind <kind>")
    now = now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    is_url = src.startswith(("http://", "https://"))
    ext = Path(urlparse(src).path if is_url else src).suffix.lower()
    kind = KIND_BY_EXT.get(ext, "image")
    key = f"curated:{hashlib.sha1(src.encode()).hexdigest()[:16]}"
    store = paths.cache_dir() / "curated"
    store.mkdir(parents=True, exist_ok=True)
    k = key.split(":")[1]
    tmp = store / f"incoming-{k}{ext}"
    tthumb = store / f"incoming-{k}-thumb.jpg"
    tpng = store / f"incoming-{k}-svg.png"
    try:
        if is_url:
            fetch.download(src, tmp)
        else:
            shutil.copyfile(src, tmp)
        meta = {"added_by": "dlib add", "origin": src}
        if kind in TEXT_KINDS:
            meta["code"] = tmp.read_text(errors="replace")[:8192]
            meta["language"] = ext.lstrip(".")
        name = title or Path(urlparse(src).path if is_url else src).stem
        # render the thumbnail first: a bad file must leave no row, stored file or thumb behind
        try:
            h = None
            if kind == "image":
                _, h = thumbs.make_thumb(tmp, tthumb)
            elif kind == "icon":
                png = thumbs.svg_to_png(meta["code"], tpng)
                if png:
                    _, h = thumbs.make_thumb(png, tthumb)
                # else: no SVG rasteriser installed; leave the thumb NULL so ensure_thumbs retries it later
            elif kind == "font":
                thumbs.specimen(tmp, name, tthumb)
        except (OSError, ValueError):
            raise
        except Exception as e:
            raise ValueError(f"cannot thumbnail {src}: {e}") from e
        draft = ItemDraft(key=key, kind=kind, title=name, page_url=page_url or (src if is_url else ""),
                          asset_url=src if is_url else "", tags=tags or [], meta=meta, license="curated: see origin")
        iid, _ = db.upsert_item(conn, "curated", draft, coll["id"], now)
        final = store / f"{iid}{ext}"
        tmp.replace(final)
        if not is_url:
            conn.execute("UPDATE items SET asset_url = ? WHERE id = ?", (str(final), iid))
            conn.commit()
        if tthumb.exists():
            dest = Path(thumbs_dir) / f"{iid}.jpg"
            dest.parent.mkdir(parents=True, exist_ok=True)
            tthumb.replace(dest)
            db.set_thumb(conn, iid, f"thumbs/{iid}.jpg", h)
    finally:
        for t in (tmp, tthumb, tpng):
            t.unlink(missing_ok=True)
    db.finish_collection(conn, coll["id"], now)
    if language:
        new_collection(conn, coll["slug"], coll["kind"], languages=[language])
    return iid
