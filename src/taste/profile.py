"""Two-layer taste profile: a general profile.md that grows across projects (written only from ticked review
proposals) and a per-project design/taste.md (direction, survey traits, every note)."""
import re
from datetime import date
from pathlib import Path

from . import rounds
from .boards.run import Run, md_line

SECTIONS = ("Liked traits", "Disliked traits", "Rules", "References", "Projects")
PROPOSAL_SECTIONS = SECTIONS[:4]
PROPOSALS = "proposals.json"
LIMIT = 300
NOTE_LIMIT = 600
_ID = re.compile(r"[A-Za-z0-9_-]{1,40}")
_REFINE = re.compile(r"^## Refine pass ", re.M)


def _run(run) -> Run:
    return run if isinstance(run, Run) else Run(run)


def _md(text, limit: int = LIMIT) -> str:
    return md_line(text, limit)


def _key(text: str) -> str:
    return " ".join(str(text).split()).casefold()


def read_profile(path: Path) -> dict[str, list[str]]:
    """Every section in SECTIONS (empty when missing), plus any other `## ` section found, in file order."""
    data: dict[str, list[str]] = {s: [] for s in SECTIONS}
    path = Path(path)
    if not path.is_file():
        return data
    current = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            data.setdefault(current, [])
        elif current is not None and line.strip():
            entry = line[2:] if line.startswith("- ") else line
            if entry.strip():
                data[current].append(entry.strip())
    return data


def write_profile(path: Path, data: dict[str, list[str]]) -> Path:
    path = Path(path)
    keys = list(SECTIONS) + [k for k in data if k not in SECTIONS]
    out = ["# Taste profile", ""]
    for k in keys:
        out += [f"## {' '.join(str(k).split())}", ""]
        out += [f"- {' '.join(str(e).split())}" for e in data.get(k, []) if str(e).strip()]
        out.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out).rstrip("\n") + "\n", encoding="utf-8")
    return path


def check_proposals(items) -> list[str]:
    """Errors in a proposals list, empty when valid."""
    if not isinstance(items, list) or not items:
        return ["proposals must be a non-empty list"]
    errs, seen = [], set()
    for p in items:
        pid = p.get("id") if isinstance(p, dict) else None
        if not isinstance(pid, str) or not _ID.fullmatch(pid):
            errs.append(f"proposal id {pid!r} must be 1-40 letters, digits, - or _")
            continue
        if pid in seen:
            errs.append(f"duplicate proposal id {pid!r}")
        seen.add(pid)
        if p.get("section") not in PROPOSAL_SECTIONS:
            errs.append(f"{pid}: section {p.get('section')!r} must be one of {', '.join(PROPOSAL_SECTIONS)}")
        if not str(p.get("text") or "").strip():
            errs.append(f"{pid}: missing text")
        if not isinstance(p.get("default"), bool):
            errs.append(f"{pid}: default must be true or false")
    return errs


def load_proposals(run) -> list[dict]:
    run = _run(run)
    if not run.has(PROPOSALS):
        raise ValueError(f"write {PROPOSALS} first")
    items = run.read(PROPOSALS)
    errs = check_proposals(items)
    if errs:
        raise ValueError(f"{PROPOSALS}: " + "; ".join(errs))
    return items


def snapshot_name(n: int) -> str:
    return f"review/{n}-proposals.json"


def _fence(line: str) -> bool:
    return line.lstrip().startswith(("```", "~~~"))


def _outline(lines: list[str]) -> list[tuple[int, str]]:
    """(index, name) of every `## ` heading outside code fences."""
    out, fenced = [], False
    for i, line in enumerate(lines):
        if _fence(line):
            fenced = not fenced
        elif not fenced and line.startswith("## "):
            out.append((i, line[3:].strip()))
    return out


def _bullets(lines: list[str]) -> list[str]:
    """Top-level bullets outside code fences."""
    out, fenced = [], False
    for line in lines:
        if _fence(line):
            fenced = not fenced
        elif not fenced and line[:2] in ("- ", "* ", "+ "):
            out.append(line[2:].strip())
    return out


def _append(text: str, additions: dict[str, list[str]]) -> tuple[str, dict[str, list[str]]]:
    """Insert new `- ` lines at the end of each section's existing text, creating missing sections at the end.
    Only inserts: every existing byte stays where it was. Returns the new text and what was actually added."""
    added: dict[str, list[str]] = {s: [] for s in SECTIONS}
    missing: list[str] = []
    for section in SECTIONS:
        lines = text.splitlines(keepends=True)
        heads = _outline(lines)
        at = next((k for k, (_, name) in enumerate(heads) if name == section), None)
        start = heads[at][0] + 1 if at is not None else len(lines)
        end = heads[at + 1][0] if at is not None and at + 1 < len(heads) else len(lines)
        have = {_key(b) for b in _bullets(lines[start:end])} if at is not None else set()
        for entry in additions.get(section, []):
            if entry and _key(entry) not in have:
                have.add(_key(entry))
                added[section].append(entry)
        if not added[section]:
            continue
        block = [f"- {e}\n" for e in added[section]]
        if at is None:
            missing.append(section)
            continue
        filled = [i for i in range(start, end) if lines[i].strip()]
        pos = filled[-1] + 1 if filled else start
        if not filled:
            block = ["\n"] + block
        if pos > 0 and not lines[pos - 1].endswith("\n"):
            lines[pos - 1] += "\n"
        lines[pos:pos] = block
        text = "".join(lines)
    for section in missing:
        if text and not text.endswith("\n"):
            text += "\n"
        text += ("\n" if text else "") + f"## {section}\n\n" + "".join(f"- {e}\n" for e in added[section])
    return text, added


def _project_dir(run: Run) -> Path | None:
    if run.has("project.json"):
        d = run.read("project.json").get("dir")
        return Path(d) if d else None
    return None


def _dest(run: Run, project_dir: Path | None) -> Path:
    return Path(project_dir) / "design" if project_dir else run.path


def _picked(run: Run, project_dir: Path | None) -> dict | None:
    """The chosen direction, from the brief's `# Design direction: <name>` heading, matched to directions.json."""
    f = _dest(run, project_dir) / "direction.md"
    if not f.is_file():
        return None
    m = re.match(r"# Design direction: (.*)", f.read_text(encoding="utf-8"))
    if not m:
        return None
    name = m.group(1).strip()
    ds = run.read("directions.json").get("directions", []) if run.has("directions.json") else []
    return next((d for d in ds if d.get("name") == name), {"name": name})


def _slug(run: Run, project_dir: Path | None) -> str:
    if project_dir:
        return Path(project_dir).name
    return re.sub(r"^\d{4}-\d{2}-\d{2}-", "", run.path.name)


def _head(run: Run, project_dir: Path | None) -> str:
    d = _picked(run, project_dir)
    lines = [f"# Taste: {_md(_slug(run, project_dir), 80)}", "", "## Direction", ""]
    if d is None:
        lines.append("No direction picked yet.")
    else:
        lines.append(f"- {_md(d['name'], 80)}" + (f" (mix {_md(d['id'], 40)})" if d.get("from") else ""))
        if d.get("from"):
            lines.append("- " + ", ".join(f"{_md(p, 40)} from {_md(s, 40)}" for p, s in d["from"].items()))
        if d.get("note"):
            lines.append(f"- note: {_md(d['note'], NOTE_LIMIT)}")
    t = run.read("taste.json") if run.has("taste.json") else {}
    survey = [f"- {label}: " + "; ".join(_md(v) for v in t[key])
              for label, key in (("Liked traits", "traits_liked"), ("Disliked traits", "traits_disliked")) if t.get(key)]
    if t.get("note"):
        survey.append(f"- Note: {_md(t['note'], NOTE_LIMIT)}")
    lines += ["", "## Survey", ""] + (survey or ["No survey traits yet."])
    notes = rounds.steering(run)["notes"]
    lines += ["", "## Notes", ""]
    for x in notes:
        where = f" ({_md(x['where'], 200)})" if x.get("where") else ""
        on = f" {_md(x['id'], 80)}" if x.get("id") else " page"
        lines.append(f"- {x['stage']} {x['n']}{on}: {_md(x['text'], NOTE_LIMIT)}{where}")
    if not notes:
        lines.append("No notes yet.")
    return "\n".join(lines) + "\n"


def write_project_taste(run, project_dir: Path | None) -> Path:
    """Write the head of taste.md, keeping every `## Refine pass` section already there."""
    run = _run(run)
    if project_dir:
        run.write("project.json", {"dir": str(Path(project_dir).resolve())})
    dest = _dest(run, project_dir)
    out = dest / "taste.md"
    old = out.read_text(encoding="utf-8") if out.is_file() else ""
    m = _REFINE.search(old)
    tail = old[m.start():] if m else ""
    dest.mkdir(parents=True, exist_ok=True)
    out.write_text(_head(run, project_dir) + ("\n" + tail if tail else ""), encoding="utf-8")
    return out


def apply_review(run, n: int, profile_path: Path) -> dict:
    """Add the ticked proposals of review pass `n` and this project's line to the general profile."""
    run = _run(run)
    r = rounds.load(run, "review", n)
    if r.at is None:
        raise ValueError(f"ingest review pass {n} first (taste round ingest)")
    if not run.has(snapshot_name(n)):
        raise ValueError(f"no {snapshot_name(n)}: render the review page again (taste round render RUN review)")
    shown = set(r.shown)
    proposals = [p for p in run.read(snapshot_name(n)) if p["id"] in shown]
    project_dir = _project_dir(run)
    d = _picked(run, project_dir)
    name = d["name"] if d else "no direction picked yet"
    wanted: dict[str, list[str]] = {s: [] for s in SECTIONS}
    for p in proposals:
        if (s := r.items.get(p["id"])) and s.vote == "pick" and p.get("section") in PROPOSAL_SECTIONS:
            wanted[p["section"]].append(_md(p["text"]))
    wanted["Projects"].append(f"{date.today().isoformat()} {_md(_slug(run, project_dir), 80)}: {_md(name, 80)}")
    path = Path(profile_path)
    old = path.read_text(encoding="utf-8") if path.is_file() else "# Taste profile\n"
    new, added = _append(old, wanted)
    if new != old or not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new, encoding="utf-8")
    return {"added": added, "skipped": [p["id"] for p in proposals if not ((s := r.items.get(p["id"])) and s.vote == "pick")],
            "path": str(profile_path)}
