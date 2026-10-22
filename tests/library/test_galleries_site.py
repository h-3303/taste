import pytest

from taste.library.fetch import Blocked, FakeFetcher, FetchError
from taste.library.sources import galleries_site as g

LICENSE = "screenshot © site owner; reference only"
SI_FIRST = "QJWODQu1ybKF"
SI_URL = ("https://r2.siteinspire.com/cdn-cgi/image/width={},height={},quality=75,format=auto,metadata=none,"
          "gravity=top,fit=crop,compress=true/QJWODQu1ybKF.jpg")
LB_FIRST_URL = ("https://cdn.land-book.com/image/0x0:1920x2880/1200x0/filters:format(webp)/website/100748/"
                "d135548ae4def104-screenshot-upload?signature=ed92cdaa5dd5ee1bb407e1d3b5aeea4aa48b7d6e447e4ab1dd61273695cf3252")
AW_IMG = "https://assets.awwwards.com/awards/media/cache/thumb_{}/submissions/2026/09/6ab1c8e48df6d916406503.png"


def test_parse_dark(fixture):
    rows = g.parse_dark(fixture("galleries_site/dark.html"))
    assert len(rows) >= 10
    r = rows[0]
    assert r["page_url"].startswith("https://www.dark.design/site/") and r["asset_url"].endswith(".webp")
    assert "render/image" in r["thumb_url"] and r["title"] and not r["title"][-1].isdigit()
    assert r == {"id": "basement", "title": "Basement", "page_url": "https://www.dark.design/site/basement-1786786858853",
                 "asset_url": f"{g.DARK_BASE}/object/public/screenshots/auto-1786786805983.webp",
                 "thumb_url": f"{g.DARK_BASE}/render/image/public/screenshots/auto-1786786805983.webp?width=640&quality=70"}
    assert len({r["id"] for r in rows}) == len(rows)


def test_parse_siteinspire(fixture):
    rows = g.parse_siteinspire(fixture("galleries_site/siteinspire.html"))
    assert len(rows) >= 10 and all("width=1920" in r["asset_url"] and "width=384" in r["thumb_url"] for r in rows)
    assert all(r["title"] for r in rows)
    assert "Mobbin" not in [r["title"] for r in rows]          # sponsor card linking off-site is skipped
    assert rows[0]["id"] == SI_FIRST and rows[0]["title"] == "The Future In Black"
    assert rows[0]["page_url"] == "https://www.siteinspire.com/website/13635-the-future-in-black"
    assert all(r["page_url"].startswith("https://www.siteinspire.com/website/") for r in rows)
    assert rows[0]["asset_url"] == SI_URL.format(1920, 1200) and rows[0]["thumb_url"] == SI_URL.format(384, 240)
    assert rows[1]["title"] == "Komma Komma" and rows[1]["page_url"].endswith("/website/13619-komma-komma")


def test_parse_siteinspire_falls_back_to_listing_without_anchor():
    html = '<img alt="X &amp; Y" class="WebsiteCard__image a" src="https://r2.siteinspire.com/cdn-cgi/image/width=1920,format=auto/abc.jpg">'
    (r,) = g.parse_siteinspire(html)
    assert r["page_url"] == "https://www.siteinspire.com/websites" and r["title"] == "X & Y"


def test_parse_godly(fixture):
    rows = g.parse_godly(fixture("galleries_site/godly.html"))
    assert len(rows) >= 10 and all(r["asset_url"].endswith("/poster/1200.webp") for r in rows)
    assert rows[0] == {"id": "our3i3u", "title": "Godly site our3i3u", "page_url": "https://godly.website/websites",
                       "asset_url": "https://cdn.recent.design/items/our3i3u/0/poster/1200.webp",
                       "thumb_url": "https://cdn.recent.design/items/our3i3u/0/poster/640.webp"}
    assert len({r["id"] for r in rows}) == len(rows)


def test_parse_landbook(fixture):
    rows = g.parse_landbook(fixture("galleries_site/landbook.html"))
    assert len(rows) >= 10 and all(r["page_url"].startswith("https://land-book.com/websites/") for r in rows)
    assert rows[0]["id"] == "100748" and rows[0]["page_url"] == "https://land-book.com/websites/100748"
    assert rows[0]["asset_url"] == rows[0]["thumb_url"] == LB_FIRST_URL
    assert len({r["id"] for r in rows}) == len(rows)


def test_parse_awwwards(fixture):
    rows = g.parse_awwwards(fixture("galleries_site/awwwards.html"))
    assert len(rows) >= 10 and all(r["page_url"].startswith("https://www.awwwards.com/sites/") for r in rows)
    assert all(r["asset_url"].startswith("https://assets.awwwards.com/") for r in rows)
    assert rows[0] == {"id": "bello", "title": "bello", "page_url": "https://www.awwwards.com/sites/bello",
                       "asset_url": AW_IMG.format("880_660"), "thumb_url": AW_IMG.format("440_330")}
    assert rows[1]["id"] == "justin-lerner" and rows[1]["title"] == "Justin Lerner"


def test_parsers_return_empty_on_empty_page():
    for fn in (g.parse_dark, g.parse_siteinspire, g.parse_godly, g.parse_landbook, g.parse_awwwards):
        assert fn("") == []


def test_siteinspire_collections_use_render_and_categories(fixture):
    f = FakeFetcher(pages={"siteinspire.com/websites/category/": fixture("galleries_site/siteinspire.html")})
    colls = list(g.SITEINSPIRE.collections(f))
    assert [c.slug for c, _ in colls][:2] == ["siteinspire/typographic", "siteinspire/design-and-art-direction"]
    assert [c.slug for c, _ in colls] == ["siteinspire/" + c for c in
                                          ("typographic", "design-and-art-direction", "agencies-and-consultancies", "minimal", "portfolio", "e-commerce")]
    assert colls[0][1][0].kind == "site" and colls[0][1][0].key.startswith("siteinspire:")
    assert colls[0][1][0].key == f"siteinspire:{SI_FIRST}" and colls[0][1][0].license == LICENSE
    assert colls[0][1][0].page_url == "https://www.siteinspire.com/website/13635-the-future-in-black"
    assert [u for k, u in f.calls if k == "render"][2] == "https://www.siteinspire.com/websites/category/agencies-and-consultancies"


def test_awwwards_uses_plain_http(fixture):
    f = FakeFetcher(text={"awwwards.com/websites/": fixture("galleries_site/awwwards.html")})
    colls = list(g.AWWWARDS.collections(f))
    assert f.calls[0][0] == "get_text" and colls[0][1]
    assert all(k == "get_text" for k, _ in f.calls)
    assert [c.slug for c, _ in colls] == ["awwwards/" + c for c in ("animation", "typography", "minimal", "portfolio", "e-commerce", "illustration")]
    assert f.calls[0][1] == "https://www.awwwards.com/websites/animation/"
    it = colls[0][1][0]
    assert it.key == "awwwards:bello" and it.kind == "site" and it.page_url == "https://www.awwwards.com/sites/bello"
    assert it.asset_url == AW_IMG.format("880_660") and it.thumb_url == AW_IMG.format("440_330")


def test_single_page_collections(fixture):
    d = list(g.DARK.collections(FakeFetcher(pages={"dark.design": fixture("galleries_site/dark.html")})))
    assert [c.slug for c, _ in d] == ["darkdesign/latest"] and d[0][0].kind == "site"
    assert d[0][1][0].key == "darkdesign:basement" and d[0][1][0].license == LICENSE
    go = list(g.GODLY.collections(FakeFetcher(pages={"godly.website": fixture("galleries_site/godly.html")})))
    assert go[0][0].slug == "godly/latest" and go[0][1][0].key == "godly:our3i3u"
    lb = list(g.LANDBOOK.collections(FakeFetcher(pages={"land-book.com": fixture("galleries_site/landbook.html")})))
    assert lb[0][0].slug == "landbook/latest" and lb[0][1][0].key == "landbook:100748"
    assert lb[0][1][0].asset_url == LB_FIRST_URL and lb[0][1][0].kind == "site"


class _Recording(FakeFetcher):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.kwargs = []

    def render(self, url, **k):
        self.kwargs.append(k)
        return super().render(url, **k)


def test_siteinspire_renders_with_stealth(fixture):
    f = _Recording(pages={"siteinspire.com": fixture("galleries_site/siteinspire.html")})
    list(g.SITEINSPIRE.collections(f))
    assert f.kwargs and all(k.get("stealth") is True and k.get("wait") == 8 for k in f.kwargs)


def test_landbook_renders_with_stealth(fixture):
    f = _Recording(pages={"land-book.com": fixture("galleries_site/landbook.html")})
    list(g.LANDBOOK.collections(f))
    assert f.kwargs == [{"wait": 8, "stealth": True}]


def test_dark_and_godly_do_not_use_stealth(fixture):
    f = _Recording(pages={"dark.design": fixture("galleries_site/dark.html"), "godly.website": fixture("galleries_site/godly.html")})
    list(g.DARK.collections(f)); list(g.GODLY.collections(f))
    assert all("stealth" not in k for k in f.kwargs)


class _Raising(FakeFetcher):
    def __init__(self, exc):
        super().__init__()
        self.exc = exc

    def render(self, *a, **k):
        raise self.exc

    def get_text(self, *a, **k):
        raise self.exc


@pytest.mark.parametrize("adapter", [g.DARK, g.SITEINSPIRE, g.GODLY, g.LANDBOOK, g.AWWWARDS])
def test_blocked_propagates(adapter):
    with pytest.raises(Blocked):
        list(adapter.collections(_Raising(Blocked("429"))))


@pytest.mark.parametrize("adapter", [g.DARK, g.SITEINSPIRE, g.GODLY, g.LANDBOOK, g.AWWWARDS])
def test_fetch_error_yields_empty_collections(adapter):
    colls = list(adapter.collections(_Raising(FetchError("boom"))))
    assert colls and all(items == [] and "boom" in c.error for c, items in colls)
