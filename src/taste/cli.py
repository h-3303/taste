"""The `taste` command: moodboards at the top level, the design library under `lib`."""
import argparse
import sys
from pathlib import Path

from . import config

VERSION = "taste 0.1.0"
_USAGE = """usage: taste <command> [args]

moodboards:  new gather inbox-add scout keep sheet palette validate canvas brief survey-add survey-keep survey-canvas
rounds:       round render RUN STAGE --title T --out DIR [--repeat-of N] | round ingest RUN STAGE N DOC | round steer RUN | round final RUN COMMENTS | gaps RUN
pages:       library-page --out DIR [--query Q] [--kind K] [--no-fetch]
additions:   add TARGET [--kind K] [--tag T ...] [--language L]
library:     lib search|show|collections|status|sources|pluck|cache|collection|add
sync:        sync [source ...]            (API/repo sources only)
seed:        seed install [ARCHIVE]
maintainer:  maintainer sync|install-timer|seed-build OUT
connectors:  connect <name> [--path P] [--bin B] | disconnect <name> | connectors
             --version
"""
_LIB_USER = {"search", "show", "collections", "status", "sources", "pluck", "cache", "collection", "add"}


def _lib(argv: list[str]) -> int:
    """Run dlib's parser; its --json is top-level, so accept it anywhere and move it to the front."""
    from .library import cli as lib_cli
    argv = list(argv)
    pre = ["--json"] if "--json" in argv else []
    return lib_cli.main(pre + [x for x in argv if x != "--json"])


def _cmd_lib(rest: list[str]) -> int:
    sub = next((x for x in rest if not x.startswith("-")), None)
    if sub not in _LIB_USER:
        print(f"error: taste lib {sub or ''}: expected one of {', '.join(sorted(_LIB_USER))}", file=sys.stderr)
        return 1
    return _lib(rest)


def _cmd_sync(rest: list[str]) -> int:
    from .library.sources import base
    import taste.library.sources  # noqa: F401  (registers adapters)
    ap = argparse.ArgumentParser(prog="taste sync")
    ap.add_argument("sources", nargs="*"); ap.add_argument("--full", action="store_true")
    ap.add_argument("--max-collections", type=int); ap.add_argument("--max-items", type=int)
    ap.add_argument("--workers", type=int, default=8); ap.add_argument("--json", action="store_true")
    a = ap.parse_args(rest)
    for slug in a.sources:
        try:
            tier = base.get(slug).info.tier
        except KeyError as e:
            print(f"error: {e.args[0]}", file=sys.stderr)
            return 1
        if tier > 1:
            print(f"{slug} needs a renderer: maintainer only (taste maintainer sync)", file=sys.stderr)
            return 1
    out = ["sync", *a.sources, "--max-tier", "1", "--workers", str(a.workers)]
    if a.full:
        out.append("--full")
    for flag, val in (("--max-collections", a.max_collections), ("--max-items", a.max_items)):
        if val is not None:
            out += [flag, str(val)]
    return _lib((["--json"] if a.json else []) + out)


def _cmd_maintainer(rest: list[str]) -> int:
    if rest and rest[0] == "seed-build":
        if len(rest) != 2:
            print("usage: taste maintainer seed-build OUT", file=sys.stderr)
            return 1
        from . import seed
        from .library import db, paths
        conn = db.connect(paths.db_path())
        rep = seed.build_seed(conn, paths.thumbs_dir(), Path(rest[1]))
        print(f"seed: {rep.files} files, {rep.links} links, {rep.skipped} skipped -> {rest[1]}")
        return 0
    if not rest or rest[0] not in ("sync", "install-timer"):
        print("usage: taste maintainer sync|install-timer|seed-build OUT", file=sys.stderr)
        return 1
    return _lib(rest)


def _cmd_seed(rest: list[str]) -> int:
    if not rest or rest[0] != "install" or len(rest) > 2:
        print("usage: taste seed install [ARCHIVE]", file=sys.stderr)
        return 1
    from . import seed
    from .library import db, paths
    paths.ensure_dirs()
    archive = Path(rest[1]) if len(rest) == 2 else None
    if archive is None:
        archive = paths.data_root() / "taste-seed.zip"
        print(f"downloading {seed.SEED_URL}")
        try:
            seed.download(seed.SEED_URL, archive)
        except Exception as e:
            print(f"error: could not download the seed: {e}", file=sys.stderr)
            return 1
    conn = db.connect(paths.db_path())
    print(f"seed: {seed.install_seed(archive, conn, paths.thumbs_dir())} items installed")
    return 0


def _cmd_connect(rest: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="taste connect")
    ap.add_argument("name"); ap.add_argument("--path"); ap.add_argument("--bin")
    a = ap.parse_args(rest)
    cfg = config.load()
    entry = {**cfg.setdefault("connectors", {}).get(a.name, {}), "enabled": True}
    for key in ("path", "bin"):
        if getattr(a, key) is not None:
            entry[key] = getattr(a, key)
    cfg["connectors"][a.name] = entry
    config.save(cfg)
    print(f"connected {a.name}")
    return 0


def _cmd_disconnect(rest: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="taste disconnect")
    ap.add_argument("name")
    a = ap.parse_args(rest)
    cfg = config.load()
    cfg.setdefault("connectors", {}).setdefault(a.name, {})["enabled"] = False
    config.save(cfg)
    print(f"disconnected {a.name}")
    return 0


def _cmd_connectors(rest: list[str]) -> int:
    conns = config.load().get("connectors", {})
    for name, c in sorted(conns.items()):
        extra = " ".join(f"{k}={v}" for k, v in c.items() if k != "enabled")
        print(f"{name:<16} {'on ' if c.get('enabled') else 'off'} {extra}".rstrip())
    if not conns:
        print("no connectors configured")
    return 0


def _cmd_add(rest: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="taste add")
    ap.add_argument("target"); ap.add_argument("--kind"); ap.add_argument("--tag", action="append", default=[])
    ap.add_argument("--language")
    a = ap.parse_args(rest)
    import sqlite3
    from . import additions
    from .library import db, fetch, paths
    from .render import RendererMissing
    try:
        paths.ensure_dirs()
        conn = db.connect(paths.db_path())
        ids = additions.add(conn, a.target, kind=a.kind, tags=a.tag, language=a.language)
    except (ValueError, fetch.FetchError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except RendererMissing as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except (OSError, sqlite3.Error) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(f"added {len(ids)} item(s) to mine/additions")
    return 0


def _cmd_round(rest: list[str]) -> int:
    import json
    from . import rounds
    from .boards.run import Run
    usage = ("usage: taste round render <run> <stage> --title T --out DIR [--repeat-of N] | "
             "ingest <run> <stage> <n> <doc.json> | steer <run> | final <run> <comments.json>")
    try:
        if rest[:1] == ["render"]:
            return _round_render(rest[1:])
        if rest[:1] == ["ingest"] and len(rest) == 5:
            r = rounds.ingest(Run(rest[1]), rest[2], int(rest[3]), json.loads(Path(rest[4]).read_text(encoding="utf-8")))
            print(f"{r.stage} round {r.n}: {len(r.items)} item(s) recorded")
        elif rest[:1] == ["steer"] and len(rest) == 2:
            print(json.dumps(rounds.steering(Run(rest[1])), indent=2, ensure_ascii=False))
        elif rest[:1] == ["final"] and len(rest) == 3:
            r = rounds.record_final(Run(rest[1]), json.loads(Path(rest[2]).read_text(encoding="utf-8")))
            print(f"final round {r.n}: {len(r.items)} comment(s) recorded")
        else:
            print(usage, file=sys.stderr)
            return 2
    except (ValueError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


def _round_render(rest: list[str]) -> int:
    from . import pages
    ap = argparse.ArgumentParser(prog="taste round render")
    ap.add_argument("run"); ap.add_argument("stage"); ap.add_argument("--title", required=True)
    ap.add_argument("--out", required=True); ap.add_argument("--repeat-of", type=int)
    a = ap.parse_args(rest)
    if a.stage not in pages.PAGES:
        print(f"error: stage {a.stage} has no page yet", file=sys.stderr)
        return 1
    page = pages.render_round(a.run, a.stage, a.title, Path(a.out), repeat_of=a.repeat_of)
    print(page)
    return 0


def _cmd_library_page(rest: list[str]) -> int:
    from . import pages
    from .library import db, paths
    ap = argparse.ArgumentParser(prog="taste library-page")
    ap.add_argument("--out", required=True); ap.add_argument("--query", default=""); ap.add_argument("--kind")
    ap.add_argument("--no-fetch", action="store_true", help="use only thumbnails already on disk")
    a = ap.parse_args(rest)
    fetch = None
    if not a.no_fetch:
        from .library.fetch import Fetcher
        fetch = Fetcher()
    paths.ensure_dirs()
    conn = db.connect(paths.db_path())
    try:
        print(pages.render_library(conn, Path(a.out), query=a.query, kind=a.kind, fetch=fetch))
    finally:
        conn.close()
    return 0


def _cmd_gaps(rest: list[str]) -> int:
    from . import rounds
    from .boards.run import Run
    if len(rest) != 1:
        print("usage: taste gaps <run>", file=sys.stderr)
        return 2
    for line in rounds.gaps(Run(rest[0])):
        print(line)
    return 0


_COMMANDS = {"round": _cmd_round, "library-page": _cmd_library_page, "gaps": _cmd_gaps, "add": _cmd_add, "lib": _cmd_lib, "sync": _cmd_sync, "maintainer": _cmd_maintainer, "seed": _cmd_seed,
             "connect": _cmd_connect, "disconnect": _cmd_disconnect, "connectors": _cmd_connectors}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "--version":
        print(VERSION)
        return 0
    if not argv or argv[0] in ("-h", "--help"):
        print(_USAGE)
        return 0 if argv else 1
    if argv[0] in _COMMANDS:
        return _COMMANDS[argv[0]](argv[1:])
    from .boards import cli as boards_cli
    return boards_cli.main(argv)
