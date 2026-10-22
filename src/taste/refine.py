"""Refine passes: per-layer options shown as stills, one pick per layer, written to taste.md and direction.md."""
import re
from datetime import date
from pathlib import Path

from . import rounds
from .boards.run import Run, md_line

LAYERS = {"ui": ("ground", "cards", "depth", "ui", "type", "accent"),
          "graphic": ("ground", "type", "accent", "imagery", "texture")}
MIN_OPTIONS, MAX_OPTIONS = 2, 6
LIMIT = 600
FINISH = "## Current finish"
_ID = re.compile(r"[A-Za-z0-9_-]{1,40}")


def _run(run) -> Run:
    return run if isinstance(run, Run) else Run(run)


def options_name(n: int) -> str:
    return f"refine/{n}-options.json"


def load_options(run, n: int) -> dict:
    run = _run(run)
    if not run.has(options_name(n)):
        raise ValueError(f"write {options_name(n)} first")
    return run.read(options_name(n))


def check_options(doc: dict, root: Path | None = None) -> list[str]:
    """Errors in an options doc, empty when valid. With `root` (the run folder), stills must be files under it."""
    errs = []
    kind = doc.get("kind")
    if kind not in LAYERS:
        return [f"kind must be one of {', '.join(LAYERS)}, not {kind!r}"]
    layers = doc.get("layers")
    if not isinstance(layers, dict) or not layers:
        return ["layers must map at least one layer to its options"]
    for layer, opts in layers.items():
        if layer not in LAYERS[kind]:
            errs.append(f"unknown layer {layer!r} for {kind} (one of {', '.join(LAYERS[kind])})")
            continue
        if not isinstance(opts, list) or not MIN_OPTIONS <= len(opts) <= MAX_OPTIONS:
            k = len(opts) if isinstance(opts, list) else 0
            errs.append(f"{layer}: needs {MIN_OPTIONS} to {MAX_OPTIONS} options, has {k}")
            if not isinstance(opts, list):
                continue
        seen = set()
        for o in opts:
            oid = o.get("id") if isinstance(o, dict) else None
            if not isinstance(oid, str) or not _ID.fullmatch(oid):
                errs.append(f"{layer}: option id {oid!r} must be 1-40 letters, digits, - or _")
                continue
            if oid in seen:
                errs.append(f"{layer}: duplicate option id {oid!r}")
            seen.add(oid)
            if not str(o.get("label") or "").strip():
                errs.append(f"{layer}:{oid}: missing label")
            still = o.get("still")
            if not isinstance(still, str) or not still:
                errs.append(f"{layer}:{oid}: missing still")
            elif root is not None:
                base = Path(root).resolve()
                p = (base / still).resolve()
                if not p.is_relative_to(base) or not p.is_file():
                    errs.append(f"{layer}:{oid}: no still file {still} in the run folder")
    return errs


def layers_of(doc: dict) -> list[str]:
    """The doc's layers in their canonical order."""
    return [x for x in LAYERS[doc["kind"]] if x in doc["layers"]]


def shown_ids(doc: dict) -> list[str]:
    """Each layer (`<layer>`, for its note) followed by its options (`<layer>:<option id>`)."""
    return [x for layer in layers_of(doc) for x in (layer, *(f"{layer}:{o['id']}" for o in doc["layers"][layer]))]


def _c(text) -> str:
    return md_line(text, LIMIT)


def _section(text: str, heading: re.Pattern) -> tuple[int, int] | None:
    """Start and end of the section whose heading line matches, ending at the next `## ` heading or EOF."""
    m = heading.search(text)
    if not m:
        return None
    nxt = text.find("\n## ", m.end())
    return m.start(), (nxt + 1 if nxt >= 0 else len(text))


def _finish_lines(body: str) -> dict[str, str]:
    return {m.group(1): m.group(0) for m in re.finditer(r"^- ([a-z]+): .*$", body, re.M)}


def _rewrite_finish(text: str, picked: dict[str, str], kind: str) -> str:
    head = re.compile(rf"^{re.escape(FINISH)}\n", re.M)
    span = _section(text, head)
    old = _finish_lines(text[span[0]:span[1]]) if span else {}
    merged = {**old, **picked}
    order = [x for x in LAYERS[kind] if x in merged] + [x for x in merged if x not in LAYERS[kind]]
    lines = [merged[x] for x in order] or ["Not refined yet."]
    if span is None:
        sep = "" if text.endswith("\n") or not text else "\n"
        return f"{text}{sep}\n{FINISH}\n\n" + "\n".join(lines) + "\n"
    start, end = span
    tail = "\n" if end < len(text) else ""
    return text[:start] + f"{FINISH}\n\n" + "\n".join(lines) + "\n" + tail + text[end:]


def _pass_section(n: int, doc: dict, r) -> tuple[list[str], dict[str, str]]:
    lines, finish = [], {}
    for layer in layers_of(doc):
        opts = doc["layers"][layer]
        state = lambda o: r.items.get(f"{layer}:{o['id']}")  # noqa: E731
        picked = next((o for o in opts if (s := state(o)) and s.vote == "pick"), None)
        notes = []
        if (s := r.items.get(layer)) and s.note:
            notes.append(_c(s.note))
        for o in opts:
            if (s := state(o)) and s.note:
                notes.append(_c(s.note) if o is picked else f"on {_c(o['label'])}: {_c(s.note)}")
        if picked is None and not notes:
            continue
        label = _c(picked["label"]) if picked else "(no pick)"
        lines.append(f"- {layer}: {label}" + (f" — {'; '.join(notes)}" if notes else ""))
        if picked:
            detail = _c(picked.get("detail", ""))
            finish[layer] = f"- {layer}: {label}" + (f" — {detail}" if detail else "")
    lines += [f"- prompt: {_c(p)}" for p in r.prompts]
    if r.note:
        lines.append(f"- note: {_c(r.note)}")
    return lines or ["- nothing picked or noted"], finish


def apply_pass(run, n: int, project_dir: Path | None) -> Path:
    """Append pass `n` to taste.md and rewrite direction.md's "Current finish" section. Touches no other file."""
    run = _run(run)
    doc = load_options(run, n)
    r = rounds.load(run, "refine", n)
    if r.at is None:
        raise ValueError(f"ingest refine pass {n} first (taste round ingest)")
    dest = Path(project_dir) / "design" if project_dir else run.path
    direction, taste = dest / "direction.md", dest / "taste.md"
    if not direction.is_file():
        raise ValueError(f"no {direction}: write the brief first")
    lines, picked = _pass_section(n, doc, r)
    section = f"## Refine pass {n} ({date.today().isoformat()})\n\n" + "\n".join(lines) + "\n"
    old = taste.read_text(encoding="utf-8") if taste.is_file() else ""
    span = _section(old, re.compile(rf"^## Refine pass {n} \(.*\n", re.M))
    if span:
        start, end = span
        new_taste = old[:start] + section + ("\n" if end < len(old) else "") + old[end:]
    else:
        new_taste = old + ("\n" if old and not old.endswith("\n\n") else "") + section
    new_direction = _rewrite_finish(direction.read_text(encoding="utf-8"), picked, doc["kind"])
    taste.write_text(new_taste, encoding="utf-8")
    direction.write_text(new_direction, encoding="utf-8")
    return taste
