from dataclasses import dataclass, field
from pathlib import Path

KINDS = ("image", "texture", "font", "palette", "site", "snippet", "icon")


@dataclass
class SourceInfo:
    slug: str
    title: str
    home_url: str
    tier: int
    policy: str = "sync"       # sync | snapshot | manual
    notes: str = ""


@dataclass
class CollectionDraft:
    slug: str
    kind: str
    title: str
    query: str = ""
    languages: list[str] = field(default_factory=list)
    policy: str = "sync"
    error: str | None = None   # set when the adapter swallowed a fetch error into an empty or partial collection


@dataclass
class ItemDraft:
    key: str                   # stable per source, e.g. "polyhaven:aerial_asphalt_01"
    kind: str
    title: str
    page_url: str
    asset_url: str
    thumb_url: str | None = None
    tags: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    license: str = ""


@dataclass
class PluckResult:
    item_id: str
    path: Path | None
    text: str = ""
    note: str = ""
