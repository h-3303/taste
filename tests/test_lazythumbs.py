import io
import json

from PIL import Image

from taste.lazythumbs import ensure_item_thumbs
from taste.library import db, search, sheet
from taste.library.fetch import Blocked, FakeFetcher, FetchError
from taste.library.models import CollectionDraft, ItemDraft, SourceInfo


def png_bytes():
    b = io.BytesIO()
    Image.new("RGB", (600, 400), (10, 200, 10)).save(b, "PNG")
    return b.getvalue()


class Scripted(FakeFetcher):
    """download() answers per URL substring: bytes, or an exception to raise."""

    def download(self, url, dest, headers=None):
        for k, v in self.files.items():
            if k in url:
                if isinstance(v, Exception):
                    raise v
                return super().download(url, dest, headers)
        raise FetchError(f"fake: no file for {url}")


def _seed(tmp_path, specs):
    conn = db.connect(tmp_path / "t.db")
    db.upsert_source(conn, SourceInfo("gal", "Gal", "https://g.test", 1))
    cid = db.upsert_collection(conn, "gal", CollectionDraft("gal/all", "site", "All"))
    ids = []
    for key, asset, meta in specs:
        iid, _ = db.upsert_item(conn, "gal", ItemDraft(key, "image", f"Garden {key}", f"https://g.test/{key}", asset,
                                                       meta={"shipping": "link", **meta}), cid, "2026-01-01")
        ids.append(iid)
    return conn, ids


def _three(tmp_path):
    conn, ids = _seed(tmp_path, [("gal:ok", "https://cdn.g.test/ok.jpg", {}),
                                 ("gal:gone", "https://cdn.g.test/gone.jpg", {}),
                                 ("gal:slow", "https://cdn.g.test/slow.jpg", {})])
    f = Scripted(files={"/ok.jpg": png_bytes(), "/gone.jpg": FetchError("x: HTTP 404", status=404),
                        "/slow.jpg": FetchError("x: timed out")})
    return conn, ids, f


def test_fetch_dead_and_timeout(tmp_path):
    conn, (ok, gone, slow), f = _three(tmp_path)
    td = tmp_path / "thumbs"
    out = ensure_item_thumbs(conn, [ok, gone, slow], f, td)
    assert out[ok] == td / f"{ok}.jpg" and out[ok].exists()
    assert db.get_item(conn, ok)["thumb"] == f"thumbs/{ok}.jpg"
    assert out[gone] is None and db.get_item(conn, gone)["meta"]["dead"] is True
    assert out[slow] is None
    row = db.get_item(conn, slow)
    assert row["thumb"] is None and not row["meta"].get("dead")


def test_dead_hidden_from_search(tmp_path):
    conn, (ok, gone, slow), f = _three(tmp_path)
    ensure_item_thumbs(conn, [ok, gone, slow], f, tmp_path / "thumbs")
    got = {r["id"] for r in search.search(conn, "garden")}
    assert got == {ok, slow}


def test_410_and_non_image_body_are_dead(tmp_path):
    conn, (a, b) = _seed(tmp_path, [("gal:a", "https://cdn.g.test/a.jpg", {}), ("gal:b", "https://cdn.g.test/b.jpg", {})])[:2]
    f = Scripted(files={"/a.jpg": FetchError("HTTP 410", status=410), "/b.jpg": b"<html>not an image</html>"})
    out = ensure_item_thumbs(conn, [a, b], f, tmp_path / "thumbs")
    assert out == {a: None, b: None}
    assert db.get_item(conn, a)["meta"]["dead"] and db.get_item(conn, b)["meta"]["dead"]


def test_5xx_leaves_row_alone(tmp_path):
    conn, (a,) = _seed(tmp_path, [("gal:a", "https://cdn.g.test/a.jpg", {})])[:2]
    f = Scripted(files={"/a.jpg": FetchError("HTTP 503", status=503)})
    assert ensure_item_thumbs(conn, [a], f, tmp_path / "thumbs") == {a: None}
    assert not db.get_item(conn, a)["meta"].get("dead")


def test_no_image_url_is_not_dead_and_not_fetched(tmp_path):
    conn, (a,) = _seed(tmp_path, [("gal:a", "", {})])[:2]
    f = Scripted()
    assert ensure_item_thumbs(conn, [a], f, tmp_path / "thumbs") == {a: None}
    assert f.calls == [] and not db.get_item(conn, a)["meta"].get("dead")


def test_meta_thumb_url_is_used(tmp_path):
    conn, (a,) = _seed(tmp_path, [("gal:a", "", {"thumb_url": "https://cdn.g.test/t.png"})])[:2]
    out = ensure_item_thumbs(conn, [a], Scripted(files={"/t.png": png_bytes()}), tmp_path / "thumbs")
    assert out[a].exists()


def test_rows_with_thumb_are_skipped(tmp_path):
    conn, (a,) = _seed(tmp_path, [("gal:a", "https://cdn.g.test/a.jpg", {})])[:2]
    db.set_thumb(conn, a, f"thumbs/{a}.jpg", None)
    f = Scripted(files={"/a.jpg": png_bytes()})
    out = ensure_item_thumbs(conn, [a], f, tmp_path / "thumbs")
    assert f.calls == [] and out[a] == tmp_path / "thumbs" / f"{a}.jpg"


def test_blocked_stops_that_host_only(tmp_path):
    conn, _ids = _seed(tmp_path, [("gal:a", "https://cdn.g.test/a.jpg", {}),
                                  ("gal:b", "https://cdn.g.test/b.jpg", {}),
                                  ("gal:c", "https://other.test/c.jpg", {})])
    byurl = {r["asset_url"]: r["id"] for r in db.items_without_thumb(conn)}
    a, b, c = (byurl[u] for u in ("https://cdn.g.test/a.jpg", "https://cdn.g.test/b.jpg", "https://other.test/c.jpg"))
    f = Scripted(files={"/a.jpg": Blocked("HTTP 429"), "/b.jpg": png_bytes(), "/c.jpg": png_bytes()})
    out = ensure_item_thumbs(conn, [a, b, c], f, tmp_path / "thumbs")
    assert out[a] is None and out[b] is None and out[c] is not None
    assert not any("b.jpg" in u for _, u in f.calls)
    assert not db.get_item(conn, a)["meta"].get("dead")


def test_sheet_draws_live_items_without_crashing(tmp_path):
    conn, (ok, gone, slow), f = _three(tmp_path)
    rows = [db.get_item(conn, i) for i in (ok, gone, slow)]
    td = tmp_path / "data" / "thumbs"
    paths = sheet.contact_sheets(rows, tmp_path / "data", tmp_path / "out", cols=2, cell=100,
                                 conn=conn, fetch=f, thumbs_dir=td)
    assert len(paths) == 1
    with Image.open(paths[0]) as im:
        assert im.size == (200, 100)   # two tiles on one row: the dead one is not drawn
    assert db.get_item(conn, gone)["meta"]["dead"] is True


def test_local_oserror_is_not_dead(tmp_path, monkeypatch):
    conn, (a,) = _seed(tmp_path, [("gal:a", "https://cdn.g.test/a.jpg", {})])[:2]
    def boom(*_a, **_k):
        raise PermissionError("thumbs dir not writable")
    monkeypatch.setattr("taste.library.thumbs.make_thumb", boom)
    assert ensure_item_thumbs(conn, [a], Scripted(files={"/a.jpg": png_bytes()}), tmp_path / "thumbs") == {a: None}
    assert not db.get_item(conn, a)["meta"].get("dead")


def test_200_challenge_page_is_blocked_not_dead(tmp_path):
    conn, _ids = _seed(tmp_path, [("gal:a", "https://cdn.g.test/a.jpg", {}), ("gal:b", "https://cdn.g.test/b.jpg", {})])
    a, b = (r["id"] for r in db.items_without_thumb(conn))
    html = b"<html><head><title>Just a moment...</title></head><body>wait</body></html>"
    f = Scripted(files={"/a.jpg": html, "/b.jpg": png_bytes()})
    out = ensure_item_thumbs(conn, [a, b], f, tmp_path / "thumbs")
    assert out == {a: None, b: None}
    assert not db.get_item(conn, a)["meta"].get("dead")
    assert [u for _, u in f.calls] == ["https://cdn.g.test/a.jpg"]   # host blocked for the rest of the call
