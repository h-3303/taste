import html as _html
import re
from pathlib import Path

from ..fetch import Blocked, FetchError
from ..models import CollectionDraft, ItemDraft, PluckResult, SourceInfo
from .base import register

HOME = "https://metalforge.xyz"
LINK = re.compile(r'href="(/([a-z0-9-]+)(?:#(?:effect|scene|shape)=([a-z0-9-]+)(?:(?:&amp;|&)[^"]*)?|/([a-z0-9-]+)|\?c=([a-z0-9-]+)[^"]*))"')
IMG = re.compile(r'<img[^>]*src="(/[^"]+\.(?:webp|png|jpg))"')
PAYWALL = "code requires a MetalForge subscription (€9.99/month on 2026-10-07); MCP available"


def _tokens(path: str) -> set[str]:
    return set(re.split(r"[-_/]+", path.rsplit(".", 1)[0].lower())) - {""}


def _card(imgs: list[str], area: str, name: str) -> str | None:
    """Best card image: tokens of the path contain area and name, else area alone; never name alone."""
    area_t, name_t = _tokens(area), _tokens(name)
    both = alone = None
    for i in imgs:
        t = _tokens(i)
        if area_t <= t:
            alone = alone or i
            if name_t <= t:
                both = both or i
    return both or alone


def parse_home(page: str) -> list[dict]:
    rows, seen = [], set()
    imgs = IMG.findall(page)
    for href, area, eff, sub, char in LINK.findall(page):
        name = eff or sub or char
        if not name or (area, name) in seen:
            continue
        seen.add((area, name))
        card = _card(imgs, area, name)
        rows.append({"area": area, "name": name, "href": _html.unescape(href), "card": f"{HOME}{card}" if card else None})
    return rows


class MetalForgeAdapter:
    info = SourceInfo("metalforge", "MetalForge", HOME, 2, notes="390 shader animations for SwiftUI, React Native and web; pages public, code paid")

    def collections(self, fetch):
        error = None
        try:
            rows = parse_home(fetch.render(HOME, wait=8))
        except Blocked:
            raise
        except FetchError as e:
            rows, error = [], str(e)
        if error:   # the home page is the only listing: record the failure on an empty collection
            yield CollectionDraft("metalforge/home", "snippet", "MetalForge: home", error=error), []
            return
        groups: dict[str, list[ItemDraft]] = {}
        for r in rows:
            groups.setdefault(r["area"], []).append(ItemDraft(
                key=f"metalforge:{r['area']}:{r['name']}", kind="snippet", title=f"MetalForge {r['area']} · {r['name']}",
                page_url=f"{HOME}{r['href']}", asset_url=f"{HOME}{r['href']}", thumb_url=r["card"],
                tags=["shader", "animation", r["area"], "swiftui", "react native", "web"],
                meta={"platforms": ["SwiftUI", "React Native", "Web"], "paywall": PAYWALL, "effect": r["name"], "area": r["area"]},
                license="proprietary"))
        for area, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            yield CollectionDraft(f"metalforge/{area}", "snippet", f"MetalForge: {area}", query=area), items

    def pluck(self, item: dict, fetch, dest_dir: Path, opts: dict) -> PluckResult:
        return PluckResult(item["id"], None, f"{item['page_url']}\n{item.get('meta', {}).get('paywall', PAYWALL)}",
                           "MetalForge: open the page, tweak the sliders, take the code (subscription)")


ADAPTER = register(MetalForgeAdapter())
