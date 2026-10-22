import re

from ..models import CollectionDraft, ItemDraft, SourceInfo
from .base import register

LOAD = "https://lospec.com/palette-list/load"
COUNTS = (2, 3, 4, 5, 6, 8, 12, 16, 24, 32, 48, 64)
PAGES = 10
TAG_RE = re.compile(r"<[^>]+>")


def _clean(text: str) -> str:
    return " ".join(TAG_RE.sub("", text or "").split())


def _item(p: dict) -> ItemDraft:
    colors = ["#" + c.lower() for c in p.get("colors", [])]
    return ItemDraft(
        key=f"lospec:{p['slug']}", kind="palette", title=p.get("title") or p["slug"],
        page_url=f"https://lospec.com/palette-list/{p['slug']}", asset_url=f"https://lospec.com/palette-list/{p['slug']}.hex",
        thumb_url=None, tags=[t for t in p.get("tags", []) if isinstance(t, str)],
        meta={"colors": colors, "count": len(colors), "author": _clean((p.get("user") or {}).get("name", ""))[:120],
              "description": _clean(p.get("description"))[:300]},
        license="see palette page")


class LospecAdapter:
    info = SourceInfo("lospec", "Lospec palettes", "https://lospec.com/palette-list", 1, notes="pixel-art palettes; open JSON")

    def collections(self, fetch):
        for n in COUNTS:
            items = []
            for page in range(PAGES):
                data = fetch.get_json(LOAD, {"colorNumberFilterType": "exact", "colorNumber": n, "page": page, "tag": "", "sortingType": "default"})
                pals = data.get("palettes") or []
                items += [_item(p) for p in pals if p.get("slug")]
                if not pals:
                    break
            if items:
                yield CollectionDraft(f"lospec/{n}-colours", "palette", f"Lospec: {n}-colour palettes", query=str(n)), items


ADAPTER = register(LospecAdapter())
