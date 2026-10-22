import copy

from taste.library.fetch import FakeFetcher
from taste.library.sources import github_data, lospec


def _lospec_fetcher(page, page1=None):
    json = {"colorNumber=8&page=0": page}
    if page1 is not None:
        json["colorNumber=8&page=1"] = page1
    json["page="] = {"palettes": []}
    return FakeFetcher(json=json)


def test_lospec_items(fixture):
    page = fixture("lospec/page0.json")
    colls = list(lospec.ADAPTER.collections(_lospec_fetcher(page)))
    coll, items = next((c, i) for c, i in colls if c.slug == "lospec/8-colours")
    it = items[0]
    p0 = page["palettes"][0]
    assert it.kind == "palette" and it.key == f"lospec:{p0['slug']}"
    assert all(c.startswith("#") and len(c) == 7 for c in it.meta["colors"]) and it.meta["count"] == 8
    assert it.page_url == f"https://lospec.com/palette-list/{p0['slug']}"
    assert "<a" not in it.meta.get("author", "")


def test_lospec_values_from_fixture(fixture):
    page = fixture("lospec/page0.json")
    _, items = next((c, i) for c, i in lospec.ADAPTER.collections(_lospec_fetcher(page)) if c.slug == "lospec/8-colours")
    assert len(items) == len(page["palettes"]) == 10
    for it, p in zip(items, page["palettes"]):
        assert it.key == f"lospec:{p['slug']}"
        assert it.title == p["title"]
        assert it.meta["colors"] == ["#" + c.lower() for c in p["colors"]]
        assert it.meta["count"] == len(p["colors"])
        assert it.tags == [t for t in p["tags"] if isinstance(t, str)]
        assert it.meta["author"] == (p.get("user") or {}).get("name", "")
    first = items[0]
    assert first.title == "Limets" and first.meta["colors"][0] == "#000000" and first.meta["colors"][3] == "#ff3d81"
    assert first.tags == ["limitedpalette", "3bit"]
    # the description carrying an <a> tag is stripped of markup
    html = next(it for it, p in zip(items, page["palettes"]) if "<a" in (p.get("description") or ""))
    assert "<" not in html.meta["description"] and ">" not in html.meta["description"]


def test_lospec_paginates_and_stops_on_empty_page(fixture):
    page = fixture("lospec/page0.json")
    page1 = copy.deepcopy(page)
    for i, p in enumerate(page1["palettes"]):
        p["slug"] = f"second-{i}"
    f = _lospec_fetcher(page, page1)
    colls = {c.slug: items for c, items in lospec.ADAPTER.collections(f)}
    assert list(colls) == ["lospec/8-colours"]            # every other colour count came back empty and is skipped
    keys = [i.key for i in colls["lospec/8-colours"]]
    assert len(keys) == 20 and keys[10] == "lospec:second-0" and keys[-1] == "lospec:second-9"
    assert len(set(keys)) == 20


def test_lospec_collection_slugs(fixture):
    page = fixture("lospec/page0.json")
    f = FakeFetcher(json={"page=": page})                  # every count and page returns the same data
    colls = list(lospec.ADAPTER.collections(f))
    assert [c.slug for c, _ in colls] == [f"lospec/{n}-colours" for n in (2, 3, 4, 5, 6, 8, 12, 16, 24, 32, 48, 64)]
    assert all(len(i) == 10 * lospec.PAGES for _, i in colls)


def test_github_datasets(fixture):
    f = FakeFetcher(json={"nice-color-palettes": fixture("github_data/nice.json"), "uiGradients": fixture("github_data/uigradients.json")})
    colls = {c.slug: items for c, items in github_data.ADAPTER.collections(f)}
    nice = colls["github-data/nice-color-palettes"][0]
    assert nice.key == "github-data:nice:0" and len(nice.meta["colors"]) == 5
    grad = colls["github-data/uigradients"][0]
    assert grad.meta["css"].startswith("linear-gradient(90deg, #") and grad.title == "Omolon"


def test_github_dataset_values(fixture):
    nice_raw, uig_raw = fixture("github_data/nice.json"), fixture("github_data/uigradients.json")
    f = FakeFetcher(json={"nice-color-palettes": nice_raw, "uiGradients": uig_raw})
    colls = {c.slug: items for c, items in github_data.ADAPTER.collections(f)}
    nice = colls["github-data/nice-color-palettes"]
    assert len(nice) == 20 and nice[7].key == "github-data:nice:7"
    assert nice[7].meta["colors"] == [c.lower() for c in nice_raw[7]] and nice[7].license == "MIT"
    grads = colls["github-data/uigradients"]
    assert len(grads) == 10
    # css is built exactly from the fixture colours, lowercased, in order
    assert grads[0].meta["css"] == "linear-gradient(90deg, #091e3a, #2f80ed, #2d9ee0)"
    assert grads[1].meta["css"] == "linear-gradient(90deg, #9400d3, #4b0082)"
    for g, raw in zip(grads, uig_raw):
        assert g.meta["css"] == f"linear-gradient(90deg, {', '.join(c.lower() for c in raw['colors'])})"
        assert g.meta["colors"] == [c.lower() for c in raw["colors"]] and g.license == "MIT"
    assert grads[3].key == "github-data:uigradients:ibtesam"
    assert any(g.key == "github-data:uigradients:radioactive-heat" for g in grads)
