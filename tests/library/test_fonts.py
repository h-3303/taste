from taste.library.fetch import FakeFetcher
from taste.library.sources import fontshare, fontsource, googlefonts


def test_googlefonts_collections(fixture):
    f = FakeFetcher(json={"metadata/fonts": fixture("googlefonts/metadata.json")})
    colls = {c.slug: items for c, items in googlefonts.ADAPTER.collections(f)}
    assert {"googlefonts/sans-serif", "googlefonts/display", "googlefonts/popular-100", "googlefonts/variable"} <= set(colls)
    it = colls["googlefonts/sans-serif"][0]
    assert it.kind == "font" and it.key.startswith("googlefonts:") and it.thumb_url is None
    assert it.page_url.startswith("https://fonts.google.com/specimen/")
    assert "weights" in it.meta and it.meta["css"].startswith("<link")
    pops = [i.meta["popularity"] for i in colls["googlefonts/popular-100"]]
    assert pops == sorted(pops)


def test_googlefonts_font_file_and_pluck(fixture, tmp_path):
    f = FakeFetcher(text={"fonts.googleapis.com/css?family=Space+Grotesk": fixture("googlefonts/css.txt")},
                    files={"fonts.gstatic.com": b"TTF"})
    item = {"id": "i", "key": "googlefonts:Space Grotesk", "title": "Space Grotesk", "meta": {"category": "Sans Serif"}, "page_url": "p"}
    p = googlefonts.ADAPTER.font_file(item, f, tmp_path)
    assert p.suffix == ".ttf" and p.read_bytes() == b"TTF"
    r = googlefonts.ADAPTER.pluck(item, f, tmp_path, {"weight": "400"})
    assert "family=Space+Grotesk" in r.text and "font-family" in r.text and r.path.suffix == ".ttf"


def test_fontsource_collections_and_pluck(fixture, tmp_path):
    fx = fixture("fontsource/display.json")
    f = FakeFetcher(json={"category=display": fx, "category=serif": [], "category=sans-serif": [], "category=monospace": [], "category=handwriting": []},
                    files={"cdn.jsdelivr.net/fontsource": b"WOFF"})
    colls = {c.slug: items for c, items in fontsource.ADAPTER.collections(f)}
    it = colls["fontsource/display"][0]
    assert it.key == f"fontsource:{fx[0]['id']}" and "npm i @fontsource/" in it.meta["install"]
    item = {"id": "i", "key": it.key, "title": it.title, "meta": it.meta, "page_url": it.page_url}
    assert fontsource.ADAPTER.font_file(item, f, tmp_path).suffix == ".woff"
    r = fontsource.ADAPTER.pluck(item, f, tmp_path, {})
    assert "@fontsource/" in r.text


def test_fontshare_collections_and_pluck(fixture, tmp_path):
    page = fixture("fontshare/page1.json"); page["has_more"] = False
    f = FakeFetcher(json={"v2/fonts": page}, text={"v2/css": fixture("fontshare/css.txt")}, files={"cdn.fontshare.com": b"TTF"})
    colls = {c.slug: items for c, items in fontshare.ADAPTER.collections(f)}
    it = next(i for items in colls.values() for i in items)
    assert it.key.startswith("fontshare:") and it.page_url.startswith("https://www.fontshare.com/fonts/")
    item = {"id": "i", "key": it.key, "title": it.title, "meta": it.meta, "page_url": it.page_url}
    assert fontshare.ADAPTER.font_file(item, f, tmp_path).suffix == ".ttf"
    assert "api.fontshare.com/v2/css" in fontshare.ADAPTER.pluck(item, f, tmp_path, {}).text


def test_googlefonts_values_and_weight_700(fixture, tmp_path):
    meta = fixture("googlefonts/metadata.json")["familyMetadataList"]
    f = FakeFetcher(json={"metadata/fonts": {"familyMetadataList": meta}})
    colls = {c.slug: items for c, items in googlefonts.ADAPTER.collections(f)}
    first = meta[0]
    it = next(i for i in colls["googlefonts/popular-100"] if i.key == f"googlefonts:{first['family']}")
    assert it.meta["popularity"] == first["popularity"] and it.meta["category"] == first["category"]
    assert it.title == first["family"] and it.meta["designers"] == first["designers"]
    assert len(colls["googlefonts/popular-100"]) == len(meta)
    var = [m["family"] for m in meta if m.get("axes")]
    assert [i.title for i in colls["googlefonts/variable"]] == sorted(var, key=lambda n: next(m["popularity"] for m in meta if m["family"] == n))
    ff = FakeFetcher(text={"family=Space+Grotesk:700": fixture("googlefonts/css.txt")}, files={"fonts.gstatic.com": b"TTF"})
    item = {"id": "i", "key": "googlefonts:Space Grotesk", "title": "Space Grotesk", "meta": {"category": "Sans Serif"}, "page_url": "p"}
    r = googlefonts.ADAPTER.pluck(item, ff, tmp_path, {"weight": "700"})
    assert "wght@700" in r.text and r.path.name == "space-grotesk-700.ttf" and "weight 700" in r.note


def test_fontshare_paginates(fixture, tmp_path):
    page = fixture("fontshare/page1.json")
    last = {**page, "fonts": page["fonts"][:1], "has_more": False}
    page["has_more"] = True
    f = FakeFetcher(json={"limit=100&offset=0": page, "limit=100&offset=100": last})
    items = [i for _, its in fontshare.ADAPTER.collections(f) for i in its]
    assert len(items) == len(page["fonts"]) + 1
    first = page["fonts"][0]
    got = next(i for i in items if i.key == f"fontshare:{first['slug']}")
    assert got.title == first["name"] and got.meta["views"] == first["views"]
