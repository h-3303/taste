import html as _html
import re

from ..fetch import Blocked, FetchError
from ..models import CollectionDraft, ItemDraft, SourceInfo
from .base import register
from .html import title as page_title, unique

LIST_RE = re.compile(r'href="https://texturelabs\.org/textures/([a-z0-9_-]+)/"')
# The 2026 site shows categories only on the list pages, as texture_cat-<slug> classes on each <article>.
ARTICLE_RE = re.compile(r'<article class="([^"]*)"[^>]*>\s*<header><h2 class="entry-title"><a href="https://texturelabs\.org/textures/([a-z0-9_-]+)/"')
CAT_CLASS = re.compile(r"texture_cat-([a-z0-9_-]+)")
TITLE_RE = re.compile(r'<div class="single-texture-title home-title">\s*([^<]+?)\s*</div>')
IMG_RE = re.compile(r'<div class="image-full">\s*<img\s+src="([^"]+)"')
NOT_CATEGORIES = {"featured", "newest", "most-popular", "unlisted", "recommended"}   # site-wide flags, not subjects
SKIP = {"feed", "page"}
PAGES = 5


def parse_list(page: str) -> list[str]:
    return [s for s in unique(LIST_RE.findall(page)) if s not in SKIP]


def parse_list_categories(page: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for classes, slug in ARTICLE_RE.findall(page):
        out[slug] = [c for c in unique(CAT_CLASS.findall(classes)) if c not in NOT_CATEGORIES]
    return out


def parse_item(page: str) -> dict:
    m = IMG_RE.search(page)
    t = TITLE_RE.search(page)
    return {"og_image": _html.unescape(m.group(1)) if m else "",
            "title": _html.unescape(t.group(1)) if t else page_title(page).split(" | ")[-1].strip()}


def _summary(errors: list[str]) -> str | None:
    return None if not errors else errors[0] + (f" (+{len(errors) - 1} more)" if len(errors) > 1 else "")


class TextureLabsAdapter:
    info = SourceInfo("texturelabs", "Texture Labs", "https://texturelabs.org", 2, notes="free textures; categories from list pages, preview image from item pages")

    def collections(self, fetch):
        slugs, cats, errors = [], {}, []
        for n in range(1, PAGES + 1):
            url = "https://texturelabs.org/textures/" if n == 1 else f"https://texturelabs.org/textures/page/{n}/"
            try:
                page = fetch.get_text(url)
            except Blocked:
                raise
            except FetchError as e:
                errors.append(str(e))
                break
            found = parse_list(page)
            if not found:
                break
            slugs += found
            for s, c in parse_list_categories(page).items():
                cats.setdefault(s, c)
        groups: dict[str, list[ItemDraft]] = {}
        for s in unique(slugs):
            url = f"https://texturelabs.org/textures/{s}/"
            try:
                d = parse_item(fetch.get_text(url))
            except Blocked:
                raise
            except FetchError as e:
                errors.append(str(e))
                continue
            if not d["og_image"]:
                continue
            tags = cats.get(s, [])
            item = ItemDraft(key=f"texturelabs:{s}", kind="texture", title=d["title"] or s, page_url=url,
                             asset_url=d["og_image"], thumb_url=d["og_image"], tags=tags,
                             meta={"categories": tags}, license="Texture Labs free licence (see page)")
            for c in tags or ["uncategorised"]:
                groups.setdefault(c, []).append(item)
        error = _summary(errors)
        if not groups and error:    # nothing listed at all: record the failure on an empty collection
            yield CollectionDraft("texturelabs/all", "texture", "Texture Labs", error=error), []
        for n, (cat, items) in enumerate(sorted(groups.items(), key=lambda kv: -len(kv[1]))):
            yield CollectionDraft(f"texturelabs/{cat}", "texture", f"Texture Labs: {cat.replace('-', ' ')}", query=cat,
                                  error=error if n == 0 else None), items


ADAPTER = register(TextureLabsAdapter())
