import json
import re
import unicodedata
from datetime import date as Date
from pathlib import Path

from .. import paths


def data_root() -> Path:
    return paths.data_root()


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "untitled"


def clean_text(text, limit: int = 120, markdown: bool = True) -> str:
    """One line of untrusted text: whitespace collapsed, cut to `limit` chars, markdown link syntax escaped."""
    text = " ".join(str(text or "").split())
    if len(text) > limit:
        text = text[:limit - 1] + "…"
    return re.sub(r"([\\\[\]()])", r"\\\1", text) if markdown else text


class Run:
    def __init__(self, path):
        self.path = Path(path)
        self.raw = self.path / "raw"
        self.images = self.path / "images"

    @classmethod
    def create(cls, slug: str, date: Date | None = None, root: Path | None = None) -> "Run":
        root = Path(root) if root else data_root()
        day = (date or Date.today()).isoformat()
        run = cls(root / "runs" / f"{day}-{slugify(slug)}")
        run.raw.mkdir(parents=True, exist_ok=True)
        run.images.mkdir(parents=True, exist_ok=True)
        return run

    def has(self, name: str) -> bool:
        return (self.path / name).exists()

    def read(self, name: str):
        return json.loads((self.path / name).read_text(encoding="utf-8"))

    def write(self, name: str, data) -> Path:
        p = self.path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return p
