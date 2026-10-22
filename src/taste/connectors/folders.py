import re
from pathlib import Path
from urllib.parse import urlparse

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

_WIKI_EMBED = re.compile(r"!\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")
_MD_EMBED = re.compile(r"!\[[^\]]*\]\(([^)\s]+)[^)]*\)")
_URL = re.compile(r"https?://[^\s)\]>\"'<]+")
_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.M)


def item(path=None, url=None, title="", source_url="", note="") -> dict:
    return {"path": path, "url": url, "title": title, "source_url": source_url, "note": note}


def is_image_url(url: str) -> bool:
    return Path(urlparse(url).path).suffix.lower() in IMAGE_SUFFIXES


class FolderImages:
    name = "folder-images"

    def __init__(self, path: Path):
        self.path = Path(path)

    def items(self) -> list[dict]:
        return [item(path=str(p), title=p.stem, note=self.name)
                for p in sorted(self.path.rglob("*")) if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES]


class FolderNotes:
    name = "folder-notes"

    def __init__(self, path: Path):
        self.path = Path(path)

    def _resolve(self, ref: str, note: Path) -> Path | None:
        for cand in (note.parent / ref, self.path / ref):
            if cand.is_file():
                return cand
        found = sorted(self.path.rglob(Path(ref).name))
        return found[0] if found else None

    def items(self) -> list[dict]:
        out = []
        for note in sorted(self.path.rglob("*.md")):
            text = note.read_text(encoding="utf-8", errors="replace")
            h = _HEADING.search(text)
            title = h.group(1) if h else note.stem
            seen: set[str] = set()

            def add_url(u):
                if u not in seen:
                    seen.add(u)
                    out.append(item(url=u, title=title, source_url=u, note=note.stem))

            for ref in [*_WIKI_EMBED.findall(text), *_MD_EMBED.findall(text)]:
                if ref.startswith(("http://", "https://")):
                    add_url(ref)
                elif Path(ref).suffix.lower() in IMAGE_SUFFIXES and (p := self._resolve(ref, note)):
                    out.append(item(path=str(p), title=title, note=note.stem))
            for u in _URL.findall(_MD_EMBED.sub("", text)):
                add_url(u.rstrip(".,;"))
        return out
