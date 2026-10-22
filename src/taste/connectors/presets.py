from pathlib import Path

import yaml

from .folders import IMAGE_SUFFIXES, item


def _split(text: str):
    if not text.startswith("---\n"):
        return None, text
    end = text.find("\n---", 4)
    if end == -1:
        return None, text
    try:
        meta = yaml.safe_load(text[4:end])
    except yaml.YAMLError:
        return None, text
    body = text[end + 4:].lstrip("-").lstrip("\n")
    return (meta if isinstance(meta, dict) else None), body


def _str(v) -> str:
    return "" if v is None else str(v)


def parse_note(path: Path) -> dict | None:
    meta, body = _split(Path(path).read_text(encoding="utf-8", errors="replace"))
    if not meta or meta.get("type") != "resource":
        return None
    tags = meta.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    first = body.strip().split("\n\n", 1)[0].strip()
    summary = "" if first.startswith("#") else first[:300]
    return {
        "note": Path(path).stem,
        "title": _str(meta.get("title")) or Path(path).stem,
        "url": _str(meta.get("url")),
        "category": _str(meta.get("category")),
        "filed_under": _str(meta.get("filed_under")).strip("[]"),
        "tags": [str(t) for t in tags],
        "resource_type": _str(meta.get("resource_type")),
        "url_status": _str(meta.get("url_status")),
        "summary": summary,
    }


class ObsidianResources:
    """Resource notes (`type: resource`) under `<path>/Resources` of an Obsidian vault."""
    name = "obsidian-resources"

    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self) -> list[dict]:
        res = self.path / "Resources"
        notes = [r for p in sorted(res.glob("*.md")) if (r := parse_note(p))] if res.is_dir() else []
        return sorted(notes, key=lambda r: r["note"])

    def items(self) -> list[dict]:
        return [item(url=r["url"], title=r["title"], source_url=r["url"], note=r["note"]) for r in self.load()]


class InstagramMedia:
    """Saved Instagram media at `<path>/<creator>/<code>_N.jpg`."""
    name = "instagram-media"

    def __init__(self, path: Path):
        self.path = Path(path)

    def _item(self, p: Path, code: str) -> dict:
        return item(path=str(p), title=f"@{p.parent.name} {code}",
                    source_url=f"https://www.instagram.com/p/{code}/", note=f"ig-{code}")

    def items(self) -> list[dict]:
        return [self._item(p, p.stem.rsplit("_", 1)[0]) for p in sorted(self.path.glob("*/*_*"))
                if p.suffix.lower() in IMAGE_SUFFIXES]

    def for_codes(self, codes: list[str]) -> list[dict]:
        return [self._item(p, code) for code in codes for p in sorted(self.path.glob(f"*/{code}_*"))
                if p.suffix.lower() in IMAGE_SUFFIXES]
