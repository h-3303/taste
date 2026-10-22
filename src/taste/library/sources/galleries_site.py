import html as _html
import re

from ..fetch import Blocked, FetchError
from ..models import CollectionDraft, ItemDraft, SourceInfo
from .base import register
from .html import unique

DARK_RE = re.compile(r'<a[^>]*href="(/site/([a-z0-9-]+?)(?:-\d+)?)"[^>]*>(?:(?!</a>).){0,600}?screenshots/(auto-[0-9]+\.webp)', re.S)
DARK_BASE = "https://sidhvpjhuucqcehkevrl.supabase.co/storage/v1"
SI_RE = re.compile(r'(?:<a[^>]*href="([^"]*)"[^>]*>(?:(?!</a>).)*?)?<img alt="([^"]+)"[^>]*class="WebsiteCard__image[^"]*"[^>]*src="(https://r2\.siteinspire\.com/cdn-cgi/image/[^"]+/([^/"]+))"', re.S)
GODLY_RE = re.compile(r'https://cdn\.recent\.design/items/([a-z0-9]+)/0/poster/1200\.webp')
LB_RE = re.compile(r'(https://cdn\.land-book\.com/image/[^"\s]*?/website/(\d+)/[^"\s]+)')
# Awwwards lazy-loads: the real image is in data-srcset ("<440 px url> 1x, <880 px url> 2x"), not data-src.
AW_RE = re.compile(r'<a[^>]*aria-label="([^"]*)"[^>]*class="figure-rollover__link"[^>]*href="/sites/([^"]+)"'
                   r'(?:(?!</figure>).){0,1500}?data-srcset="(https://assets\.awwwards\.com/awards/[^"\s]+) 1x(?:, (https://assets\.awwwards\.com/awards/[^"\s]+) 2x)?"', re.S)


def _sized(url: str, width: int) -> str:
    url = re.sub(r"width=\d+", f"width={width}", url)
    return re.sub(r"height=\d+", f"height={width * 5 // 8}", url)    # siteinspire crops 16:10; keep the ratio


def parse_dark(html: str) -> list[dict]:
    rows = []
    for path, slug, shot in DARK_RE.findall(html):
        rows.append({"id": slug, "title": slug.replace("-", " ").title(), "page_url": f"https://www.dark.design{path}",
                     "asset_url": f"{DARK_BASE}/object/public/screenshots/{shot}",
                     "thumb_url": f"{DARK_BASE}/render/image/public/screenshots/{shot}?width=640&quality=70"})
    return _dedupe(rows)


def parse_siteinspire(html: str) -> list[dict]:
    rows = []
    for href, alt, src, fname in SI_RE.findall(html):
        if href.startswith("http"):        # sponsor card linking off-site, not a gallery entry
            continue
        src = _html.unescape(src)
        rows.append({"id": fname.rsplit(".", 1)[0], "title": _html.unescape(alt),
                     "page_url": f"https://www.siteinspire.com{href}" if href else "https://www.siteinspire.com/websites",
                     "asset_url": _sized(src, 1920), "thumb_url": _sized(src, 384)})
    return _dedupe(rows)


def parse_godly(html: str) -> list[dict]:
    return [{"id": i, "title": f"Godly site {i}", "page_url": "https://godly.website/websites",
             "asset_url": f"https://cdn.recent.design/items/{i}/0/poster/1200.webp",
             "thumb_url": f"https://cdn.recent.design/items/{i}/0/poster/640.webp"} for i in unique(GODLY_RE.findall(html))]


def parse_landbook(html: str) -> list[dict]:
    rows = []
    for url, wid in LB_RE.findall(html):
        url = _html.unescape(url)
        rows.append({"id": wid, "title": f"Land-book site {wid}", "page_url": f"https://land-book.com/websites/{wid}",
                     "asset_url": url, "thumb_url": url})
    return _dedupe(rows)


def parse_awwwards(html: str) -> list[dict]:
    return _dedupe([{"id": slug, "title": _html.unescape(label) or slug, "page_url": f"https://www.awwwards.com/sites/{slug}",
                     "asset_url": big or small, "thumb_url": small} for label, slug, small, big in AW_RE.findall(html)])


def _dedupe(rows: list[dict]) -> list[dict]:
    seen, out = set(), []
    for r in rows:
        if r["id"] not in seen:
            seen.add(r["id"]); out.append(r)
    return out


def _items(slug: str, rows: list[dict], tags: list[str]) -> list[ItemDraft]:
    return [ItemDraft(key=f"{slug}:{r['id']}", kind="site", title=r["title"], page_url=r["page_url"], asset_url=r["asset_url"],
                      thumb_url=r["thumb_url"], tags=tags, meta={"gallery": slug}, license="screenshot © site owner; reference only")
            for r in rows]


def _render_safe(fetch, url, wait, **kw) -> tuple[str, str | None]:
    """(html, error): a FetchError becomes an empty page plus its message, for the collection's error column."""
    try:
        return fetch.render(url, wait=wait, **kw), None
    except Blocked:
        raise
    except FetchError as e:
        return "", str(e)


class DarkDesignAdapter:
    info = SourceInfo("darkdesign", "Dark.design", "https://www.dark.design", 2, notes="dark-mode site gallery")

    def collections(self, fetch):
        html, err = _render_safe(fetch, "https://www.dark.design", 6)
        rows = parse_dark(html)
        yield CollectionDraft("darkdesign/latest", "site", "Dark.design: latest", languages=["dark mode ui"], error=err), _items("darkdesign", rows, ["dark mode ui"])


class SiteinspireAdapter:
    info = SourceInfo("siteinspire", "Siteinspire", "https://www.siteinspire.com", 2, notes="rate-limited: 1 request per 3 s")
    CATS = ("typographic", "design-and-art-direction", "agencies-and-consultancies", "minimal", "portfolio", "e-commerce")

    def collections(self, fetch):
        for c in self.CATS:
            html, err = _render_safe(fetch, f"https://www.siteinspire.com/websites/category/{c}", 8, stealth=True)
            rows = parse_siteinspire(html)
            yield CollectionDraft(f"siteinspire/{c}", "site", f"Siteinspire: {c}", query=c, error=err), _items("siteinspire", rows, [c])


class GodlyAdapter:
    info = SourceInfo("godly", "Godly", "https://godly.website", 2, notes="listing only; items link to the listing")

    def collections(self, fetch):
        html, err = _render_safe(fetch, "https://godly.website/websites", 8)
        rows = parse_godly(html)
        yield CollectionDraft("godly/latest", "site", "Godly: latest", error=err), _items("godly", rows, ["landing page hero"])


class LandbookAdapter:
    info = SourceInfo("landbook", "Land-book", "https://land-book.com", 2, notes="listing only")

    def collections(self, fetch):
        html, err = _render_safe(fetch, "https://land-book.com/websites", 8, stealth=True)
        rows = parse_landbook(html)
        yield CollectionDraft("landbook/latest", "site", "Land-book: latest", error=err), _items("landbook", rows, ["landing page hero"])


class AwwwardsAdapter:
    info = SourceInfo("awwwards", "Awwwards", "https://www.awwwards.com", 2, notes="plain HTTP (Obscura gets 403); category listings")
    CATS = ("animation", "typography", "minimal", "portfolio", "e-commerce", "illustration")

    def collections(self, fetch):
        for c in self.CATS:
            err = None
            try:
                html = fetch.get_text(f"https://www.awwwards.com/websites/{c}/")
            except Blocked:
                raise
            except FetchError as e:
                html, err = "", str(e)
            yield CollectionDraft(f"awwwards/{c}", "site", f"Awwwards: {c}", query=c, error=err), _items("awwwards", parse_awwwards(html), [c])


DARK = register(DarkDesignAdapter())
SITEINSPIRE = register(SiteinspireAdapter())
GODLY = register(GodlyAdapter())
LANDBOOK = register(LandbookAdapter())
AWWWARDS = register(AwwwardsAdapter())
