from pathlib import Path

import yaml


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


def load_library(vault: Path) -> list[dict]:
    res = Path(vault) / "Resources"
    notes = [r for p in sorted(res.glob("*.md")) if (r := parse_note(p))] if res.is_dir() else []
    if not notes:
        raise FileNotFoundError(f"no resource notes under {res}")
    return sorted(notes, key=lambda r: r["note"])
