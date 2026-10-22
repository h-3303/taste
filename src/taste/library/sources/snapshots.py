import re
from urllib.parse import quote

from ..models import CollectionDraft, ItemDraft, SourceInfo
from ..vocabulary import TERMS, term_slug
from .base import register
from .html import unique

IMG = re.compile(r'<img[^>]*src="(https://[^"]+\.(?:jpg|jpeg|png|webp)(?:\?[^"]*)?)"')
PEN = re.compile(r'href="/([A-Za-z0-9_-]+)/pen/([A-Za-z0-9]+)"')
SKIP = ("avatar", "logo", "icon", "badge", "emoji")
CAP = 60
N_TERMS = 10


def parse_images(html: str) -> list[str]:
    return [u for u in unique(IMG.findall(html)) if not any(s in u.lower() for s in SKIP)][:CAP]


class SnapshotAdapter:
    def __init__(self, slug: str, title: str, home: str, url_fn, kind: str = "image"):
        self.info = SourceInfo(slug, title, home, 3, policy="snapshot", notes="bot-protected; one-off snapshot with --snapshot")
        self.url_fn, self.kind = url_fn, kind

    def _items(self, html: str, term: str, page: str) -> list[ItemDraft]:
        slug = self.info.slug
        if slug == "codepen":
            return [ItemDraft(key=f"codepen:{u}/{pid}", kind="snippet", title=f"CodePen {u}/{pid} · {term}", page_url=f"https://codepen.io/{u}/pen/{pid}",
                              asset_url=f"https://codepen.io/{u}/pen/{pid}.html", thumb_url=f"https://shots.codepen.io/{u}/pen/{pid}-512.jpg",
                              tags=[term, "codepen"], meta={"term": term, "user": u, "pen": pid}, license="see pen")
                    for u, pid in unique(PEN.findall(html))[:CAP]]
        return [ItemDraft(key=f"{slug}:{re.sub(r'[^A-Za-z0-9]', '', u)[-40:]}", kind=self.kind, title=f"{self.info.title} · {term}", page_url=page,
                          asset_url=u, thumb_url=u, tags=[term], meta={"term": term}, license="see source page")
                for u in parse_images(html)]

    def collections(self, fetch):
        for term in TERMS[:N_TERMS]:
            page = self.url_fn(term)
            html = fetch.render(page, wait=8, stealth=True, obey_robots=False)
            yield CollectionDraft(f"{self.info.slug}/{term_slug(term)}", self.kind, f"{self.info.title}: {term}", query=term,
                                  languages=[term], policy="snapshot"), self._items(html, term, page)


PIN_SIZE = re.compile(r"/(\d+x\d*(?:_RS)?)/")


class PinterestAdapter(SnapshotAdapter):
    """Pinterest's img src is a 75 px preview; the full asset is the same path at /736x/."""

    def _items(self, html: str, term: str, page: str) -> list[ItemDraft]:
        items = super()._items(html, term, page)
        for it in items:
            it.asset_url = PIN_SIZE.sub("/736x/", it.thumb_url, count=1) if "pinimg.com" in it.thumb_url else it.asset_url
        return items


BEHANCE = register(SnapshotAdapter("behance", "Behance", "https://www.behance.net", lambda t: f"https://www.behance.net/search/projects?search={quote(t)}"))
DRIBBBLE = register(SnapshotAdapter("dribbble", "Dribbble", "https://dribbble.com", lambda t: f"https://dribbble.com/search/{quote(t)}"))
PINTEREST = register(PinterestAdapter("pinterest", "Pinterest", "https://www.pinterest.com", lambda t: f"https://www.pinterest.com/search/pins/?q={quote(t)}"))
CODEPEN = register(SnapshotAdapter("codepen", "CodePen", "https://codepen.io", lambda t: f"https://codepen.io/search/pens?q={quote(t)}", kind="snippet"))
