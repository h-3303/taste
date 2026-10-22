import html as _html
import re

from ..fetch import Blocked, FetchError
from ..models import CollectionDraft, ItemDraft, SourceInfo
from ..vocabulary import slugify
from .base import register
from .html import unique

API = "https://cari.institute/api/aesthetics?page={n}"
PAGES = 5
PREVIEW_RE = re.compile(r'<img class="image-preview" src="([^"]+)"')
P_RE = re.compile(r"<p[^>]*>(.*?)</p>", re.S)
TAG_RE = re.compile(r"<[^>]+>")
DESC_RE = re.compile(r'<div class="description">(.*?)</div>', re.S)
SLOT_RE = re.compile(r"<p[^>]*\sslot=.*?</p>", re.S)


def parse_index(data: dict) -> list[dict]:
    out = []
    for group in data.get("content", []):
        for letter, entries in group.items():
            out += [e for e in entries if e.get("urlSlug")]
    return out


def parse_page(page: str) -> dict:
    m = DESC_RE.search(page)
    if m:    # the aesthetic's own intro block
        paras = [TAG_RE.sub("", p) for p in P_RE.findall(m.group(1))]
    else:    # fallback: any long paragraph, minus the footer and slotted case-study blurbs
        paras = [TAG_RE.sub("", p) for p in P_RE.findall(SLOT_RE.sub("", page))]
        paras = [p for p in paras if len(p) > 40 and not p.strip().startswith("©")]
    text = " ".join(" ".join(p.split()) for p in paras if p.strip())
    return {"description": _html.unescape(text)[:600], "reference_images": unique(_html.unescape(u) for u in PREVIEW_RE.findall(page))}


class CariAdapter:
    info = SourceInfo("cari", "CARI (Consumer Aesthetics Research Institute)", "https://cari.institute/aesthetics", 2,
                      notes="index of named aesthetics; reference images are on Are.na's CDN and are kept as URLs only")

    def collections(self, fetch):
        entries, api_error = [], None
        for n in range(1, PAGES + 1):
            try:
                entries += parse_index(fetch.get_json(API.format(n=n)))
            except Blocked:
                raise
            except FetchError as e:
                api_error = str(e)
                break
        if not entries and api_error:    # no index at all: record the failure on an empty collection
            yield CollectionDraft("cari/index", "image", "CARI aesthetics", error=api_error), []
            return
        groups: dict[str, list[dict]] = {}
        for e in entries:
            groups.setdefault(e.get("decadeYear") or "undated", []).append(e)
        for n, (decade, es) in enumerate(sorted(groups.items())):
            items, errors = [], ([api_error] if api_error and n == 0 else [])
            for e in es:
                page_url = f"https://cari.institute/aesthetics/{e['urlSlug']}"
                try:
                    detail = parse_page(fetch.render(page_url, wait=6))
                except Blocked:
                    raise
                except FetchError as exc:
                    errors.append(str(exc))
                    detail = {"description": "", "reference_images": []}
                era = f"{e.get('startYear') or '?'} – {e.get('endYear') or 'present'}"
                items.append(ItemDraft(
                    key=f"cari:{e['urlSlug']}", kind="image", title=e["name"], page_url=page_url,
                    asset_url=e.get("displayImageUrl") or "", thumb_url=e.get("displayImageUrl"),
                    tags=[e["name"].lower(), decade, "aesthetic"],
                    meta={"era": era, "decade": decade, **detail}, license="CARI attribution guidelines"))
            yield CollectionDraft(f"cari/{slugify(decade)}", "image", f"CARI aesthetics: {decade}", query=decade,
                                  error=errors[0] + (f" (+{len(errors) - 1} more)" if len(errors) > 1 else "") if errors else None), items


ADAPTER = register(CariAdapter())
