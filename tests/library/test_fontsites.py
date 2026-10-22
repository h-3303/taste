import pytest

from taste.library.fetch import Blocked, FakeFetcher, FetchError
from taste.library.sources import fontsites


def _fetcher(fixture):
    return FakeFetcher(pages={"collletttivo.it/typefaces/": fixture("fontsites/collletttivo-borges.html"),
                              "collletttivo.it/typefaces": fixture("fontsites/collletttivo-list.html")})


def test_collletttivo_list_links(fixture):
    slugs = fontsites.parse_collletttivo_list(fixture("fontsites/collletttivo-list.html"))
    assert slugs[:3] == ["borges", "ronzino", "aujournuit"]
    assert "_payload.json" not in " ".join(slugs) and len(slugs) == len(set(slugs))


def test_collletttivo_page(fixture):
    d = fontsites.parse_collletttivo_page(fixture("fontsites/collletttivo-borges.html"))
    assert d["title"] == "Borges Family"
    assert d["og_image"].startswith("https://www.collletttivo.it/_og/") and d["og_image"].endswith(".png")
    assert "download_url" not in d


def test_collletttivo_collection(fixture):
    coll, items = next(fontsites.COLLLETTTIVO.collections(_fetcher(fixture)))
    assert coll.slug == "collletttivo/typefaces" and coll.kind == "font" and len(items) >= 5
    first = items[0]
    assert first.key == "collletttivo:borges" and first.title == "Borges Family" and first.kind == "font"
    assert first.page_url == "https://www.collletttivo.it/typefaces/borges"
    assert first.thumb_url.startswith("https://www.collletttivo.it/_og/") and first.asset_url == first.thumb_url
    assert first.meta["asset_is_specimen"] is True and "download_url" not in first.meta
    assert first.license == "OFL (see page)"


def test_collletttivo_blocked_propagates(fixture):
    class F(FakeFetcher):
        def render(self, url, wait=6, stealth=False, obey_robots=True, timeout=40):
            raise Blocked(url)
    with pytest.raises(Blocked):
        list(fontsites.COLLLETTTIVO.collections(F()))


def test_collletttivo_fetch_error_yields_empty():
    class F(FakeFetcher):
        def render(self, url, wait=6, stealth=False, obey_robots=True, timeout=40):
            raise FetchError(url)
    coll, items = next(fontsites.COLLLETTTIVO.collections(F()))
    assert coll.slug == "collletttivo/typefaces" and items == [] and coll.error


def test_collletttivo_failed_typeface_page_is_skipped(fixture):
    class F(FakeFetcher):
        def render(self, url, wait=6, stealth=False, obey_robots=True, timeout=40):
            if url.endswith("/typefaces/ronzino"):
                raise FetchError(url)
            return super().render(url, wait=wait)
    f = F(pages=_fetcher(fixture).pages)
    _, items = next(fontsites.COLLLETTTIVO.collections(f))
    keys = [i.key for i in items]
    assert "collletttivo:ronzino" not in keys and "collletttivo:borges" in keys and len(keys) == 15
    assert all(i.thumb_url for i in items)
