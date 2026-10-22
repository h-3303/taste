"""Bring an existing dlib library, moodboards runs and project direction files into taste."""
import json
import shutil
from pathlib import Path

from . import profile
from .library import db
from .library.ids import new_id
from .licences import classify

_PROFILE_KEYS = (("Liked traits", "traits_liked"), ("Disliked traits", "traits_disliked"))


def _thumb_name(row_thumb) -> str | None:
    return Path(row_thumb).name if row_thumb else None


def import_library(src_dir: Path, conn, thumbs_dir: Path) -> int:
    """Copy items, collections and thumbnails from a dlib data dir, upserting by key.

    An existing key keeps its row and id (only a missing thumb is filled and `meta.private` added).
    Ids that collide with a different key are re-minted. Returns rows processed."""
    src_dir, thumbs_dir = Path(src_dir), Path(thumbs_dir)
    thumbs_dir.mkdir(parents=True, exist_ok=True)
    sconn = db.connect(src_dir / "library.db")
    try:
        for s in sconn.execute("SELECT * FROM sources"):
            d = dict(s)
            conn.execute(f"INSERT OR IGNORE INTO sources({','.join(d)}) VALUES ({','.join('?' * len(d))})", list(d.values()))
        cmap: dict[str, str] = {}
        for c in sconn.execute("SELECT * FROM collections"):
            d = dict(c)
            have = conn.execute("SELECT id FROM collections WHERE slug = ?", (d["slug"],)).fetchone()
            if have:
                cmap[d["id"]] = have[0]
                continue
            if conn.execute("SELECT 1 FROM collections WHERE id = ?", (d["id"],)).fetchone():
                d["id"] = new_id()
            conn.execute(f"INSERT INTO collections({','.join(d)}) VALUES ({','.join('?' * len(d))})", list(d.values()))
            cmap[c["id"]] = d["id"]
        imap: dict[str, str] = {}
        n = 0
        for r in sconn.execute("SELECT * FROM items ORDER BY rowid"):
            d = dict(r)
            meta = json.loads(d["meta"] or "{}")
            if classify(d["source"], d["license"] or "", d["page_url"] or "", d["asset_url"] or "") == "never":
                meta["private"] = True
            tname = _thumb_name(d["thumb"])
            src_thumb = src_dir / "thumbs" / tname if tname else None
            have = conn.execute("SELECT id, thumb, meta FROM items WHERE key = ?", (d["key"],)).fetchone()
            if have:
                iid = have["id"]
                emeta = json.loads(have["meta"] or "{}")
                if meta.get("private") and not emeta.get("private"):
                    conn.execute("UPDATE items SET meta = ? WHERE id = ?",
                                 (json.dumps({**emeta, "private": True}, ensure_ascii=False), iid))
                if src_thumb and src_thumb.is_file() and not (thumbs_dir / f"{iid}.jpg").is_file():
                    shutil.copyfile(src_thumb, thumbs_dir / f"{iid}.jpg")
                    conn.execute("UPDATE items SET thumb = ? WHERE id = ?", (f"thumbs/{iid}.jpg", iid))
            else:
                iid = d["id"]
                if conn.execute("SELECT 1 FROM items WHERE id = ?", (iid,)).fetchone():
                    iid = new_id()
                d["id"], d["meta"] = iid, json.dumps(meta, ensure_ascii=False)
                if src_thumb and src_thumb.is_file():
                    shutil.copyfile(src_thumb, thumbs_dir / f"{iid}.jpg")
                    d["thumb"] = f"thumbs/{iid}.jpg"
                else:
                    d["thumb"] = None
                conn.execute(f"INSERT INTO items({','.join(d)}) VALUES ({','.join('?' * len(d))})", list(d.values()))
            imap[r["id"]] = iid
            n += 1
        for ic in sconn.execute("SELECT item, collection FROM item_collections"):
            if ic["item"] in imap and ic["collection"] in cmap:
                conn.execute("INSERT OR IGNORE INTO item_collections(item, collection) VALUES (?,?)",
                             (imap[ic["item"]], cmap[ic["collection"]]))
        conn.commit()
        return n
    finally:
        sconn.close()


def import_runs(src_dir: Path, dest: Path) -> int:
    """Copy each moodboards `runs/<name>/` not already in `dest`; never overwrites. Returns runs copied."""
    runs = Path(src_dir) / "runs"
    dest = Path(dest)
    n = 0
    if not runs.is_dir():
        return 0
    for r in sorted(runs.iterdir()):
        if r.is_dir() and not (dest / r.name).exists():
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copytree(r, dest / r.name)
            n += 1
    return n


def import_profile(runs_dir: Path, profile_path: Path) -> list[dict]:
    """Proposals from every run's taste.json traits, deduped (and without what the profile already has).
    Writes nothing: the profile is confirm-first."""
    have = profile.read_profile(Path(profile_path))
    seen = {(s, profile._key(t)) for s, items in have.items() for t in items}
    out: list[dict] = []
    runs_dir = Path(runs_dir)
    for r in sorted(runs_dir.iterdir()) if runs_dir.is_dir() else []:
        f = r / "taste.json"
        if not f.is_file():
            continue
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        for section, key in _PROFILE_KEYS:
            for t in doc.get(key) or []:
                if isinstance(t, str) and t.strip() and (section, profile._key(t)) not in seen:
                    seen.add((section, profile._key(t)))
                    out.append({"id": f"i{len(out) + 1}", "section": section, "text": t.strip(), "default": False})
    return out


def import_project(project_dir: Path) -> Path | None:
    """Point `design/taste.md` at an existing `design/direction.md`; leave an existing taste.md alone."""
    d = Path(project_dir) / "design"
    out = d / "taste.md"
    if not (d / "direction.md").is_file() or out.exists():
        return None
    out.write_text("# Taste\n\n## Direction\n\nSee [direction.md](direction.md).\n", encoding="utf-8")
    return out
