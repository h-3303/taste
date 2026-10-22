from pathlib import Path

from ..models import CollectionDraft, ItemDraft, PluckResult, SourceInfo
from .base import register

API = "https://api.fontsource.org/v1/fonts?category={cat}"
CDN = "https://cdn.jsdelivr.net/fontsource/fonts/{id}@latest/latin-400-normal.{ext}"
CATS = ("sans-serif", "serif", "display", "handwriting", "monospace")


def _item(f: dict) -> ItemDraft:
    fid = f["id"]
    return ItemDraft(
        key=f"fontsource:{fid}", kind="font", title=f.get("family") or fid, page_url=f"https://fontsource.org/fonts/{fid}",
        asset_url=CDN.format(id=fid, ext="woff2"), thumb_url=None,
        tags=[f.get("category", ""), f.get("type", ""), *(["variable"] if f.get("variable") else [])],
        meta={"category": f.get("category"), "weights": f.get("weights", []), "styles": f.get("styles", []),
              "variable": bool(f.get("variable")), "license": f.get("license"), "install": f"npm i @fontsource/{fid}",
              "css": f'import "@fontsource/{fid}/400.css";'},
        license=f.get("license") or "")


class FontsourceAdapter:
    info = SourceInfo("fontsource", "Fontsource", "https://fontsource.org", 1, notes="self-hostable open fonts as npm packages")

    def collections(self, fetch):
        for cat in CATS:
            items = [_item(f) for f in fetch.get_json(API.format(cat=cat))]
            if items:
                yield CollectionDraft(f"fontsource/{cat}", "font", f"Fontsource: {cat}", query=cat), items

    def font_file(self, item: dict, fetch, dest_dir: Path) -> Path:
        fid = item["key"].split(":", 1)[1]
        return fetch.download(CDN.format(id=fid, ext="woff"), Path(dest_dir) / f"{fid}-400.woff")

    def pluck(self, item: dict, fetch, dest_dir: Path, opts: dict) -> PluckResult:
        fid = item["key"].split(":", 1)[1]
        path = fetch.download(CDN.format(id=fid, ext="woff2"), Path(dest_dir) / f"{fid}-400.woff2")
        text = f"npm i @fontsource/{fid}\nimport \"@fontsource/{fid}/400.css\";\nfont-family: \"{item['title']}\";"
        return PluckResult(item["id"], path, text, f"Fontsource {fid} ({item.get('meta', {}).get('license', '')}): {item.get('page_url', '')}")


ADAPTER = register(FontsourceAdapter())
