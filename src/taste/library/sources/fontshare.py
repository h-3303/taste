import re
from pathlib import Path

from ..models import CollectionDraft, ItemDraft, PluckResult, SourceInfo
from ..vocabulary import slugify
from .base import register

API = "https://api.fontshare.com/v2/fonts"
CSS = "https://api.fontshare.com/v2/css?f[]={slug}@400"
TTF_RE = re.compile(r"url\('(//cdn\.fontshare\.com/[^']+\.ttf)'\)")


def _item(f: dict) -> ItemDraft:
    slug = f["slug"]
    return ItemDraft(
        key=f"fontshare:{slug}", kind="font", title=f.get("name") or slug, page_url=f"https://www.fontshare.com/fonts/{slug}",
        asset_url=CSS.format(slug=slug), thumb_url=None,
        tags=[f.get("category", "").lower(), *[t.get("name", "").lower() for t in f.get("font_tags", []) if isinstance(t, dict)]],
        meta={"category": f.get("category"), "styles": len(f.get("styles") or []), "axes": [a.get("tag") for a in (f.get("axes") or []) if isinstance(a, dict)],
              "license": f.get("license_type"), "views": f.get("views", 0),
              "css": f'<link href="{CSS.format(slug=slug)}&display=swap" rel="stylesheet">'},
        license="Fontshare Free Font License (ITF FFL)")


class FontshareAdapter:
    info = SourceInfo("fontshare", "Fontshare", "https://www.fontshare.com", 1, notes="Indian Type Foundry free fonts; open JSON API")

    def collections(self, fetch):
        offset, fonts = 0, []
        while True:
            page = fetch.get_json(API, {"limit": 100, "offset": offset})
            fonts += page.get("fonts", [])
            if not page.get("has_more"):
                break
            offset += 100
        groups: dict[str, list[ItemDraft]] = {}
        for f in fonts:
            groups.setdefault(f.get("category") or "Other", []).append(_item(f))
        for cat, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            items.sort(key=lambda i: -i.meta.get("views", 0))
            yield CollectionDraft(f"fontshare/{slugify(cat)}", "font", f"Fontshare: {cat}", query=cat), items

    def font_file(self, item: dict, fetch, dest_dir: Path) -> Path:
        slug = item["key"].split(":", 1)[1]
        m = TTF_RE.search(fetch.get_text(CSS.format(slug=slug)))
        if not m:
            raise ValueError(f"{slug}: no ttf in css")
        return fetch.download("https:" + m.group(1), Path(dest_dir) / f"{slug}-400.ttf")

    def pluck(self, item: dict, fetch, dest_dir: Path, opts: dict) -> PluckResult:
        slug = item["key"].split(":", 1)[1]
        path = self.font_file(item, fetch, dest_dir)
        text = f'<link href="{CSS.format(slug=slug)}&display=swap" rel="stylesheet">\nfont-family: "{item["title"]}";'
        return PluckResult(item["id"], path, text, f"Fontshare {slug} (ITF FFL): {item.get('page_url', '')}")


ADAPTER = register(FontshareAdapter())
