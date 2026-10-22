from pathlib import Path

from ..models import CollectionDraft, ItemDraft, PluckResult, SourceInfo
from ..vocabulary import slugify
from .base import register

ASSETS = "https://api.polyhaven.com/assets?type=textures"
CATS = "https://api.polyhaven.com/categories/textures"
FILES = "https://api.polyhaven.com/files/{id}"
THUMB = "https://cdn.polyhaven.com/asset_img/thumbs/{id}.png?width=400"
MAPS = {"diffuse": "Diffuse", "normal": "nor_gl", "rough": "Rough", "ao": "AO", "displacement": "Displacement", "arm": "arm"}


def _item(aid: str, a: dict) -> ItemDraft:
    return ItemDraft(
        key=f"polyhaven:{aid}", kind="texture", title=a.get("name") or aid,
        page_url=f"https://polyhaven.com/a/{aid}", asset_url=FILES.format(id=aid), thumb_url=THUMB.format(id=aid),
        tags=list(dict.fromkeys([*a.get("tags", []), *a.get("categories", [])])),
        meta={"authors": list((a.get("authors") or {}).keys()), "max_resolution": a.get("max_resolution"),
              "description": (a.get("description") or "")[:300], "category_path": a.get("category", ""),
              "download_count": a.get("download_count", 0)},
        license="CC0")


class PolyHavenAdapter:
    info = SourceInfo("polyhaven", "Poly Haven", "https://polyhaven.com/textures", 1,
                      notes="CC0 PBR textures; open JSON API; pluck fetches one map at one resolution")

    def collections(self, fetch):
        assets = fetch.get_json(ASSETS)
        cats = fetch.get_json(CATS)
        for cat, n in sorted(cats.items(), key=lambda kv: -kv[1]):
            if cat == "all":
                continue
            items = [_item(aid, a) for aid, a in assets.items() if cat in a.get("categories", [])]
            items.sort(key=lambda i: -i.meta.get("download_count", 0))
            if items:
                yield CollectionDraft(f"polyhaven/{slugify(cat)}", "texture", f"Poly Haven: {cat}", query=cat), items

    def pluck(self, item: dict, fetch, dest_dir: Path, opts: dict) -> PluckResult:
        aid = item["key"].split(":", 1)[1]
        files = fetch.get_json(FILES.format(id=aid))
        map_key = MAPS.get((opts.get("map") or "diffuse").lower(), opts.get("map"))
        res = (opts.get("res") or "2k").lower()
        try:
            entry = files[map_key][res]
        except KeyError:
            raise ValueError(f"{aid}: no map {map_key!r} at {res}; maps: {', '.join(files)}") from None
        fmt = "jpg" if "jpg" in entry else next(iter(entry))
        url = entry[fmt]["url"]
        path = fetch.download(url, Path(dest_dir) / url.rsplit("/", 1)[-1])
        return PluckResult(item["id"], path, "", f"Poly Haven {aid} {map_key} {res} (CC0): {item.get('page_url', '')}")


ADAPTER = register(PolyHavenAdapter())
