import pytest

from taste.library.fetch import Blocked, FakeFetcher, FetchError
from taste.library.sources import metalforge


def test_parse_effects(fixture):
    rows = metalforge.parse_home(fixture("metalforge/home.html"))
    areas = {r["area"] for r in rows}
    assert {"editor", "buttons", "carousel"} <= areas and len(rows) >= 40
    assert all(r["name"] and r["href"].startswith("/") for r in rows)
    triples = {(r["area"], r["name"], r["href"]) for r in rows}
    assert ("editor", "grain", "/editor#effect=grain") in triples
    assert ("buttons", "fireworks", "/buttons/fireworks") in triples
    chars = [r for r in rows if r["area"] == "character"]
    assert chars and all("&amp;" not in r["href"] and r["href"].startswith("/character?c=" + r["name"]) for r in chars)


def test_dedupe_and_nameless_skipped():
    page = ('<a href="/editor#effect=grain">a</a><a href="/editor#effect=grain">b</a>'
            '<a href="/edison#size=0.13&amp;x=1">c</a>')
    rows = metalforge.parse_home(page)
    assert [(r["area"], r["name"]) for r in rows] == [("editor", "grain")]


def test_card_image_matched_by_area():
    page = '<a href="/carousel#effect=bulge">a</a><img src="/carousel-card-stretch.webp"><a href="/editor#effect=x">b</a>'
    rows = {r["area"]: r for r in metalforge.parse_home(page)}
    assert rows["carousel"]["card"] == "https://metalforge.xyz/carousel-card-stretch.webp"
    assert rows["editor"]["card"] is None


def test_collections_and_pluck(fixture, tmp_path):
    f = FakeFetcher(pages={"metalforge.xyz": fixture("metalforge/home.html")})
    colls = {c.slug: items for c, items in metalforge.ADAPTER.collections(f)}
    it = colls["metalforge/editor"][0]
    assert it.kind == "snippet" and it.key.startswith("metalforge:editor:") and "paywall" in it.meta
    assert it.license == "proprietary" and it.page_url == it.asset_url
    keys = [i.key for items in colls.values() for i in items]
    assert len(keys) == len(set(keys))
    r = metalforge.ADAPTER.pluck({"id": "x", "page_url": it.page_url, "meta": it.meta, "title": it.title}, f, tmp_path, {})
    assert r.path is None and "metalforge.xyz" in r.text and "subscription" in r.text


def test_blocked_propagates():
    class F(FakeFetcher):
        def render(self, url, wait=6, stealth=False, obey_robots=True, timeout=40):
            raise Blocked(url)
    with pytest.raises(Blocked):
        list(metalforge.ADAPTER.collections(F()))


def test_fetch_error_yields_no_collections():
    [(coll, items)] = list(metalforge.ADAPTER.collections(FakeFetcher()))
    assert items == [] and coll.error


def test_card_stem_matching(fixture):
    rows = {(r["area"], r["name"]): r for r in metalforge.parse_home(fixture("metalforge/home.html"))}
    assert rows[("carousel", "stretch")]["card"] == "https://metalforge.xyz/carousel-card-stretch.webp"
    page = '<a href="/editor#effect=watermelon">a</a><img src="/fruit-card-watermelon.webp">'
    assert metalforge.parse_home(page)[0]["card"] is None     # name appears only in another area's card


def test_effect_with_trailing_query(fixture):
    rows = {(r["area"], r["name"]): r for r in metalforge.parse_home(fixture("metalforge/home.html"))}
    r = rows[("editor", "progress")]
    assert r["href"] == "/editor#effect=progress&style=slosh"
