from pathlib import Path
from urllib.parse import quote

from ..models import CollectionDraft, ItemDraft, PluckResult, SourceInfo
from .base import register

SEARCH = "https://archive.org/advancedsearch.php"
META = "https://archive.org/metadata/{id}"
MAX_BYTES = 15_000_000
QUERIES = [("archive/rave-zines", "Internet Archive: Rave Zines", "collection:ravezines"),
           ("archive/david-rumsey", "Internet Archive: David Rumsey maps", "collection:david-rumsey-map-collection AND mediatype:image")]


def _is_jpeg(f: dict) -> bool:
    # Many items (e.g. the rave zines) carry no format "JPEG" file, only the "Item Tile" __ia_thumb.jpg.
    return f.get("format") == "JPEG" or str(f.get("name", "")).lower().endswith((".jpg", ".jpeg"))


def pick_image(identifier: str, files: list[dict]) -> str | None:
    jpegs = [f for f in files if _is_jpeg(f) and int(f.get("size") or 0) <= MAX_BYTES]
    if not jpegs:
        return None
    best = max(jpegs, key=lambda f: int(f.get("size") or 0))
    return f"https://archive.org/download/{identifier}/{quote(best['name'])}"


class ArchiveAdapter:
    info = SourceInfo("archive", "Internet Archive (opt-in collections)", "https://archive.org", 1, policy="manual",
                      notes="run only when named: dlib sync archive")

    def collections(self, fetch):
        for slug, title, q in QUERIES:
            docs = fetch.get_json(SEARCH, {"q": q, "fl[]": "identifier,title", "rows": 100, "output": "json"})["response"]["docs"]
            items = [ItemDraft(key=f"archive:{d['identifier']}", kind="image", title=str(d.get("title") or d["identifier"]),
                               page_url=f"https://archive.org/details/{d['identifier']}", asset_url=META.format(id=d["identifier"]),
                               thumb_url=f"https://archive.org/services/img/{d['identifier']}", tags=[slug.split('/')[1]],
                               meta={"identifier": d["identifier"]}, license="see item page") for d in docs]
            yield CollectionDraft(slug, "image", title, query=q, policy="manual"), items

    def pluck(self, item: dict, fetch, dest_dir: Path, opts: dict) -> PluckResult:
        ident = item["key"].split(":", 1)[1]
        url = pick_image(ident, fetch.get_json(META.format(id=ident)).get("files", []))
        if not url:
            raise ValueError(f"{ident}: no usable JPEG")
        return PluckResult(item["id"], fetch.download(url, Path(dest_dir) / f"archive-{ident}.jpg"), "", item.get("page_url", ""))


ADAPTER = register(ArchiveAdapter())
