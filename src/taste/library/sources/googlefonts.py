import re
from pathlib import Path

from ..models import CollectionDraft, ItemDraft, PluckResult, SourceInfo
from ..vocabulary import slugify
from .base import register

META = "https://fonts.google.com/metadata/fonts"
CSS1 = "https://fonts.googleapis.com/css?family={fam}:{w}"
CSS2 = "https://fonts.googleapis.com/css2?family={fam}:wght@{w}&display=swap"
TTF_RE = re.compile(r"url\((https://fonts\.gstatic\.com/[^)]+\.ttf)\)")
CURL_UA = {"User-Agent": "curl/8"}   # the v1 css endpoint serves TTF urls to a non-browser UA


def _plus(family: str) -> str:
    return family.replace(" ", "+")


def _item(f: dict) -> ItemDraft:
    fam = f["family"]
    weights = sorted({k.rstrip("i") for k in (f.get("fonts") or {})}, key=lambda w: int(w) if w.isdigit() else 0)
    axes = [a.get("tag") for a in f.get("axes", []) if isinstance(a, dict)]
    return ItemDraft(
        key=f"googlefonts:{fam}", kind="font", title=fam, page_url=f"https://fonts.google.com/specimen/{_plus(fam)}",
        asset_url=CSS2.format(fam=_plus(fam), w="400"), thumb_url=None,
        tags=[f.get("category", "").lower(), *[d for d in f.get("designers", [])], *(["variable"] if axes else [])],
        meta={"category": f.get("category"), "weights": weights, "axes": axes, "designers": f.get("designers", []),
              "popularity": f.get("popularity", 10**6), "date_added": f.get("dateAdded"),
              "css": f'<link href="{CSS2.format(fam=_plus(fam), w="400")}" rel="stylesheet">'},
        license="OFL-1.1 (see specimen page)")


class GoogleFontsAdapter:
    info = SourceInfo("googlefonts", "Google Fonts", "https://fonts.google.com", 1, notes="metadata JSON; specimens rendered lazily")

    def collections(self, fetch):
        fams = fetch.get_json(META)["familyMetadataList"]
        items = [_item(f) for f in fams]
        by_pop = sorted(items, key=lambda i: i.meta["popularity"])
        yield CollectionDraft("googlefonts/popular-100", "font", "Google Fonts: 100 most popular"), by_pop[:100]
        for cat in ("Sans Serif", "Serif", "Display", "Handwriting", "Monospace"):
            cat_items = [i for i in by_pop if i.meta["category"] == cat]
            if cat_items:
                yield CollectionDraft(f"googlefonts/{slugify(cat)}", "font", f"Google Fonts: {cat}", query=cat), cat_items
        yield CollectionDraft("googlefonts/variable", "font", "Google Fonts: variable fonts"), [i for i in by_pop if i.meta["axes"]]

    def font_file(self, item: dict, fetch, dest_dir: Path) -> Path:
        fam = item["key"].split(":", 1)[1]
        css = fetch.get_text(CSS1.format(fam=_plus(fam), w="400"), headers=CURL_UA)
        m = TTF_RE.search(css)
        if not m:
            raise ValueError(f"{fam}: no TTF url in css")
        return fetch.download(m.group(1), Path(dest_dir) / f"{slugify(fam)}-400.ttf")

    def pluck(self, item: dict, fetch, dest_dir: Path, opts: dict) -> PluckResult:
        fam = item["key"].split(":", 1)[1]
        w = str(opts.get("weight") or 400)
        css = fetch.get_text(CSS1.format(fam=_plus(fam), w=w), headers=CURL_UA)
        m = TTF_RE.search(css)
        path = fetch.download(m.group(1), Path(dest_dir) / f"{slugify(fam)}-{w}.ttf") if m else None
        text = (f'<link href="{CSS2.format(fam=_plus(fam), w=w)}" rel="stylesheet">\n'
                f'@import url("{CSS2.format(fam=_plus(fam), w=w)}");\n'
                f'font-family: "{fam}", {"serif" if item.get("meta", {}).get("category") == "Serif" else "sans-serif"};')
        return PluckResult(item["id"], path, text, f"Google Fonts {fam} weight {w}: {item.get('page_url', '')}")


ADAPTER = register(GoogleFontsAdapter())
