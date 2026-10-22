import pytest

from taste.library.fetch import Blocked, FakeFetcher, FetchError
from taste.library.sources import cari

FIRST_REF = "https://images.are.na/eyJidWNrZXQiOiJhcmVuYV9pbWFnZXMiLCJrZXkiOiI0NjI2NjMxOC9vcmlnaW5hbF8wNDg2YTMzNzU3ZjBkMjk4ZjMyZjNmZTEyMTRkMWViYS5wbmciLCJlZGl0cyI6eyJyZXNpemUiOnsid2lkdGgiOjEyMDAsImhlaWdodCI6MTIwMCwiZml0IjoiaW5zaWRlIiwid2l0aG91dEVubGFyZ2VtZW50Ijp0cnVlfSwid2VicCI6eyJxdWFsaXR5Ijo3NX0sImpwZWciOnsicXVhbGl0eSI6NzV9LCJyb3RhdGUiOm51bGx9fQ=="


def make(fixture, **over):
    kw = dict(json={"page=1": fixture("cari/api1.json"), "page=": {"content": []}},
              pages={"cari.institute/aesthetics/": fixture("cari/frutiger-aero.html")})
    kw.update(over)
    return FakeFetcher(**kw)


def test_parse_index_groups_by_decade(fixture):
    entries = cari.parse_index(fixture("cari/api1.json"))
    assert len(entries) >= 15 and {"name", "urlSlug", "decadeYear", "displayImageUrl"} <= set(entries[0])
    fa = next(e for e in entries if e["name"] == "Frutiger Aero")
    assert fa["urlSlug"] == "frutiger-aero" and fa["decadeYear"] == "2000s"


def test_parse_page_keeps_description_and_reference_urls(fixture):
    d = cari.parse_page(fixture("cari/frutiger-aero.html"))
    assert len(d["description"]) > 50 and all(u.startswith("https://") for u in d["reference_images"])
    assert d["reference_images"][0] == FIRST_REF and len(d["description"]) <= 600
    assert d["description"].startswith("Term coined by Sofi Lee to describe the corporate tech aesthetic")
    assert "©" not in d["description"] and "Consumer Aesthetics Research Institute" not in d["description"]
    assert "Asadal" not in d["description"]


def test_parse_page_fallback_drops_footer_and_slotted_blurbs():
    page = ('<p slot="summary">A case study blurb that is certainly longer than forty characters.</p>'
            '<p>The real description of this aesthetic, long enough to be kept as text.</p>'
            '<p>© Consumer Aesthetics Research Institute 2026 and some more words to be long</p>')
    assert cari.parse_page(page)["description"] == "The real description of this aesthetic, long enough to be kept as text."


def test_collections(fixture):
    f = make(fixture)
    colls = list(cari.ADAPTER.collections(f))
    assert colls and all(c.slug.startswith("cari/") and c.slug.endswith("s") for c, _ in colls)
    it = colls[0][1][0]
    assert it.key.startswith("cari:") and it.thumb_url.startswith("https://cari-prod.s3") and "–" in it.meta["era"]
    assert it.meta["reference_images"] and not any(c[0] == "download" for c in f.calls)
    assert it.title.lower() in [t.lower() for t in it.tags]


def test_frutiger_aero_lands_in_2000s_with_exact_values(fixture):
    colls = {c.slug: items for c, items in cari.ADAPTER.collections(make(fixture))}
    assert "cari/2000s" in colls
    it = next(i for i in colls["cari/2000s"] if i.key == "cari:frutiger-aero")
    assert it.title == "Frutiger Aero" and it.page_url == "https://cari.institute/aesthetics/frutiger-aero"
    assert it.meta["era"] == "Mid 2000s – Early 2010s" and "frutiger aero" in it.tags
    assert it.meta["reference_images"][0] == FIRST_REF
    assert it.asset_url == it.thumb_url and it.license == "CARI attribution guidelines"


def test_never_downloads_reference_images(fixture):
    f = make(fixture)
    list(cari.ADAPTER.collections(f))
    assert not any(kind == "download" or "images.are.na" in url for kind, url in f.calls)


def test_blocked_from_api_propagates(fixture):
    class B(FakeFetcher):
        def get_json(self, url, params=None, headers=None):
            raise Blocked("challenge")
    with pytest.raises(Blocked):
        list(cari.ADAPTER.collections(B()))


def test_blocked_from_page_render_propagates(fixture):
    class B(FakeFetcher):
        def render(self, url, **kw):
            raise Blocked("challenge")
    f = B(json={"page=1": fixture("cari/api1.json"), "page=": {"content": []}})
    with pytest.raises(Blocked):
        list(cari.ADAPTER.collections(f))


def test_page_fetch_error_yields_item_with_empty_description(fixture):
    f = make(fixture, pages={})     # every render raises FetchError
    colls = list(cari.ADAPTER.collections(f))
    items = [i for _, its in colls for i in its]
    assert items and all(i.meta["description"] == "" and i.meta["reference_images"] == [] for i in items)
    assert all(i.thumb_url.startswith("https://cari-prod.s3") for i in items)
    assert all(c.error for c, _ in colls)


def test_api_failure_with_no_entries_yields_errored_collection():
    class F(FakeFetcher):
        def get_json(self, url, params=None, headers=None):
            raise FetchError("api down")
    [(coll, items)] = list(cari.ADAPTER.collections(F()))
    assert items == [] and "api down" in coll.error
