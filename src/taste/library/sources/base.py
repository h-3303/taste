from pathlib import Path
from typing import Iterator, Protocol, runtime_checkable

from ..models import CollectionDraft, ItemDraft, PluckResult, SourceInfo

REGISTRY: dict[str, "Adapter"] = {}


@runtime_checkable
class Adapter(Protocol):
    info: SourceInfo

    def collections(self, fetch) -> Iterator[tuple[CollectionDraft, list[ItemDraft]]]: ...


def register(adapter):
    REGISTRY[adapter.info.slug] = adapter
    return adapter


def get(slug: str):
    try:
        return REGISTRY[slug]
    except KeyError:
        raise KeyError(f"unknown source {slug!r}; known: {', '.join(sorted(REGISTRY))}") from None


def all_adapters() -> list:
    return [REGISTRY[k] for k in sorted(REGISTRY)]


def has_pluck(adapter) -> bool:
    return callable(getattr(adapter, "pluck", None))


def has_font_file(adapter) -> bool:
    return callable(getattr(adapter, "font_file", None))
