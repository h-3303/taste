from pathlib import Path

from taste.library.fetch import FakeFetcher
from taste.library.sources import polyhaven


def test_collections_group_by_category(fixture):
    f = FakeFetcher(json={"assets?type=textures": fixture("polyhaven/assets.json"),
                          "categories/textures": fixture("polyhaven/categories.json")})
    colls = list(polyhaven.ADAPTER.collections(f))
    slugs = [c.slug for c, _ in colls]
    assert "polyhaven/all" not in slugs and "polyhaven/outdoor" in slugs
    coll, items = next((c, i) for c, i in colls if c.slug == "polyhaven/asphalt")
    it = items[0]
    assert it.key == "polyhaven:aerial_asphalt_01" and it.kind == "texture" and it.license == "CC0"
    assert it.page_url == "https://polyhaven.com/a/aerial_asphalt_01"
    assert it.thumb_url.startswith("https://cdn.polyhaven.com/asset_img/thumbs/aerial_asphalt_01.png")
    assert "cracked" in it.tags and it.meta["max_resolution"] == [8192, 8192]


def test_collections_sorted_largest_first(fixture):
    f = FakeFetcher(json={"assets?type=textures": fixture("polyhaven/assets.json"),
                          "categories/textures": fixture("polyhaven/categories.json")})
    slugs = [c.slug for c, _ in polyhaven.ADAPTER.collections(f)]
    assert slugs[0] == "polyhaven/outdoor"          # biggest category (after 'all') comes first → sample takes the big ones


def test_pluck_picks_map_and_res(fixture, tmp_path):
    f = FakeFetcher(json={"files/aerial_asphalt_01": fixture("polyhaven/files.json")},
                    files={"aerial_asphalt_01_diff_2k.jpg": b"JPEGDATA"})
    item = {"id": "abc", "key": "polyhaven:aerial_asphalt_01", "title": "Aerial Asphalt 01", "meta": {}}
    r = polyhaven.ADAPTER.pluck(item, f, tmp_path, {"map": "diffuse", "res": "2k"})
    assert r.path == tmp_path / "aerial_asphalt_01_diff_2k.jpg" and r.path.read_bytes() == b"JPEGDATA"
    assert "CC0" in r.note


def _colls(fixture):
    f = FakeFetcher(json={"assets?type=textures": fixture("polyhaven/assets.json"),
                          "categories/textures": fixture("polyhaven/categories.json")})
    return {c.slug: i for c, i in polyhaven.ADAPTER.collections(f)}


def test_item_values_and_ordering(fixture):
    colls = _colls(fixture)
    it = next(i for i in colls["polyhaven/asphalt"] if i.key == "polyhaven:aerial_asphalt_01")
    assert it.meta["authors"] == ["Rob Tuytel"] and it.meta["category_path"].startswith("Asphalt")
    counts = [i.meta["download_count"] for i in colls["polyhaven/outdoor"]]
    assert len(counts) > 1 and counts == sorted(counts, reverse=True)


def test_pluck_normal_1k(fixture, tmp_path):
    files = fixture("polyhaven/files.json")
    url = files["nor_gl"]["1k"]["jpg"]["url"]
    f = FakeFetcher(json={"files/aerial_asphalt_01": files}, files={url: b"NOR"})
    item = {"id": "abc", "key": "polyhaven:aerial_asphalt_01", "meta": {}}
    r = polyhaven.ADAPTER.pluck(item, f, tmp_path, {"map": "normal", "res": "1k"})
    assert r.path.name.endswith("_nor_gl_1k.jpg") and r.path.read_bytes() == b"NOR"
    assert ("download", url) in f.calls


def test_pluck_unknown_map_lists_available(fixture, tmp_path):
    import pytest
    f = FakeFetcher(json={"files/aerial_asphalt_01": fixture("polyhaven/files.json")})
    item = {"id": "abc", "key": "polyhaven:aerial_asphalt_01", "meta": {}}
    with pytest.raises(ValueError, match="Diffuse"):
        polyhaven.ADAPTER.pluck(item, f, tmp_path, {"map": "bogus"})
