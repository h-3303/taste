import pytest

from taste.library.fetch import Blocked, FakeFetcher
from taste.library.sources import snapshots


def test_parse_images_filters_and_caps(fixture):
    urls = snapshots.parse_images(fixture("snapshots/generic.html"))
    assert len(urls) == 10 and not any("avatar" in u or "logo" in u or u.startswith("data:") for u in urls)
    assert len(snapshots.parse_images("".join(f'<img src="https://c/{i}.jpg">' for i in range(100)))) == 60


def test_codepen_items(fixture):
    f = FakeFetcher(pages={"codepen.io/search": fixture("snapshots/generic.html")})
    coll, items = next(snapshots.CODEPEN.collections(f))
    assert coll.slug == "codepen/neumorphism" and coll.policy == "snapshot"
    assert {i.key for i in items} == {"codepen:alice/abc123", "codepen:bob/def456"}
    assert items[0].thumb_url.startswith("https://shots.codepen.io/") and items[0].kind == "snippet"


def test_codepen_has_no_pluck_override():
    assert not hasattr(snapshots.CODEPEN, "pluck")
    assert not hasattr(snapshots.BEHANCE, "pluck")


def test_behance_render_is_stealth(fixture):
    seen = {}
    class F(FakeFetcher):
        def render(self, url, wait=6, stealth=False, obey_robots=True, timeout=40):
            seen.update(stealth=stealth, robots=obey_robots)
            return fixture("snapshots/generic.html")
    coll, items = next(snapshots.BEHANCE.collections(F()))
    assert seen == {"stealth": True, "robots": False} and len(items) == 10 and items[0].kind == "image"
    assert snapshots.BEHANCE.info.tier == 3 and snapshots.BEHANCE.info.policy == "snapshot"


def test_blocked_propagates():
    class F(FakeFetcher):
        def render(self, url, **kw):
            raise Blocked("Cloudflare challenge")
    with pytest.raises(Blocked):
        next(snapshots.DRIBBBLE.collections(F()))


def test_pinterest_asset_is_upsized_thumb_kept():
    class F(FakeFetcher):
        def render(self, url, **kw):
            return '<img src="https://i.pinimg.com/75x75_RS/ab/cd/ef.jpg"><img src="https://cdn.example/x.jpg">'
    _, items = next(snapshots.PINTEREST.collections(F()))
    assert items[0].asset_url == "https://i.pinimg.com/736x/ab/cd/ef.jpg"
    assert items[0].thumb_url == "https://i.pinimg.com/75x75_RS/ab/cd/ef.jpg"
    assert items[1].asset_url == "https://cdn.example/x.jpg"
