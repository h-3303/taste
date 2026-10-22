"""Optional sources of images and references. All are off until `taste connect <name> --path P`."""
import sys
from pathlib import Path
from typing import Protocol

from .. import config
from .folders import FolderImages, FolderNotes
from .presets import InstagramMedia, ObsidianResources


class Connector(Protocol):
    name: str

    def items(self) -> list[dict]:
        """Dicts {"path": str | None, "url": str | None, "title", "source_url", "note"}."""


REGISTRY = {"folder-images": FolderImages, "folder-notes": FolderNotes,
            "obsidian-resources": ObsidianResources, "instagram-media": InstagramMedia}


def enabled() -> list[Connector]:
    out = []
    for name, cls in REGISTRY.items():
        c = config.connector(name)
        if not c:
            continue
        path = c.get("path")
        if not path or not Path(path).expanduser().is_dir():
            print(f"warning: connector {name}: path {path or '(none set)'} not found, skipped", file=sys.stderr)
            continue
        out.append(cls(Path(path).expanduser()))
    return out
