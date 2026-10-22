from taste.library.fetch import FakeFetcher
from taste.library.sources import archive


def test_pick_image_largest_jpeg_under_cap(fixture):
    url = archive.pick_image("rz_Groove_90", fixture("archive/metadata.json")["files"])
    assert url and url.startswith("https://archive.org/download/rz_Groove_90/")
    assert url == "https://archive.org/download/rz_Groove_90/__ia_thumb.jpg"
    assert archive.pick_image("x", [{"name": "a.jpg", "format": "JPEG", "size": "99999999"}]) is None


def test_collections(fixture):
    f = FakeFetcher(json={"advancedsearch.php": fixture("archive/search.json")})
    colls = list(archive.ADAPTER.collections(f))
    assert [c.slug for c, _ in colls] == ["archive/rave-zines", "archive/david-rumsey"]
    it = colls[0][1][0]
    assert it.key.startswith("archive:") and it.thumb_url.startswith("https://archive.org/services/img/")
    assert it.key == "archive:zine_atmosphere27" and it.title == "atmosphere27"
    assert it.page_url == "https://archive.org/details/zine_atmosphere27"
    assert it.thumb_url == "https://archive.org/services/img/zine_atmosphere27"
    assert it.asset_url == "https://archive.org/metadata/zine_atmosphere27"
    assert colls[0][0].policy == "manual" and archive.ADAPTER.info.policy == "manual" and archive.ADAPTER.info.tier == 1


def test_pluck(fixture, tmp_path):
    f = FakeFetcher(json={"metadata/rz_Groove_90": fixture("archive/metadata.json")}, files={"archive.org/download/": b"JPG"})
    r = archive.ADAPTER.pluck({"id": "i", "key": "archive:rz_Groove_90", "title": "Groove", "page_url": "p"}, f, tmp_path, {})
    assert r.path and r.path.read_bytes() == b"JPG"
