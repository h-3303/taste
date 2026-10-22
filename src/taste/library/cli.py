import argparse
import json
import sqlite3
import sys
from pathlib import Path

from . import cache as cache_mod, curated, db, paths, pluck as pluck_mod, search as search_mod, sheet as sheet_mod, sync as sync_mod, timer
from .fetch import FetchError, Fetcher
from .sources import base
import taste.library.sources  # noqa: F401  (registers adapters)


class MissingTool(Exception):
    """A required tool or the data directory is unusable (exit code 2)."""


def _obscura() -> str | None:
    b = paths.obscura_bin()
    return b if b and Path(b).exists() else None


def _conn():
    try:
        paths.ensure_dirs()
        return db.connect(paths.db_path())
    except (OSError, sqlite3.OperationalError) as e:
        raise MissingTool(f"data directory not usable: {paths.data_root()} ({e})") from e


def _fetcher():
    if not _obscura():
        raise MissingTool("obscura not found: download the x86_64-linux-stealth release from "
                          "https://github.com/h4ckf0r0day/obscura/releases into ~/.local/bin or enable the obscura connector in config.json")
    return Fetcher()


class _Parser(argparse.ArgumentParser):
    def error(self, message):  # exit 1, not argparse's 2 (2 means missing tool/data dir)
        self.print_usage(sys.stderr)
        print(f"error: {message}", file=sys.stderr)
        raise SystemExit(1)


def _out(obj, as_json: bool, lines: list[str]) -> None:
    if as_json:
        print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))
    else:
        print("\n".join(lines))


def _item_line(r: dict) -> str:
    colls = ",".join(r.get("collections", [])[:2])
    return f"{r['id']}  {r['kind']:<8} {r['title'][:60]:<60} {r['source']:<14} {colls}"


def cmd_sync(a) -> int:
    try:
        adapters = [base.get(s) for s in a.sources] if a.sources else base.all_adapters()
    except KeyError as e:
        print(f"error: {e.args[0]}", file=sys.stderr)
        return 1
    conn = _conn()
    opts = sync_mod.SyncOptions(sample=not a.full, max_collections=a.max_collections, max_items=a.max_items,
                                snapshot=a.snapshot, workers=a.workers, screenshots=a.screenshots)
    f = _fetcher()
    try:
        rep = sync_mod.sync(conn, adapters, f, paths.thumbs_dir(), opts, log=(lambda *_: None) if a.json else print,
                            explicit=bool(a.sources))
    finally:
        f.close()
    _out(rep.sources, a.json, [rep.summary()])
    return 0


def cmd_search(a) -> int:
    conn = _conn()
    rows, mode = search_mod.search_with_mode(conn, a.query, a.kind, a.source, a.collection, a.language, a.limit)
    lines = [_item_line(r) for r in rows] or ["no results"]
    if mode == "any":
        lines.insert(0, "no item matches all terms; showing any-term matches")
    if a.sheet:
        f = _fetcher()
        try:
            if any(r["kind"] == "font" and not r["thumb"] for r in rows):
                sync_mod.ensure_thumbs(conn, f, paths.thumbs_dir(), kind="font", limit=len(rows), log=lambda *_: None)
        finally:
            f.close()
        rows = [db.get_item(conn, r["id"]) for r in rows]
        sheets = sheet_mod.contact_sheets(rows, paths.data_root(), Path(a.sheet))
        lines += [f"sheet: {p}" for p in sheets]
        for r in rows:
            r["sheets"] = [str(p) for p in sheets]
    _out({"match": mode, "results": rows}, a.json, lines)
    return 0


def cmd_show(a) -> int:
    conn = _conn()
    r = db.get_item(conn, a.id)
    if not r:
        print(f"error: no item {a.id}", file=sys.stderr)
        return 1
    thumb = str(paths.data_root() / r["thumb"]) if r.get("thumb") else "(none)"
    lines = [f"{k}: {v}" for k, v in r.items() if k not in ("meta", "tags", "collections", "thumb")]
    lines += [f"thumb: {thumb}", f"tags: {', '.join(r['tags'])}", f"collections: {', '.join(r['collections'])}",
              "meta: " + json.dumps(r["meta"], ensure_ascii=False)[:2000]]
    _out({**r, "thumb_path": thumb}, a.json, lines)
    return 0


def cmd_collections(a) -> int:
    rows = db.list_collections(_conn(), a.kind, a.source, a.language)
    _out(rows, a.json, [f"{c['slug']:<42} {c['kind']:<8} {c['item_count']:>5}  {c.get('synced_at') or ''}" for c in rows])
    return 0


def cmd_status(a) -> int:
    conn = _conn()
    s = db.stats(conn)
    s["thumb_bytes"] = sum(p.stat().st_size for p in paths.thumbs_dir().glob("*.jpg"))
    s["obscura"] = _obscura() or "missing"
    lines = [f"items {s['items']}  collections {s['collections']}  sources {s['sources']}  thumbs {s['thumbs']} "
             f"({s['thumb_bytes'] // 1_000_000} MB)  cache {s['cache_bytes'] // 1_000_000} MB  obscura {s['obscura']}",
             "by kind: " + ", ".join(f"{k} {v}" for k, v in s["by_kind"].items()),
             "by source: " + ", ".join(f"{k} {v}" for k, v in s["by_source"].items())]
    lines += [f"error {e['slug']}: {e['error'][:120]}" for e in s["errors"]]
    _out(s, a.json, lines)
    return 0


def cmd_sources(a) -> int:
    rows = [{"slug": x.info.slug, "title": x.info.title, "tier": x.info.tier, "policy": x.info.policy, "home": x.info.home_url}
            for x in base.all_adapters()]
    _out(rows, a.json, [f"{r['slug']:<16} tier {r['tier']}  {r['policy']:<8} {r['title']}  {r['home']}" for r in rows])
    return 0


def cmd_pluck(a) -> int:
    conn = _conn()
    out = Path(a.out) if a.out else paths.cache_dir()
    opts = {k: v for k, v in (("res", a.res), ("map", a.map), ("weight", a.weight)) if v}
    f = Fetcher()  # downloads need only httpx; Obscura is for rendering, so pluck works without it
    results, failed = [], []
    try:
        for iid in a.ids:
            try:
                r = pluck_mod.pluck(conn, iid, f, out, opts, cache_root=paths.cache_dir())
                results.append({"id": iid, "path": str(r.path) if r.path else None, "text": r.text, "note": r.note})
            except (KeyError, ValueError, FetchError, OSError) as e:
                failed.append({"id": iid, "error": str(e)})
                print(f"error: {iid}: {e}", file=sys.stderr)
    finally:
        f.close()
    lines = []
    for r in results:
        lines.append(f"{r['id']}  {r['path'] or '(no file)'}  {r['note']}")
        if r["text"]:
            lines += ["", r["text"], ""]
    _out({"results": results, "failed": failed}, a.json, lines)
    return 1 if failed else 0


def cmd_collection(a) -> int:
    conn = _conn()
    cid = curated.new_collection(conn, a.slug, a.kind, a.title, a.language or [])
    _out({"id": cid, "slug": curated._slug(a.slug)}, a.json, [curated._slug(a.slug)])
    return 0


def cmd_add(a) -> int:
    conn = _conn()
    f = Fetcher()  # downloads need only httpx
    ids = []
    try:
        for src in a.sources:
            try:
                ids.append(curated.add(conn, a.collection, src, f, paths.thumbs_dir(), a.title or "", [t.strip() for t in a.tags.split(",") if t.strip()] if a.tags else [],
                                       a.page_url or "", a.language))
            except (KeyError, ValueError, FetchError, OSError) as e:
                print(f"error: {src}: {e}", file=sys.stderr)
                return 1
    finally:
        f.close()
    _out(ids, a.json, ids)
    return 0


def cmd_cache(a) -> int:
    conn = _conn()
    if a.action == "size":
        _out({"bytes": cache_mod.size(conn)}, a.json, [f"{cache_mod.size(conn) / 1e6:.1f} MB"])
        return 0
    removed = cache_mod.prune(conn, paths.cache_dir(), int(a.max_gb * 1024 ** 3))
    _out({"removed": [str(p) for p in removed]}, a.json, [f"removed {len(removed)} files; cache now {cache_mod.size(conn) / 1e6:.1f} MB"])
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = _Parser(prog="dlib", description="h's design library")
    ap.add_argument("--json", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("sync", help="run source adapters (sample mode unless --full)")
    p.add_argument("sources", nargs="*"); p.add_argument("--full", action="store_true")
    p.add_argument("--max-collections", type=int); p.add_argument("--max-items", type=int)
    p.add_argument("--snapshot", action="store_true", help="allow tier-3 sources (one-off)")
    p.add_argument("--workers", type=int, default=8); p.add_argument("--screenshots", action="store_true")
    p.set_defaults(fn=cmd_sync)
    p = sub.add_parser("search"); p.add_argument("query", nargs="?", default="")
    for opt in ("--kind", "--source", "--collection", "--language"):
        p.add_argument(opt)
    p.add_argument("--limit", type=int, default=40); p.add_argument("--sheet", help="write contact sheets into DIR")
    p.set_defaults(fn=cmd_search)
    p = sub.add_parser("show"); p.add_argument("id"); p.set_defaults(fn=cmd_show)
    p = sub.add_parser("collections")
    for opt in ("--kind", "--source", "--language"):
        p.add_argument(opt)
    p.set_defaults(fn=cmd_collections)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    sub.add_parser("sources").set_defaults(fn=cmd_sources)
    p = sub.add_parser("pluck", help="fetch the full asset / css / hex / code for items")
    p.add_argument("ids", nargs="+"); p.add_argument("--out"); p.add_argument("--res"); p.add_argument("--map"); p.add_argument("--weight")
    p.set_defaults(fn=cmd_pluck)
    p = sub.add_parser("cache"); p.add_argument("action", choices=["prune", "size"]); p.add_argument("--max-gb", type=float, default=2.0)
    p.set_defaults(fn=cmd_cache)
    p = sub.add_parser("collection"); sp = p.add_subparsers(dest="action", required=True)
    q = sp.add_parser("new"); q.add_argument("slug"); q.add_argument("--kind", required=True); q.add_argument("--title"); q.add_argument("--language", action="append")
    q.set_defaults(fn=cmd_collection)
    p = sub.add_parser("add", help="add a url or file to a curated collection")
    p.add_argument("collection"); p.add_argument("sources", nargs="+"); p.add_argument("--title"); p.add_argument("--tags"); p.add_argument("--page-url"); p.add_argument("--language")
    p.set_defaults(fn=cmd_add)
    sub.add_parser("install-timer", help="install the weekly systemd user timer").set_defaults(fn=lambda a: (print(f"installed under {timer.install()} (weekly, Sunday 04:00)"), 0)[1])
    return ap


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    try:
        return a.fn(a)
    except MissingTool as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
