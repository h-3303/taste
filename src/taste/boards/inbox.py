import json
import shutil
from pathlib import Path

from .models import Candidate
from taste.connectors.folders import IMAGE_SUFFIXES


def is_style(name: str) -> bool:
    """Style ids are "1", "2", ... (any count of directions)."""
    return name.isascii() and name.isdigit() and not name.startswith("0")


def _sources(folder: Path) -> dict[str, tuple[str, str, str]]:
    """sources.txt: filename<TAB>source url[<TAB>source note[<TAB>title]] per line."""
    f = folder / "sources.txt"
    if not f.exists():
        return {}
    out = {}
    for line in f.read_text(encoding="utf-8").splitlines():
        parts = [x.strip() for x in line.split("\t")]
        if len(parts) >= 2:
            note = parts[2] if len(parts) > 2 and parts[2] else "inbox"
            out[parts[0]] = (parts[1], note, parts[3] if len(parts) > 3 else "")
    return out


def _free(dest: Path, name: str) -> Path:
    target, n = dest / f"inbox-{name}", 1
    while target.exists():
        n += 1
        target = dest / f"inbox-{Path(name).stem}-{n}{Path(name).suffix}"
    return target


def _take(folder: Path, style: str | None, dest: Path, known: dict) -> None:
    sources = _sources(folder)
    for p in sorted(folder.iterdir()):
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES:
            target = _free(dest, p.name)
            shutil.move(p, target)
            url, note, title = sources.get(p.name, ("", "inbox", ""))
            known[target.name] = {"url": url, "note": note, "style": style, "title": title}
    (folder / "sources.txt").unlink(missing_ok=True)


def take_inbox(inbox: Path, dest: Path) -> list[Candidate]:
    """Move new inbox images into dest, then return every inbox image dest holds (earlier gathers too).

    Images in inbox/1, inbox/2, ... are tagged with that style; loose ones in inbox/ are untagged.
    """
    inbox, dest = Path(inbox), Path(dest)
    store = dest / "inbox-sources.json"
    known = json.loads(store.read_text(encoding="utf-8")) if store.exists() else {}
    known = {k: v if isinstance(v, dict) else {"url": v, "note": "inbox", "style": None} for k, v in known.items()}
    if inbox.is_dir():
        dest.mkdir(parents=True, exist_ok=True)
        _take(inbox, None, dest, known)
        for sub in sorted(inbox.iterdir(), key=lambda p: (len(p.name), p.name)):
            if sub.is_dir() and is_style(sub.name):
                _take(sub, sub.name, dest, known)
        store.write_text(json.dumps(known, indent=2, ensure_ascii=False), encoding="utf-8")
    out = []
    for p in sorted(dest.glob("inbox-*")):
        if p.suffix.lower() in IMAGE_SUFFIXES:
            k = known.get(p.name, {"url": "", "note": "inbox", "style": None})
            title = k.get("title") or p.stem.removeprefix("inbox-")
            out.append(Candidate("inbox", p, k["url"], k["note"], title, k["style"]))
    return out
