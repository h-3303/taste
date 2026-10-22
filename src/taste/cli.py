"""The `taste` command: moodboards at the top level, the design library under `lib`."""
import argparse
import sys

from . import config

VERSION = "taste 0.1.0"
_USAGE = """usage: taste <command> [args]

moodboards:  new gather inbox-add scout keep sheet palette validate canvas brief survey-add survey-keep survey-canvas
library:     lib search|show|collections|status|sources|pluck|cache|collection|add
sync:        sync [source ...]            (API/repo sources only)
maintainer:  maintainer sync|install-timer
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
    if not rest or rest[0] not in ("sync", "install-timer"):
        print("usage: taste maintainer sync|install-timer", file=sys.stderr)
        return 1
    return _lib(rest)


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


_COMMANDS = {"lib": _cmd_lib, "sync": _cmd_sync, "maintainer": _cmd_maintainer,
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
