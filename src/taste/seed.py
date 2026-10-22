"""Seed snapshots: a zip of dlib's database plus thumbnails, shipping open files and gallery links only."""
import json
import shutil
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .library import db
from .library.fetch import banned
from .licences import classify

SEED_URL = "https://github.com/h-3303/taste/releases/latest/download/taste-seed.zip"
EMPTY_MESSAGE = "Your library is empty: run `taste seed install` first (or `taste add` your own)"
_ITEM_COLS = ("id", "key", "source", "kind", "title", "page_url", "asset_url", "thumb", "tags", "meta",
              "license", "hash", "search_text", "added_at", "last_seen")


_DROP_META = {"code", "css", "origin", "images", "reference_images", "path", "file"}


def _is_http(v: str) -> bool:
    return v.startswith(("http://", "https://"))


def _clean(v):
    """Scrub a meta value: drop local paths, data: URIs and banned hosts (recursively); None means drop."""
    if isinstance(v, str):
        if v.startswith("data:") or (v.startswith(("/", "~", "file:")) or v[1:3] in (":\\", ":/")):
            return None
        if _is_http(v) and banned(v):
            return None
        return v
    if isinstance(v, list):
        return [c for c in (_clean(x) for x in v) if c is not None]
    if isinstance(v, dict):
        return {k: c for k, x in v.items() if k not in _DROP_META and (c := _clean(x)) is not None}
    return v


@dataclass
class SeedReport:
    files: int
    links: int
    skipped: int


def library_is_empty(conn) -> bool:
    return conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 0


def download(url: str, dest: Path) -> None:
    import httpx
    with httpx.stream("GET", url, follow_redirects=True, timeout=120.0) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_bytes():
                f.write(chunk)


def build_seed(conn, thumbs_dir: Path, out: Path) -> SeedReport:
    thumbs_dir, out = Path(thumbs_dir), Path(out)
    files = links = skipped = 0
    shipped: dict[str, str] = {}      # item id -> "file" | "link"
    with tempfile.TemporaryDirectory() as tmp:
        seed_path = Path(tmp) / "seed.db"
        sdb = db.connect(seed_path)
        thumb_files: list[Path] = []
        link_rows: list[dict] = []
        for r in conn.execute("SELECT * FROM items ORDER BY rowid"):
            meta = json.loads(r["meta"] or "{}")
            how = classify(r["source"], r["license"] or "", r["page_url"] or "", r["asset_url"] or "",
                           code=meta.get("code") or "")
            if how == "never" or meta.get("private"):
                skipped += 1
                continue
            row = {c: r[c] for c in _ITEM_COLS}
            if how == "file":
                files += 1
                src = thumbs_dir / Path(r["thumb"]).name if r["thumb"] else None
                if src and src.is_file():
                    thumb_files.append(src)
                else:
                    row["thumb"] = None
            else:
                links += 1
                row["thumb"] = None
                meta = _clean(meta)
                meta["shipping"] = "link"
                au = row["asset_url"] or ""
                row["asset_url"] = au if _is_http(au) and not banned(au) else ""
                row["hash"] = None
                row["meta"] = json.dumps(meta, ensure_ascii=False)
            shipped[r["id"]] = how
            if how == "link":
                link_rows.append(row)
            sdb.execute(f"INSERT INTO items({','.join(_ITEM_COLS)}) VALUES ({','.join('?' * len(_ITEM_COLS))})",
                        [row[c] for c in _ITEM_COLS])
        for ic in conn.execute("SELECT item, collection FROM item_collections"):
            if ic["item"] in shipped:
                sdb.execute("INSERT OR IGNORE INTO item_collections(item, collection) VALUES (?,?)", tuple(ic))
        for c in conn.execute("SELECT * FROM collections"):
            if sdb.execute("SELECT 1 FROM item_collections WHERE collection = ?", (c["id"],)).fetchone():
                d = dict(c)
                sdb.execute(f"INSERT INTO collections({','.join(d)}) VALUES ({','.join('?' * len(d))})", list(d.values()))
        sources = {x[0] for x in sdb.execute("SELECT DISTINCT source FROM items")}
        for s in conn.execute("SELECT * FROM sources"):
            if s["slug"] in sources:
                d = dict(s)
                sdb.execute(f"INSERT INTO sources({','.join(d)}) VALUES ({','.join('?' * len(d))})", list(d.values()))
        for row in link_rows:
            st = db._search_text(sdb, row["id"], row["source"], row["kind"], json.loads(row["meta"]))
            sdb.execute("UPDATE items SET search_text = ? WHERE id = ?", (st, row["id"]))
        sdb.commit()
        sdb.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        sdb.close()
        out.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(seed_path, "seed.db")
            for p in thumb_files:
                z.write(p, f"thumbs/{p.name}")
    return SeedReport(files, links, skipped)


def install_seed(archive: Path, conn, thumbs_dir: Path) -> int:
    thumbs_dir = Path(thumbs_dir)
    thumbs_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(archive) as z:
        seed_path = z.extract("seed.db", tmp)
        sdb = sqlite3.connect(seed_path)
        sdb.row_factory = sqlite3.Row
        for s in sdb.execute("SELECT * FROM sources"):
            d = dict(s)
            conn.execute(f"INSERT OR IGNORE INTO sources({','.join(d)}) VALUES ({','.join('?' * len(d))})", list(d.values()))
        cslug = {c["id"]: c["slug"] for c in sdb.execute("SELECT id, slug FROM collections")}
        for c in sdb.execute("SELECT * FROM collections"):
            d = dict(c)
            conn.execute(f"INSERT OR IGNORE INTO collections({','.join(d)}) VALUES ({','.join('?' * len(d))})", list(d.values()))
        for r in sdb.execute("SELECT * FROM items ORDER BY rowid"):
            if r["source"] == "mine":
                continue
            cur = conn.execute("SELECT id, thumb, source FROM items WHERE key = ?", (r["key"],)).fetchone()
            if cur and cur["source"] == "mine":
                continue
            thumb = r["thumb"]
            if thumb and f"thumbs/{Path(thumb).name}" in z.namelist():
                thumb = f"thumbs/{Path(thumb).name}"
                dest = thumbs_dir / Path(thumb).name
                if not dest.exists():
                    dest.write_bytes(z.read(f"thumbs/{Path(thumb).name}"))
            else:
                thumb = None
            if cur:
                iid = cur["id"]
                conn.execute("""UPDATE items SET title=?, page_url=?, asset_url=?, tags=?, meta=?, license=?,
                                search_text=?, last_seen=?, thumb=COALESCE(thumb, ?) WHERE id=?""",
                             (r["title"], r["page_url"], r["asset_url"], r["tags"], r["meta"], r["license"],
                              r["search_text"], r["last_seen"], thumb, iid))
            else:
                iid = r["id"]
                conn.execute(f"INSERT INTO items({','.join(_ITEM_COLS)}) VALUES ({','.join('?' * len(_ITEM_COLS))})",
                             [r[c] if c != "thumb" else thumb for c in _ITEM_COLS])
            for ic in sdb.execute("SELECT collection FROM item_collections WHERE item = ?", (r["id"],)):
                crow = conn.execute("SELECT id FROM collections WHERE slug = ?", (cslug[ic[0]],)).fetchone()
                if crow:
                    conn.execute("INSERT OR IGNORE INTO item_collections(item, collection) VALUES (?,?)", (iid, crow["id"]))
            n += 1
        conn.execute("""UPDATE collections SET item_count =
                        (SELECT COUNT(*) FROM item_collections WHERE collection = collections.id)""")
        conn.commit()
        sdb.close()
    return n
