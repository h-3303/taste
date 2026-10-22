import json
import re
import shutil
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


def md_line(text, limit: int = 300) -> str:
    """One escaped markdown line: links escaped by clean_text, inline HTML neutralised."""
    return clean_text(text, limit=limit).replace("<", "&lt;")


def fresh_out(out_dir) -> Path:
    """Make out_dir ready for a render: an empty or new folder, or one holding an earlier render (its files.json),
    whose index.html, img/ and files.json are cleared. Anything else is the person's and is refused."""
    out_dir = Path(out_dir)
    if out_dir.exists():
        if not out_dir.is_dir():
            raise ValueError(f"--out {out_dir} is a file, not a folder")
        if any(out_dir.iterdir()) and not (out_dir / "files.json").is_file():
            raise ValueError(f"--out {out_dir} is not empty and holds no earlier render (no files.json); "
                             "give an empty or new folder")
    shutil.rmtree(out_dir / "img", ignore_errors=True)
    for name in ("index.html", "files.json"):
        (out_dir / name).unlink(missing_ok=True)
    (out_dir / "img").mkdir(parents=True)
    return out_dir


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
