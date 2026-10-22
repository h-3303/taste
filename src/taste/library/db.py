import json
import sqlite3
from pathlib import Path

from .ids import new_id

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources(
  slug TEXT PRIMARY KEY, title TEXT, home_url TEXT, tier INTEGER, policy TEXT, notes TEXT DEFAULT '',
  error TEXT, synced_at TEXT);
CREATE TABLE IF NOT EXISTS collections(
  id TEXT PRIMARY KEY, slug TEXT UNIQUE NOT NULL, source TEXT NOT NULL, kind TEXT, title TEXT,
  query TEXT DEFAULT '', languages TEXT DEFAULT '[]', policy TEXT DEFAULT 'sync',
  item_count INTEGER DEFAULT 0, synced_at TEXT, error TEXT);
CREATE TABLE IF NOT EXISTS items(
  id TEXT PRIMARY KEY, key TEXT UNIQUE NOT NULL, source TEXT NOT NULL, kind TEXT NOT NULL, title TEXT,
  page_url TEXT, asset_url TEXT, thumb TEXT, tags TEXT DEFAULT '[]', meta TEXT DEFAULT '{}',
  license TEXT DEFAULT '', hash TEXT, search_text TEXT DEFAULT '', added_at TEXT, last_seen TEXT);
CREATE TABLE IF NOT EXISTS item_collections(
  item TEXT NOT NULL, collection TEXT NOT NULL, PRIMARY KEY(item, collection));
CREATE INDEX IF NOT EXISTS items_hash ON items(hash);
CREATE INDEX IF NOT EXISTS items_kind ON items(kind);
CREATE INDEX IF NOT EXISTS ic_collection ON item_collections(collection);
CREATE TABLE IF NOT EXISTS cache(path TEXT PRIMARY KEY, item TEXT, bytes INTEGER, last_used TEXT);
CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(
  title, tags, search_text, content='items', content_rowid='rowid');
CREATE TRIGGER IF NOT EXISTS items_ai AFTER INSERT ON items BEGIN
  INSERT INTO items_fts(rowid, title, tags, search_text) VALUES (new.rowid, new.title, new.tags, new.search_text);
END;
CREATE TRIGGER IF NOT EXISTS items_ad AFTER DELETE ON items BEGIN
  INSERT INTO items_fts(items_fts, rowid, title, tags, search_text)
  VALUES ('delete', old.rowid, old.title, old.tags, old.search_text);
END;
CREATE TRIGGER IF NOT EXISTS items_au AFTER UPDATE ON items BEGIN
  INSERT INTO items_fts(items_fts, rowid, title, tags, search_text)
  VALUES ('delete', old.rowid, old.title, old.tags, old.search_text);
  INSERT INTO items_fts(rowid, title, tags, search_text) VALUES (new.rowid, new.title, new.tags, new.search_text);
END;
"""


def connect(path) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    return conn


def _meta_text(meta: dict) -> str:
    out = []
    for k, v in meta.items():
        if k in ("code", "css", "images", "reference_images"):
            continue
        if isinstance(v, (list, tuple)):
            out += [str(x) for x in v if isinstance(x, (str, int, float))]
        elif isinstance(v, (str, int, float)):
            out.append(str(v))
    return " ".join(out)


def _search_text(conn, item_id: str, source: str, kind: str, meta: dict) -> str:
    slugs = [r[0] for r in conn.execute(
        "SELECT c.slug FROM item_collections ic JOIN collections c ON c.id = ic.collection WHERE ic.item = ?",
        (item_id,))]
    words = " ".join(s.replace("/", " ").replace("-", " ") for s in slugs)
    return f"{kind} {source} {words} {_meta_text(meta)}"[:4000]


def upsert_source(conn, info) -> None:
    conn.execute("""INSERT INTO sources(slug, title, home_url, tier, policy, notes) VALUES (?,?,?,?,?,?)
                    ON CONFLICT(slug) DO UPDATE SET title=excluded.title, home_url=excluded.home_url,
                    tier=excluded.tier, policy=excluded.policy, notes=excluded.notes""",
                 (info.slug, info.title, info.home_url, info.tier, info.policy, info.notes))
    conn.commit()


def set_source_error(conn, slug: str, error: str | None, now: str | None = None) -> None:
    conn.execute("UPDATE sources SET error = ?, synced_at = COALESCE(?, synced_at) WHERE slug = ?", (error, now, slug))
    conn.commit()


def upsert_collection(conn, source: str, c) -> str:
    row = conn.execute("SELECT id FROM collections WHERE slug = ?", (c.slug,)).fetchone()
    cid = row["id"] if row else new_id()
    conn.execute("""INSERT INTO collections(id, slug, source, kind, title, query, languages, policy)
                    VALUES (?,?,?,?,?,?,?,?)
                    ON CONFLICT(slug) DO UPDATE SET kind=excluded.kind, title=excluded.title, query=excluded.query,
                    languages=excluded.languages, policy=excluded.policy""",
                 (cid, c.slug, source, c.kind, c.title, c.query, json.dumps(c.languages), c.policy))
    conn.commit()
    return cid


def upsert_item(conn, source: str, d, collection_id: str, now: str) -> tuple[str, bool]:
    row = conn.execute("SELECT id FROM items WHERE key = ?", (d.key,)).fetchone()
    created = row is None
    iid = row["id"] if row else new_id()
    tags, meta = json.dumps(d.tags), json.dumps(d.meta, ensure_ascii=False)
    if created:
        conn.execute("""INSERT INTO items(id, key, source, kind, title, page_url, asset_url, tags, meta, license,
                        added_at, last_seen) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (iid, d.key, source, d.kind, d.title, d.page_url, d.asset_url, tags, meta, d.license, now, now))
    else:
        conn.execute("""UPDATE items SET title=?, page_url=?, asset_url=?, tags=?, meta=?, license=?, last_seen=?
                        WHERE id=?""", (d.title, d.page_url, d.asset_url, tags, meta, d.license, now, iid))
    conn.execute("INSERT OR IGNORE INTO item_collections(item, collection) VALUES (?,?)", (iid, collection_id))
    conn.execute("UPDATE items SET search_text = ? WHERE id = ?", (_search_text(conn, iid, source, d.kind, d.meta), iid))
    conn.commit()
    return iid, created


def set_thumb(conn, item_id: str, thumb: str | None, hash: str | None) -> None:
    conn.execute("UPDATE items SET thumb = ?, hash = ? WHERE id = ?", (thumb, hash, item_id))
    conn.commit()


def finish_collection(conn, collection_id: str, now: str, error: str | None = None) -> None:
    conn.execute("""UPDATE collections SET item_count = (SELECT COUNT(*) FROM item_collections WHERE collection = ?),
                    synced_at = ?, error = ? WHERE id = ?""", (collection_id, now, error, collection_id))
    conn.commit()


def _row(conn, r) -> dict:
    d = dict(r)
    d["tags"] = json.loads(d.get("tags") or "[]")
    d["meta"] = json.loads(d.get("meta") or "{}")
    d["collections"] = [x[0] for x in conn.execute(
        "SELECT c.slug FROM item_collections ic JOIN collections c ON c.id = ic.collection WHERE ic.item = ? ORDER BY c.slug",
        (d["id"],))]
    d.pop("search_text", None)
    return d


def get_item(conn, item_id: str) -> dict | None:
    r = conn.execute("""SELECT i.*, s.tier AS source_tier FROM items i JOIN sources s ON s.slug = i.source
                        WHERE i.id = ?""", (item_id,)).fetchone()
    return _row(conn, r) if r else None


def _crow(r) -> dict:
    d = dict(r)
    d["languages"] = json.loads(d.get("languages") or "[]")
    return d


def get_collection(conn, slug: str) -> dict | None:
    r = conn.execute("SELECT * FROM collections WHERE slug = ?", (slug,)).fetchone()
    return _crow(r) if r else None


def list_collections(conn, kind=None, source=None, language=None) -> list[dict]:
    sql, args = "SELECT * FROM collections WHERE 1=1", []
    if kind:
        sql += " AND kind = ?"; args.append(kind)
    if source:
        sql += " AND source = ?"; args.append(source)
    if language:
        sql += " AND languages LIKE ?"; args.append(f'%{json.dumps(language)}%')
    return [_crow(r) for r in conn.execute(sql + " ORDER BY slug", args)]


def query_items(conn, fts: str | None, kind=None, source=None, collection=None, language=None, limit=40) -> list[dict]:
    where, args = [], []
    if kind:
        where.append("i.kind = ?"); args.append(kind)
    if source:
        where.append("i.source = ?"); args.append(source)
    if collection:
        where.append("i.id IN (SELECT ic.item FROM item_collections ic JOIN collections c ON c.id = ic.collection WHERE c.slug = ?)")
        args.append(collection)
    if language:
        where.append("i.id IN (SELECT ic.item FROM item_collections ic JOIN collections c ON c.id = ic.collection WHERE c.languages LIKE ?)")
        args.append(f'%{json.dumps(language)}%')
    if fts:
        sql = ("SELECT i.*, bm25(items_fts) AS rank FROM items_fts JOIN items i ON i.rowid = items_fts.rowid "
               "WHERE items_fts MATCH ?")
        args = [fts] + args
        if where:
            sql += " AND " + " AND ".join(where)
        sql += " ORDER BY rank"
    else:
        sql = "SELECT i.*, 0 AS rank FROM items i"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY i.added_at DESC, i.rowid DESC"
    rows, seen_hash, out = conn.execute(sql, args), set(), []
    for r in rows:
        if r["hash"]:
            if r["hash"] in seen_hash:
                continue
            seen_hash.add(r["hash"])
        out.append(_row(conn, r))
        if len(out) >= limit:
            break
    return out


def items_without_thumb(conn, kind=None, source=None) -> list[dict]:
    sql, args = "SELECT * FROM items WHERE thumb IS NULL", []
    if kind:
        sql += " AND kind = ?"; args.append(kind)
    if source:
        sql += " AND source = ?"; args.append(source)
    return [_row(conn, r) for r in conn.execute(sql + " ORDER BY added_at", args)]


def stats(conn) -> dict:
    one = lambda q, *a: conn.execute(q, a).fetchone()[0]
    return {
        "items": one("SELECT COUNT(*) FROM items"),
        "collections": one("SELECT COUNT(*) FROM collections"),
        "sources": one("SELECT COUNT(*) FROM sources"),
        "thumbs": one("SELECT COUNT(*) FROM items WHERE thumb IS NOT NULL"),
        "by_kind": {r[0]: r[1] for r in conn.execute("SELECT kind, COUNT(*) FROM items GROUP BY kind ORDER BY kind")},
        "by_source": {r[0]: r[1] for r in conn.execute("SELECT source, COUNT(*) FROM items GROUP BY source ORDER BY source")},
        "errors": [dict(r) for r in conn.execute("SELECT slug, error FROM sources WHERE error IS NOT NULL")]
                  + [{"slug": r[0], "error": r[1]} for r in conn.execute("SELECT slug, error FROM collections WHERE error IS NOT NULL")],
        "cache_bytes": one("SELECT COALESCE(SUM(bytes), 0) FROM cache"),
    }
