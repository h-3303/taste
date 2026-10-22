import hashlib
import re
from urllib.parse import quote

from ..fetch import Blocked, FetchError
from ..models import CollectionDraft, ItemDraft, SourceInfo
from ..vocabulary import TERMS, term_slug
from .base import register
from .html import unique

# Obscura's render of cosmos.so ends in Next's error shell (hydration fails), so there are no <img> tiles; the
# search results survive in the server-rendered RSC payload as media objects with a cdn url.
COSMOS_RE = re.compile(r'"media":\{[^{}]*?"url":"https://cdn\.cosmos\.so/([0-9a-f-]{36})"')
COSMOS_IMG_RE = re.compile(r'<img[^>]*data-testid="element-image-img"[^>]*src="https://cdn\.cosmos\.so/([^"?]+)')
DSP_RE = re.compile(r'https://dspncdn\.com/a1/media/\d+x/([0-9a-f]{2}/[0-9a-f]{2}/[0-9a-f]{2}/[0-9a-f]+\.(?:jpg|jpeg|png|gif))')
SAVEE_RE = re.compile(r'https://dm\.savee-cdn\.com/asset-image/w420/([0-9a-f]{24})\.jpg')


def parse_cosmos(html: str) -> list[str]:
    return unique([*COSMOS_IMG_RE.findall(html), *COSMOS_RE.findall(html)])


def parse_designspiration(html: str) -> list[str]:
    return unique(DSP_RE.findall(html))


def parse_savee(html: str) -> list[str]:
    return unique(SAVEE_RE.findall(html))


def term_collections(slug: str, title: str, fetch, page_url_fn, parse_fn, make_item_fn, wait: int):
    for term in TERMS:
        page = page_url_fn(term)
        error = None
        try:
            found = parse_fn(fetch.render(page, wait=wait))
        except Blocked:
            raise
        except FetchError as e:
            found, error = [], str(e)
        items = [make_item_fn(x, term, page) for x in found]
        yield CollectionDraft(f"{slug}/{term_slug(term)}", "image", f"{title}: {term}", query=term, languages=[term], error=error), items


class CosmosAdapter:
    info = SourceInfo("cosmos", "Cosmos", "https://www.cosmos.so", 2, notes="search pages rendered by Obscura; tiles at 1600 px")

    def collections(self, fetch):
        yield from term_collections(
            "cosmos", "Cosmos", fetch,
            lambda t: f"https://www.cosmos.so/search/elements/{quote(t)}", parse_cosmos,
            lambda cid, term, page: ItemDraft(
                key=f"cosmos:{cid}", kind="image", title=f"Cosmos · {term}", page_url=page,
                asset_url=f"https://cdn.cosmos.so/{cid}?format=jpeg&w=1600", thumb_url=f"https://cdn.cosmos.so/{cid}?format=jpeg&w=400",
                tags=[term], meta={"term": term}, license="see source page"),
            wait=8)


class DesignspirationAdapter:
    info = SourceInfo("designspiration", "Designspiration", "https://www.designspiration.com", 2, notes="largest public size is 692 px")

    def collections(self, fetch):
        yield from term_collections(
            "designspiration", "Designspiration", fetch,
            lambda t: f"https://www.designspiration.com/search/saves/?q={quote(t)}", parse_designspiration,
            lambda path, term, page: ItemDraft(
                key=f"designspiration:{hashlib.sha1(path.encode()).hexdigest()[:16]}", kind="image", title=f"Designspiration · {term}",
                page_url=page, asset_url=f"https://dspncdn.com/a1/media/692x/{path}", thumb_url=f"https://dspncdn.com/a1/media/236x/{path}",
                tags=[term], meta={"term": term}, license="see source page"),
            wait=6)


class SaveeAdapter:
    info = SourceInfo("savee", "Savee", "https://savee.it", 2, notes="only the 420 px size is public")

    def collections(self, fetch):
        yield from term_collections(
            "savee", "Savee", fetch,
            lambda t: f"https://savee.it/search/?q={quote(t)}", parse_savee,
            lambda sid, term, page: ItemDraft(
                key=f"savee:{sid}", kind="image", title=f"Savee · {term}", page_url=page,
                asset_url=f"https://dm.savee-cdn.com/asset-image/w420/{sid}.jpg", thumb_url=f"https://dm.savee-cdn.com/asset-image/w420/{sid}.jpg",
                tags=[term], meta={"term": term}, license="see source page"),
            wait=6)


COSMOS = register(CosmosAdapter())
DESIGNSPIRATION = register(DesignspirationAdapter())
SAVEE = register(SaveeAdapter())
