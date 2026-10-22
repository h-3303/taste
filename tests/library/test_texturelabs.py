import pytest

from taste.library.fetch import Blocked, FakeFetcher, FetchError
from taste.library.sources import texturelabs

LIST = "https://texturelabs.org/textures/"


def test_parse_list(fixture):
    slugs = texturelabs.parse_list(fixture("texturelabs/list.html"))
    assert len(slugs) >= 20 and "feed" not in slugs and "page" not in slugs
    assert "cmykpaperpattern" in slugs


def test_parse_list_categories(fixture):
    cats = texturelabs.parse_list_categories(fixture("texturelabs/list.html"))
    assert cats["retratone_v1-0-4"] == []                 # only "unlisted" -> no real category
    assert "paper" in {c for v in cats.values() for c in v}
    assert not {"featured", "newest", "unlisted", "most-popular"} & {c for v in cats.values() for c in v}


def test_parse_item(fixture):
    d = texturelabs.parse_item(fixture("texturelabs/item.html"))
    assert d["og_image"] == "https://texturelabs.org/wp-content/uploads/Texturelabs_CMYKPaperPatternS.jpg"
    assert d["title"] == "CMYK Seamless Paper"


def _fake(fixture, calls=None):
    class F(FakeFetcher):
        def get_text(self, url, headers=None):
            self.calls.append(("get_text", url))
            if url.rstrip("/").endswith("/textures") or "/page/" in url:
                return fixture("texturelabs/list.html") if "/page/" not in url else ""
            return fixture("texturelabs/item.html")
    return F()


def test_collections_group_by_category(fixture):
    colls = list(texturelabs.ADAPTER.collections(_fake(fixture)))
    assert colls and all(c.slug.startswith("texturelabs/") for c, _ in colls)
    it = colls[0][1][0]
    assert it.kind == "texture" and it.key.startswith("texturelabs:") and it.thumb_url == it.asset_url
    assert it.license == "Texture Labs free licence (see page)"
    by_slug = dict((c.slug, items) for c, items in colls)
    assert "texturelabs/paper" in by_slug and all("paper" in i.tags for i in by_slug["texturelabs/paper"])
    assert any(i.key == "texturelabs:cmykpaperpattern" for i in by_slug["texturelabs/uncategorised"])


def test_item_in_two_categories_lands_in_both(fixture):
    cats = texturelabs.parse_list_categories(fixture("texturelabs/list.html"))
    multi = next(s for s, v in cats.items() if len(v) >= 2)
    colls = dict((c.slug, items) for c, items in texturelabs.ADAPTER.collections(_fake(fixture)))
    for cat in cats[multi]:
        assert any(i.key == f"texturelabs:{multi}" for i in colls[f"texturelabs/{cat}"])


def test_pagination_stops_when_a_page_fails(fixture):
    f = _fake(fixture)
    list(texturelabs.ADAPTER.collections(f))
    listing = [u for _, u in f.calls if "/textures/" in u and ("/page/" in u or u == LIST)]
    assert listing == [LIST, LIST + "page/2/"] or listing[:2] == [LIST, LIST + "page/2/"]
    assert LIST + "page/3/" not in [u for _, u in f.calls]


def test_pagination_fetches_all_pages(fixture):
    class F(FakeFetcher):
        def get_text(self, url, headers=None):
            self.calls.append(("get_text", url))
            return fixture("texturelabs/list.html") if "/page/" in url or url == LIST else fixture("texturelabs/item.html")
    f = F()
    list(texturelabs.ADAPTER.collections(f))
    pages = [u for _, u in f.calls if "/page/" in u]
    assert pages == [f"{LIST}page/{n}/" for n in range(2, texturelabs.PAGES + 1)]


def test_blocked_propagates():
    class F(FakeFetcher):
        def get_text(self, url, headers=None):
            raise Blocked(url)
    with pytest.raises(Blocked):
        list(texturelabs.ADAPTER.collections(F()))


def test_fetch_error_yields_empty():
    class F(FakeFetcher):
        def get_text(self, url, headers=None):
            raise FetchError('boom ' + url)
    [(coll, items)] = list(texturelabs.ADAPTER.collections(F()))
    assert items == [] and "boom" in coll.error


def test_pagination_stops_on_fetch_error(fixture):
    class F(FakeFetcher):
        def get_text(self, url, headers=None):
            self.calls.append(("get_text", url))
            if url.endswith("/page/3/"):
                raise FetchError(url)
            return fixture("texturelabs/list.html") if "/page/" in url or url == LIST else fixture("texturelabs/item.html")
    f = F()
    list(texturelabs.ADAPTER.collections(f))
    pages = [u for _, u in f.calls if "/page/" in u]
    assert pages == [LIST + "page/2/", LIST + "page/3/"]
