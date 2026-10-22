import pytest

from taste.library import db, pluck
from taste.library.fetch import FakeFetcher, FetchError
from taste.library.models import CollectionDraft, ItemDraft, SourceInfo
from taste.library.sources import base


def seed(tmp_path, draft: ItemDraft, source="s", tier=1):
    conn = db.connect(tmp_path / "t.db")
    db.upsert_source(conn, SourceInfo(source, source, "https://s", tier))
    c = db.upsert_collection(conn, source, CollectionDraft(f"{source}/c", draft.kind, "c"))
    iid, _ = db.upsert_item(conn, source, draft, c, "t")
    return conn, iid


def test_pluck_palette_writes_hex_and_gpl(tmp_path):
    conn, iid = seed(tmp_path, ItemDraft("s:p", "palette", "Rust", "https://s/p", "https://s/p.hex", meta={"colors": ["#230000", "#e18866"]}))
    r = pluck.pluck(conn, iid, FakeFetcher(), tmp_path / "out", {})
    assert r.text == "#230000\n#e18866" and (tmp_path / "out" / f"{iid}.gpl").read_text().startswith("GIMP Palette")
    assert r.path == tmp_path / "out" / f"{iid}.hex"


def test_pluck_snippet_writes_code(tmp_path):
    conn, iid = seed(tmp_path, ItemDraft("s:c", "snippet", "Beam", "https://s/c", "https://raw/x.tsx", meta={"code": "export const a = 1;", "language": "tsx"}))
    r = pluck.pluck(conn, iid, FakeFetcher(), tmp_path / "out", {})
    assert r.path.suffix == ".tsx" and r.text == "export const a = 1;"


def test_pluck_image_downloads(tmp_path):
    conn, iid = seed(tmp_path, ItemDraft("s:i", "image", "Pic", "https://s/i", "https://cdn/pic.jpg?w=1600"))
    r = pluck.pluck(conn, iid, FakeFetcher(files={"cdn/pic.jpg": b"JPG"}), tmp_path / "out", {})
    assert r.path == tmp_path / "out" / f"{iid}.jpg" and r.path.read_bytes() == b"JPG"


def test_pluck_dead_url_cleans_up(tmp_path):
    conn, iid = seed(tmp_path, ItemDraft("s:d", "image", "Dead", "https://s/d", "https://cdn/dead.jpg"))
    with pytest.raises(FetchError):
        pluck.pluck(conn, iid, FakeFetcher(), tmp_path / "out", {})
    assert not list((tmp_path / "out").glob("*")) if (tmp_path / "out").exists() else True


def test_pluck_delegates_to_adapter(tmp_path, monkeypatch):
    from taste.library.models import PluckResult
    class A:
        info = SourceInfo("s", "s", "https://s", 1)
        def collections(self, fetch): yield from ()
        def pluck(self, item, fetch, dest_dir, opts):
            return PluckResult(item["id"], None, "adapter did it", "")
    monkeypatch.setattr(base, "REGISTRY", {"s": A()})
    conn, iid = seed(tmp_path, ItemDraft("s:x", "texture", "T", "https://s/x", "https://s/x"))
    assert pluck.pluck(conn, iid, FakeFetcher(), tmp_path / "out", {}).text == "adapter did it"


def test_pluck_records_cache(tmp_path):
    from taste.library import cache
    conn, iid = seed(tmp_path, ItemDraft("s:i", "image", "Pic", "https://s/i", "https://cdn/pic.jpg"))
    root = tmp_path / "cache"
    pluck.pluck(conn, iid, FakeFetcher(files={"cdn/pic.jpg": b"JPG"}), root, {}, cache_root=root)
    assert cache.size(conn) == 3
