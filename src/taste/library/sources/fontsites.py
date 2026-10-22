import html as _html
import re

from ..fetch import Blocked, FetchError
from ..models import CollectionDraft, ItemDraft, SourceInfo
from .base import register
from .html import og_image, title as page_title, unique

CO_LINK = re.compile(r'href="/typefaces/([a-z0-9-]+)"')
H1 = re.compile(r"<h1[^>]*>(.*?)</h1>", re.S)
TAG = re.compile(r"<[^>]+>")


def parse_collletttivo_list(page: str) -> list[str]:
    return unique(CO_LINK.findall(page))


def parse_collletttivo_page(page: str) -> dict:
    # <title> is "Borges Family · Collletttivo"; the <h1> is a section heading ("Clt Borges Family Overview").
    title = page_title(page).split("·")[0].strip()
    if not title:
        m = H1.search(page)
        title = _html.unescape(" ".join(TAG.sub("", m.group(1)).split())) if m else ""
    return {"title": title, "og_image": og_image(page)}


def _render(fetch, url, wait=6) -> tuple[str, str | None]:
    try:
        return fetch.render(url, wait=wait), None
    except Blocked:
        raise
    except FetchError as e:
        return "", str(e)


def _font_item(slug: str, page_url: str, d: dict) -> ItemDraft:
    img = d["og_image"]
    # No font file is linked from these pages: the specimen image is the asset.
    return ItemDraft(key=f"collletttivo:{slug}", kind="font", title=d.get("title") or slug.replace("-", " ").title(),
                     page_url=page_url, asset_url=img, thumb_url=img, tags=["open source"],
                     meta={"specimen": img, "asset_is_specimen": True}, license="OFL (see page)")


class CollletttivoAdapter:
    info = SourceInfo("collletttivo", "Collletttivo", "https://www.collletttivo.it", 2, notes="Italian open-source type collective; specimen is the og:image")

    def collections(self, fetch):
        html, error = _render(fetch, "https://www.collletttivo.it/typefaces", 8)
        slugs = parse_collletttivo_list(html)
        items = []
        for s in slugs:
            url = f"https://www.collletttivo.it/typefaces/{s}"
            html, err = _render(fetch, url, 6)
            error = error or err
            d = parse_collletttivo_page(html)
            if not d["og_image"]:      # failed or empty render: leave it out so the next sync retries
                continue
            items.append(_font_item(s, url, d))
        yield CollectionDraft("collletttivo/typefaces", "font", "Collletttivo typefaces", error=error), items


COLLLETTTIVO = register(CollletttivoAdapter())
