from taste.library.fetch import Blocked, FakeFetcher, FetchError
from taste.library.sources import galleries_img as g
from taste.library.vocabulary import TERMS, term_slug

COSMOS_FIRST = "7931119e-2598-4609-9a9b-0c3f4accc092"
DSP_FIRST = "7d/6e/25/7d6e2531a72faa2c3add8d2d4e2f9006.jpg"
SAVEE_FIRST = "6ab62d063c9caf40b5a17ce5"


def test_parse_cosmos(fixture):
    ids = g.parse_cosmos(fixture("galleries_img/cosmos.html"))
    assert len(ids) >= 5 and len(ids) == len(set(ids)) and all("/" not in i and "?" not in i for i in ids)
    assert ids[0] == COSMOS_FIRST


def test_parse_designspiration(fixture):
    paths = g.parse_designspiration(fixture("galleries_img/designspiration.html"))
    assert len(paths) >= 5 and all(p.endswith((".jpg", ".png", ".gif", ".jpeg")) for p in paths)
    assert paths[0] == DSP_FIRST and len(paths) == len(set(paths))


def test_parse_savee(fixture):
    ids = g.parse_savee(fixture("galleries_img/savee.html"))
    assert len(ids) >= 5 and all(len(i) == 24 for i in ids)
    assert ids[0] == SAVEE_FIRST and len(ids) == len(set(ids))


def test_parsers_return_empty_on_empty_page():
    assert g.parse_cosmos("") == g.parse_designspiration("") == g.parse_savee("") == []


def test_cosmos_collections_per_term(fixture):
    f = FakeFetcher(pages={"cosmos.so/search/elements/": fixture("galleries_img/cosmos.html")})
    colls = list(g.COSMOS.collections(f))
    assert len(colls) == len(TERMS) and colls[0][0].slug == "cosmos/neumorphism"
    coll, items = colls[0]
    it = items[0]
    assert it.key == f"cosmos:{COSMOS_FIRST}"
    assert it.asset_url == f"https://cdn.cosmos.so/{COSMOS_FIRST}?format=jpeg&w=1600"
    assert it.thumb_url == f"https://cdn.cosmos.so/{COSMOS_FIRST}?format=jpeg&w=400"
    assert it.page_url == "https://www.cosmos.so/search/elements/neumorphism" and it.meta["term"] == "neumorphism"
    assert f.calls[0] == ("render", "https://www.cosmos.so/search/elements/neumorphism")


def test_collection_language_and_slug_follow_term(fixture):
    f = FakeFetcher(pages={"cosmos.so/search/elements/": fixture("galleries_img/cosmos.html")})
    for (coll, _), term in zip(g.COSMOS.collections(f), TERMS):
        assert coll.slug == f"cosmos/{term_slug(term)}" and coll.languages == [term] and coll.query == term
    # a multi-word term is slugged and its page url is percent-encoded
    multi = next(t for t in TERMS if " " in t)
    colls = {c.query: c for c, _ in g.COSMOS.collections(f)}
    assert colls[multi].slug == "cosmos/" + term_slug(multi) and " " not in colls[multi].slug
    assert ("render", "https://www.cosmos.so/search/elements/" + multi.replace(" ", "%20")) in f.calls


def test_term_error_yields_empty_but_blocked_propagates():
    class F(FakeFetcher):
        def render(self, url, **kw):
            if "neumorphism" in url:
                raise FetchError("boom")
            if "glassmorphism" in url:
                raise Blocked("challenge")
            return ""
    gen = g.COSMOS.collections(F())
    coll, items = next(gen)
    assert coll.slug == "cosmos/neumorphism" and items == [] and "boom" in coll.error
    try:
        next(gen)
        assert False, "Blocked should propagate"
    except Blocked:
        pass


def test_designspiration_item_shape(fixture):
    f = FakeFetcher(pages={"designspiration.com": fixture("galleries_img/designspiration.html")})
    coll, items = next(g.DESIGNSPIRATION.collections(f))
    it = items[0]
    assert coll.slug == f"designspiration/{term_slug(TERMS[0])}"
    assert it.key == "designspiration:414215ca1ef68ee6"
    assert it.asset_url == f"https://dspncdn.com/a1/media/692x/{DSP_FIRST}"
    assert it.thumb_url == f"https://dspncdn.com/a1/media/236x/{DSP_FIRST}"
    assert it.page_url == f"https://www.designspiration.com/search/saves/?q={TERMS[0]}"


def test_savee_item_shape(fixture):
    f = FakeFetcher(pages={"savee.it": fixture("galleries_img/savee.html")})
    coll, items = next(g.SAVEE.collections(f))
    it = items[0]
    assert it.asset_url == it.thumb_url == f"https://dm.savee-cdn.com/asset-image/w420/{SAVEE_FIRST}.jpg"
    assert it.key == f"savee:{SAVEE_FIRST}" and coll.slug == f"savee/{term_slug(TERMS[0])}"
