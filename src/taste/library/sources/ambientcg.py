from pathlib import Path

from ..models import CollectionDraft, ItemDraft, PluckResult, SourceInfo
from ..vocabulary import slugify
from .base import register

API = "https://ambientcg.com/api/v2/full_json"
TYPES = ("Material", "Decal")


def _item(a: dict) -> ItemDraft:
    zips = {}
    for folder in (a.get("downloadFolders") or {}).values():
        for cat in (folder.get("downloadFiletypeCategories") or {}).values():
            for d in cat.get("downloads", []):
                zips[d["attribute"]] = d["downloadLink"]
    prev = a.get("previewImage") or {}
    return ItemDraft(
        key=f"ambientcg:{a['assetId']}", kind="texture", title=a.get("displayName") or a["assetId"],
        page_url=f"https://ambientcg.com/view?id={a['assetId']}", asset_url=zips.get("2K-JPG") or next(iter(zips.values()), ""),
        thumb_url=prev.get("512-PNG") or prev.get("256-PNG"),
        tags=[t for t in a.get("tags", []) if not t.isdigit()],
        meta={"category": a.get("displayCategory"), "type": a.get("dataType"), "method": a.get("creationMethodName"),
              "zips": zips, "popularity": a.get("popularityScore", 0)},
        license="CC0")


class AmbientCGAdapter:
    info = SourceInfo("ambientcg", "ambientCG", "https://ambientcg.com", 1, notes="CC0 PBR materials and decals; open API")

    def _all(self, fetch, typ: str):
        offset = 0
        while True:
            page = fetch.get_json(API, {"type": typ, "limit": 250, "offset": offset, "include": "downloadData,imageData,tagData"})
            found = page.get("foundAssets") or []
            yield from found
            if not page.get("nextPageHttp") or not found:
                return
            offset += len(found)

    def collections(self, fetch):
        groups: dict[str, list[ItemDraft]] = {}
        for typ in TYPES:
            for a in self._all(fetch, typ):
                cat = a.get("displayCategory") or typ
                groups.setdefault(cat, []).append(_item(a))
        for cat, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            items.sort(key=lambda i: -i.meta.get("popularity", 0))
            yield CollectionDraft(f"ambientcg/{slugify(cat)}", "texture", f"ambientCG: {cat}", query=cat), items

    def pluck(self, item: dict, fetch, dest_dir: Path, opts: dict) -> PluckResult:
        zips = item.get("meta", {}).get("zips") or {}
        want = f"{(opts.get('res') or '2K').upper()}-JPG"
        url = zips.get(want) or next(iter(zips.values()), None)
        if not url:
            raise ValueError(f"{item['key']}: no downloads recorded")
        name = url.split("file=")[-1] if "file=" in url else url.rsplit("/", 1)[-1]
        path = fetch.download(url, Path(dest_dir) / name)
        return PluckResult(item["id"], path, "", f"ambientCG {name} (CC0): {item.get('page_url', '')}")


ADAPTER = register(AmbientCGAdapter())
