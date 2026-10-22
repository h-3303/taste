"""The `taste` command: moodboards at the top level, the design library under `lib`."""
import argparse
import sys
from pathlib import Path

from . import config

VERSION = "taste 0.1.0"
_USAGE = """usage: taste <command> [args]

moodboards:  new gather inbox-add scout keep sheet palette validate canvas brief survey-add survey-keep survey-canvas
rounds:       round render RUN STAGE --title T --out DIR [--repeat-of N] | round ingest RUN STAGE N DOC | round steer RUN | round final RUN COMMENTS | gaps RUN | combine RUN --from-round N
refine:      refine check RUN N | refine apply RUN N [--project DIR]   (round render RUN refine shows pass N)
profile:     profile show | profile project RUN [--project DIR] | profile apply RUN N   (round render RUN review shows proposals.json)
pages:       library-page --out DIR [--query Q] [--kind K] [--no-fetch]
additions:   add TARGET [--kind K] [--tag T ...] [--language L]
library:     lib search|show|collections|status|sources|pluck|cache|collection|add
import:      import [--dlib DIR] [--moodboards DIR] [--project DIR ...]
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


def _parser(prog: str, description: str = "") -> argparse.ArgumentParser:
    from .library.cli import _Parser   # usage errors exit 1, as everywhere in taste
    return _Parser(prog=prog, description=description or None)


def _cmd_maintainer(rest: list[str]) -> int:
    if rest and rest[0] in ("sync", "install-timer"):
        return _lib(rest)   # the library's own parser (and its --help) handles these
    ap = _parser("taste maintainer", "for whoever publishes seed snapshots")
    sub = ap.add_subparsers(dest="action", required=True, parser_class=type(ap))
    sub.add_parser("sync", help="sync every source, renderer ones included")
    sub.add_parser("install-timer", help="install the weekly taste-sync systemd user timer")
    sub.add_parser("seed-build", help="write a seed snapshot zip").add_argument("out")
    a = ap.parse_args(rest)
    from . import seed
    from .library import db, paths
    conn = db.connect(paths.db_path())
    rep = seed.build_seed(conn, paths.thumbs_dir(), Path(a.out))
    print(f"seed: {rep.files} files, {rep.links} links, {rep.skipped} skipped -> {a.out}")
    return 0


def _cmd_seed(rest: list[str]) -> int:
    ap = _parser("taste seed")
    sub = ap.add_subparsers(dest="action", required=True, parser_class=type(ap))
    sub.add_parser("install", help="install the seed library (downloads the latest unless ARCHIVE is given)") \
        .add_argument("archive", nargs="?", metavar="ARCHIVE")
    a = ap.parse_args(rest)
    from . import seed
    from .library import db, paths
    paths.ensure_dirs()
    archive = Path(a.archive) if a.archive else None
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


def _check_name(name: str) -> int:
    from .connectors import REGISTRY
    known = [*REGISTRY, "obscura"]
    if name in known:
        return 0
    print(f"error: unknown connector {name!r}; known: {', '.join(known)}", file=sys.stderr)
    return 1


def _cmd_connect(rest: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="taste connect")
    ap.add_argument("name"); ap.add_argument("--path"); ap.add_argument("--bin")
    a = ap.parse_args(rest)
    if (rc := _check_name(a.name)):
        return rc
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
    if (rc := _check_name(a.name)):
        return rc
    cfg = config.load()
    cfg.setdefault("connectors", {}).setdefault(a.name, {})["enabled"] = False
    config.save(cfg)
    print(f"disconnected {a.name}")
    return 0


def _cmd_connectors(rest: list[str]) -> int:
    _parser("taste connectors", "list configured connectors and whether each is on").parse_args(rest)
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
    from . import rounds
    from .boards.run import Run
    page = pages.render_round(a.run, a.stage, a.title, Path(a.out), repeat_of=a.repeat_of)
    print(page)
    print(f"pass: {a.stage} {rounds.next_n(Run(a.run), a.stage) - 1}")   # the n to ingest; each render starts one
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


def _cmd_combine(rest: list[str]) -> int:
    from . import combine, rounds
    from .boards.run import Run
    ap = argparse.ArgumentParser(prog="taste combine")
    ap.add_argument("run"); ap.add_argument("--from-round", type=int, required=True)
    a = ap.parse_args(rest)
    try:
        run = Run(a.run)
        new = combine.apply_combos(run, rounds.load(run, "directions", a.from_round))
    except (ValueError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    for m in new:
        print(f"{m['id']}\t{m['name']}")
    if not new:
        print(f"nothing new from round {a.from_round}")
    return 0


def _cmd_refine(rest: list[str]) -> int:
    from . import refine
    from .boards.run import Run
    ap = argparse.ArgumentParser(prog="taste refine")
    ap.add_argument("action", choices=("check", "apply")); ap.add_argument("run"); ap.add_argument("n", type=int)
    ap.add_argument("--project")
    a = ap.parse_args(rest)
    run = Run(a.run)
    try:
        doc = refine.load_options(run, a.n)
        errs = refine.check_options(doc, root=run.path)
        if errs:
            print("\n".join(f"error: {e}" for e in errs), file=sys.stderr)
            return 1
        if a.action == "check":
            k = sum(len(o) for o in doc["layers"].values())
            print(f"{refine.options_name(a.n)}: ok ({len(doc['layers'])} layers, {k} options)")
        else:
            print(refine.apply_pass(run, a.n, Path(a.project) if a.project else None))
    except (ValueError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


def _cmd_profile(rest: list[str]) -> int:
    from . import profile
    from .paths import profile_path
    ap = argparse.ArgumentParser(prog="taste profile")
    ap.add_argument("action", choices=("show", "project", "apply")); ap.add_argument("run", nargs="?")
    ap.add_argument("n", nargs="?", type=int); ap.add_argument("--project")
    a = ap.parse_args(rest)
    try:
        if a.action == "show":
            p = profile_path()
            print(p.read_text(encoding="utf-8").rstrip("\n") if p.is_file() else f"no profile yet ({p})")
        elif a.run is None or (a.action == "apply" and a.n is None):
            print("usage: taste profile show | project RUN [--project DIR] | apply RUN N", file=sys.stderr)
            return 2
        elif a.action == "project":
            print(profile.write_project_taste(a.run, Path(a.project) if a.project else None))
        else:
            res = profile.apply_review(a.run, a.n, profile_path())
            k = sum(len(v) for v in res["added"].values())
            print(f"{res['path']}: {k} new entr{'y' if k == 1 else 'ies'}")
    except (ValueError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


def _cmd_import(rest: list[str]) -> int:
    import json
    import sqlite3
    from . import importer, paths as tpaths
    ap = argparse.ArgumentParser(prog="taste import")
    ap.add_argument("--dlib"); ap.add_argument("--moodboards"); ap.add_argument("--project", action="append", default=[])
    a = ap.parse_args(rest)
    try:
        if a.dlib:
            from .library import db, paths
            paths.ensure_dirs()
            conn = db.connect(paths.db_path())
            try:
                print(f"{importer.import_library(Path(a.dlib), conn, paths.thumbs_dir())} library items imported")
            finally:
                conn.close()
        if a.moodboards:
            k = importer.import_runs(Path(a.moodboards), tpaths.runs_dir())
            print(f"{k} run{'' if k == 1 else 's'} imported")
            props = importer.import_profile(tpaths.runs_dir(), tpaths.profile_path())
            if props:
                out = tpaths.data_root() / "import-proposals.json"
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(json.dumps(props, indent=2, ensure_ascii=False), encoding="utf-8")
                print(f"{len(props)} profile proposals written to {out} (review them before they join the profile)")
        for p in a.project:
            made = importer.import_project(Path(p))
            print(f"{made} written" if made else f"{p}: nothing to do")
    except (OSError, sqlite3.Error) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


def _cmd_gaps(rest: list[str]) -> int:
    from . import rounds
    from .boards.run import Run
    ap = _parser("taste gaps", "what is thin so far in a run")
    ap.add_argument("run")
    a = ap.parse_args(rest)
    for line in rounds.gaps(Run(a.run)):
        print(line)
    return 0


_COMMANDS = {"import": _cmd_import, "round": _cmd_round, "refine": _cmd_refine, "profile": _cmd_profile, "combine": _cmd_combine, "library-page": _cmd_library_page, "gaps": _cmd_gaps, "add": _cmd_add, "lib": _cmd_lib, "sync": _cmd_sync, "maintainer": _cmd_maintainer, "seed": _cmd_seed,
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
