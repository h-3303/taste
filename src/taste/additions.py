"""`taste add`: put the person's own files, folders and links into the library as private `mine` items."""
import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from PIL import UnidentifiedImageError

from . import paths as taste_paths
from .library import db, fetch as _fetch, paths, thumbs
from .library.models import CollectionDraft, ItemDraft, SourceInfo

SOURCE = SourceInfo("mine", "Mine", "", 1, policy="manual", notes="taste add: private, never shipped")
COLLECTION = "mine/additions"
KIND_BY_EXT = {**dict.fromkeys((".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"), "image"),
               **dict.fromkeys((".ttf", ".otf", ".woff", ".woff2"), "font")}


def _is_url(s: str) -> bool:
    return s.startswith(("http://", "https://"))


def _ext(s: str) -> str:
    return Path(urlparse(s).path if _is_url(s) else s).suffix.lower()


def _one(conn, src: str, coll_id: str, kind, tags, language, fetch, now: str) -> str:
    is_url = _is_url(src)
    name = Path(urlparse(src).path if is_url else src).name or urlparse(src).netloc
    page = is_url and _ext(src) not in KIND_BY_EXT
    ext = ".png" if page else _ext(src)
    kind = kind or ("image" if page else KIND_BY_EXT.get(ext))
    if not kind:
        raise ValueError(f"can't tell what {name} is: pass --kind")
    store = taste_paths.library_dir() / "mine"
    store.mkdir(parents=True, exist_ok=True)
    key = f"mine:{hashlib.sha1(src.encode()).hexdigest()[:16]}"
    tmp = store / f"incoming-{key.split(':')[1]}{ext}"
    tthumb = store / f"incoming-{key.split(':')[1]}-thumb.jpg"
    try:
        if page:
            fetch.screenshot(src, tmp)
        elif is_url:
            fetch.download(src, tmp)
        else:
            shutil.copyfile(src, tmp)
        h = None
        try:
            if kind == "font":
                thumbs.specimen(tmp, Path(name).stem, tthumb)
            else:
                _, h = thumbs.make_thumb(tmp, tthumb)
        except (OSError, ValueError) as e:
            if isinstance(e, OSError) and not isinstance(e, UnidentifiedImageError):
                raise   # real filesystem errors propagate
            raise ValueError(f"cannot thumbnail {src}: {e}") from e
        except Exception as e:
            raise ValueError(f"cannot thumbnail {src}: {e}") from e
        meta = {"added_by": "taste add", "origin": src, "private": True}
        if language:
            meta["language"] = language
        draft = ItemDraft(key=key, kind=kind, title=Path(name).stem or name, page_url=src if is_url else "",
                          asset_url=src if is_url and not page else "", tags=list(tags), meta=meta, license="mine")
        iid, _ = db.upsert_item(conn, "mine", draft, coll_id, now)
        final = store / f"{iid}{ext}"
        tmp.replace(final)
        if not is_url:
            conn.execute("UPDATE items SET asset_url = ? WHERE id = ?", (str(final), iid)); conn.commit()
        dest = paths.thumbs_dir() / f"{iid}.jpg"
        dest.parent.mkdir(parents=True, exist_ok=True)
        tthumb.replace(dest)
        db.set_thumb(conn, iid, f"thumbs/{iid}.jpg", h)
        return iid
    finally:
        tmp.unlink(missing_ok=True)
        tthumb.unlink(missing_ok=True)


def add(conn, target: str, *, kind: str | None = None, tags: list[str] = [], language: str | None = None,
        fetch=None, renderer=None) -> list[str]:
    """Add a file, folder (non-recursive), image URL or page URL; returns the new item ids."""
    if _is_url(target):
        if _fetch.banned(target):
            raise _fetch.FetchError(f"banned host: {target}")
        sources = [target]
    else:
        p = Path(target).expanduser()
        if p.is_dir():
            sources = [str(f) for f in sorted(p.iterdir()) if f.is_file() and (kind or f.suffix.lower() in KIND_BY_EXT)]
        elif p.is_file():
            sources = [str(p)]
        else:
            raise ValueError(f"no such file or folder: {target}")
    if sources and any(_is_url(s) for s in sources) and fetch is None:
        fetch = _fetch.Fetcher(renderer=renderer)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    db.upsert_source(conn, SOURCE)
    langs = [language] if language else []
    existing = db.get_collection(conn, COLLECTION)
    langs = list(dict.fromkeys([*(existing["languages"] if existing else []), *langs]))
    coll_id = db.upsert_collection(conn, "mine", CollectionDraft(COLLECTION, kind or "image", "Mine: additions",
                                                                 languages=langs, policy="manual"))
    ids = [_one(conn, s, coll_id, kind, tags, language, fetch, now) for s in sources]
    db.finish_collection(conn, coll_id, now)
    return ids
