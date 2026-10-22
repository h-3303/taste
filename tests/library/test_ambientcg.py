from taste.library.fetch import FakeFetcher
from taste.library.sources import ambientcg


def test_items_from_page(fixture):
    page = fixture("ambientcg/page1.json")
    page["nextPageHttp"] = None
    f = FakeFetcher(json={"type=Material": page, "type=Decal": {"foundAssets": [], "nextPageHttp": None}})
    colls = list(ambientcg.ADAPTER.collections(f))
    assert colls and all(c.slug.startswith("ambientcg/") for c, _ in colls)
    it = [i for _, items in colls for i in items][0]
    assert it.key.startswith("ambientcg:") and it.kind == "texture" and it.license == "CC0"
    assert it.thumb_url.endswith(".png") and "512-PNG" in it.thumb_url
    assert it.page_url.startswith("https://ambientcg.com/view?id=")
    assert it.meta["zips"]           # attribute -> url map


def test_pluck_default_2k(fixture, tmp_path):
    page = fixture("ambientcg/page1.json")
    a = page["foundAssets"][0]
    zips = {z["attribute"]: z["downloadLink"] for z in a["downloadFolders"]["default"]["downloadFiletypeCategories"]["zip"]["downloads"]}
    item = {"id": "x", "key": f"ambientcg:{a['assetId']}", "title": a["assetId"], "meta": {"zips": zips}}
    want = next(u for k, u in zips.items() if k == "2K-JPG")
    f = FakeFetcher(files={want: b"ZIP"})
    r = ambientcg.ADAPTER.pluck(item, f, tmp_path, {})
    assert r.path.name.endswith("_2K-JPG.zip") and r.path.read_bytes() == b"ZIP"


def _first_asset(fixture):
    page = fixture("ambientcg/page1.json")
    page["nextPageHttp"] = None
    return page, page["foundAssets"][0]


def test_first_asset_values(fixture):
    from taste.library.vocabulary import slugify
    page, a = _first_asset(fixture)
    f = FakeFetcher(json={"type=Material": page, "type=Decal": {"foundAssets": [], "nextPageHttp": None}})
    colls = list(ambientcg.ADAPTER.collections(f))
    coll, items = next((c, i) for c, i in colls if c.slug == f"ambientcg/{slugify(a['displayCategory'])}")
    it = next(i for i in items if i.key == f"ambientcg:{a['assetId']}")
    zips = {z["attribute"]: z["downloadLink"] for z in a["downloadFolders"]["default"]["downloadFiletypeCategories"]["zip"]["downloads"]}
    assert it.asset_url == zips["2K-JPG"]
    assert it.thumb_url == a["previewImage"]["512-PNG"]
    assert "096" in a["tags"] and not any(t.isdigit() for t in it.tags) and "wood" in it.tags


def test_pagination_follows_next_page():
    class Paged(FakeFetcher):
        def get_json(self, url, params=None, headers=None):
            self.calls.append(("get_json", url))
            if params["type"] == "Decal":
                return {"foundAssets": [], "nextPageHttp": None}
            a = lambda n: {"assetId": n, "displayCategory": "Wood"}
            if params["offset"] == 0:
                return {"foundAssets": [a("A1"), a("A2")], "nextPageHttp": "next"}
            assert params["offset"] == 2
            return {"foundAssets": [a("A3")], "nextPageHttp": None}

    f = Paged()
    items = [i for _, its in ambientcg.ADAPTER.collections(f) for i in its]
    assert sorted(i.key for i in items) == ["ambientcg:A1", "ambientcg:A2", "ambientcg:A3"]
    assert len(f.calls) == 3          # two Material pages + one Decal


def test_pluck_respects_res_and_falls_back(tmp_path):
    zips = {"2K-JPG": "https://x.test/get?file=Wood096_2K-JPG.zip", "4K-JPG": "https://x.test/get?file=Wood096_4K-JPG.zip"}
    item = {"id": "x", "key": "ambientcg:Wood096", "meta": {"zips": zips}}
    f = FakeFetcher(files={zips["4K-JPG"]: b"FOUR"})
    r = ambientcg.ADAPTER.pluck(item, f, tmp_path, {"res": "4k"})
    assert r.path.name.endswith("_4K-JPG.zip") and r.path.read_bytes() == b"FOUR"

    only = {"1K-JPG": "https://x.test/get?file=Wood096_1K-JPG.zip"}
    f2 = FakeFetcher(files={only["1K-JPG"]: b"ONE"})
    r2 = ambientcg.ADAPTER.pluck({"id": "x", "key": "ambientcg:Wood096", "meta": {"zips": only}}, f2, tmp_path, {"res": "8k"})
    assert r2.path.name.endswith("_1K-JPG.zip") and r2.path.read_bytes() == b"ONE"
