from dataclasses import dataclass
from pathlib import Path


@dataclass
class Candidate:
    """One image file gathered from a source, before normalisation."""
    kind: str          # "site" | "archive" | "vault" | "inbox" | "library"
    path: Path
    source_url: str
    source_note: str   # library note title, "ig-<code>", or "inbox"
    title: str
    style: str | None = None   # "1".."4": the design language it was gathered for
