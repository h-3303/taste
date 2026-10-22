from pathlib import Path

from PIL import Image

from taste.library import db, sync
from taste.library.fetch import Blocked, FakeFetcher, FetchError
from taste.library.models import CollectionDraft, ItemDraft, SourceInfo


def png_bytes():
    import io
    b = io.BytesIO()
    Image.new("RGB", (600, 400), (10, 200, 10)).save(b, "PNG")
    return b.getvalue()


class Good:
    info = SourceInfo("good", "Good", "https://g.test", 1)

    def __init__(self, n_coll=5, n_items=30):
        self.n_coll, self.n_items = n_coll, n_items

    def collections(self, fetch):
        for c in range(self.n_coll):
            items = [ItemDraft(f"good:{c}-{i}", "image", f"Item {c}-{i}", f"https://g.test/{c}/{i}",
                               f"https://cdn.g.test/{c}/{i}.jpg", thumb_url=f"https://cdn.g.test/t/{c}-{i}.png")
                     for i in range(self.n_items)]
            yield CollectionDraft(f"good/c{c}", "image", f"Good {c}"), items


class Flaky:
    info = SourceInfo("flaky", "Flaky", "https://f.test", 2)

    def collections(self, fetch):
        yield CollectionDraft("flaky/ok", "image", "ok"), [ItemDraft("flaky:1", "image", "One", "https://f.test/1", "https://cdn.f.test/1.jpg")]
        raise FetchError("second page exploded")


class Walled:
    info = SourceInfo("walled", "Walled", "https://w.test", 3, policy="snapshot")

    def collections(self, fetch):
        fetch.render("https://w.test/search")
        yield CollectionDraft("walled/x", "image", "x"), []


class Palettes:
    info = SourceInfo("pal", "Pal", "https://p.test", 1)

    def collections(self, fetch):
        yield CollectionDraft("pal/all", "palette", "All"), [
            ItemDraft("pal:1", "palette", "Rust", "https://p.test/1", "https://p.test/1.hex", meta={"colors": ["#230000", "#e18866"]})]


def _fetch():
    return FakeFetcher(files={"cdn.g.test/": png_bytes(), "cdn.f.test/": png_bytes()})


def test_sample_caps_collections_and_items(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    rep = sync.sync(conn, [Good()], _fetch(), tmp_path / "thumbs", sync.SyncOptions(sample=True), log=lambda *_: None)
    assert rep.sources["good"]["collections"] == 3 and rep.sources["good"]["new"] == 72
    assert db.stats(conn)["items"] == 72 and db.stats(conn)["thumbs"] == 72
    assert len(list((tmp_path / "thumbs").glob("*.jpg"))) == 72
    assert db.get_item(conn, db.query_items(conn, None, limit=1)[0]["id"])["thumb"].startswith("thumbs/")


def test_full_mode_takes_everything(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    rep = sync.sync(conn, [Good(2, 30)], _fetch(), tmp_path / "thumbs", sync.SyncOptions(sample=False), log=lambda *_: None)
    assert rep.sources["good"]["new"] == 60


def test_sync_is_idempotent(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    f = _fetch()
    sync.sync(conn, [Good(1, 3)], f, tmp_path / "thumbs", sync.SyncOptions(), log=lambda *_: None)
    n_calls = len(f.calls)
    rep = sync.sync(conn, [Good(1, 3)], f, tmp_path / "thumbs", sync.SyncOptions(), log=lambda *_: None)
    assert rep.sources["good"]["new"] == 0 and rep.sources["good"]["seen"] == 3
    assert db.stats(conn)["items"] == 3 and len(list((tmp_path / "thumbs").glob("*.jpg"))) == 3
    assert len(f.calls) == n_calls          # thumbnails not downloaded again


def test_sync_records_adapter_error_and_continues(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    rep = sync.sync(conn, [Flaky(), Good(1, 2)], _fetch(), tmp_path / "thumbs", sync.SyncOptions(), log=lambda *_: None)
    assert db.get_collection(conn, "flaky/ok")["item_count"] == 1
    assert any("second page exploded" in x for x in rep.sources["flaky"]["failures"])
    assert rep.sources["good"]["new"] == 2
    assert "second page exploded" in (conn.execute("SELECT error FROM sources WHERE slug='flaky'").fetchone()[0] or "")


def test_sync_blocked_source_stops(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    class F(FakeFetcher):
        def render(self, url, **kw):
            raise Blocked(f"{url}: bot challenge")
    rep = sync.sync(conn, [Walled()], F(), tmp_path / "thumbs", sync.SyncOptions(snapshot=True), log=lambda *_: None)
    assert rep.sources["walled"]["blocked"] and db.stats(conn)["items"] == 0
    assert "challenge" in conn.execute("SELECT error FROM sources WHERE slug='walled'").fetchone()[0]


def test_tier3_needs_snapshot_flag(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    rep = sync.sync(conn, [Walled()], FakeFetcher(), tmp_path / "thumbs", sync.SyncOptions(), log=lambda *_: None)
    assert rep.sources["walled"]["failures"] == ["tier 3 source skipped: pass --snapshot to catalogue it once"]


def test_palette_gets_swatch_without_download(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    f = FakeFetcher()
    sync.sync(conn, [Palettes()], f, tmp_path / "thumbs", sync.SyncOptions(), log=lambda *_: None)
    assert db.stats(conn)["thumbs"] == 1 and f.calls == []


def test_thumb_failure_keeps_item(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    rep = sync.sync(conn, [Good(1, 2)], FakeFetcher(), tmp_path / "thumbs", sync.SyncOptions(), log=lambda *_: None)
    assert db.stats(conn)["items"] == 2 and db.stats(conn)["thumbs"] == 0
    assert len(rep.sources["good"]["failures"]) == 2
    assert len(db.items_without_thumb(conn)) == 2


def test_ensure_thumbs_fills_missing(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    sync.sync(conn, [Good(1, 2)], FakeFetcher(), tmp_path / "thumbs", sync.SyncOptions(), log=lambda *_: None)
    n = sync.ensure_thumbs(conn, _fetch(), tmp_path / "thumbs", log=lambda *_: None)
    assert n == 2 and db.stats(conn)["thumbs"] == 2


class WallFetcher(FakeFetcher):
    def download(self, url, dest, headers=None):
        self.calls.append(("download", url))
        raise Blocked(f"{url}: bot challenge")


def test_blocked_during_thumbnail_marks_source_blocked(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    rep = sync.sync(conn, [Good(1, 3)], WallFetcher(), tmp_path / "thumbs", sync.SyncOptions(workers=1), log=lambda *_: None)
    assert rep.sources["good"]["blocked"] is True
    assert db.stats(conn)["items"] == 3
    assert "challenge" in conn.execute("SELECT error FROM sources WHERE slug='good'").fetchone()[0]


def test_blocked_stops_the_rest_of_the_batch(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    f = WallFetcher()
    rep = sync.sync(conn, [Good(1, 24)], f, tmp_path / "thumbs", sync.SyncOptions(workers=8), log=lambda *_: None)
    downloads = [c for c in f.calls if c[0] == "download"]
    assert 1 <= len(downloads) <= 8 and len(downloads) < 24
    assert rep.sources["good"]["blocked"] is True and rep.sources["good"]["failures"] == [rep.sources["good"]["failures"][0]]


def test_ensure_thumbs_stops_on_blocked(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    sync.sync(conn, [Good(1, 3)], FakeFetcher(), tmp_path / "thumbs", sync.SyncOptions(), log=lambda *_: None)
    f = WallFetcher()
    n = sync.ensure_thumbs(conn, f, tmp_path / "thumbs", log=lambda *_: None)
    assert n == 0 and len([c for c in f.calls if c[0] == "download"]) == 1


class Fonty:
    info = SourceInfo("fonty", "Fonty", "https://fo.test", 1)

    def font_file(self, item, fetch, tmp):
        raise KeyError("no font url")

    def collections(self, fetch):
        yield CollectionDraft("fonty/all", "image", "All"), [
            ItemDraft("fonty:img", "image", "Pic", "https://fo.test/1", "https://cdn.g.test/1.jpg"),
            ItemDraft("fonty:font", "font", "Face", "https://fo.test/2", "https://fo.test/2.ttf")]


def test_unexpected_worker_exception_is_a_thumb_failure(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    rep = sync.sync(conn, [Fonty()], _fetch(), tmp_path / "thumbs", sync.SyncOptions(), log=lambda *_: None)
    r = rep.sources["fonty"]
    assert r["thumbs"] == 1 and len(r["failures"]) == 1 and "(Face)" in r["failures"][0] and "no font url" in r["failures"][0]
    assert conn.execute("SELECT error FROM sources WHERE slug='fonty'").fetchone()[0] is None
    assert db.stats(conn)["items"] == 2


def test_sync_passes_item_cap_to_adapter(tmp_path):
    class Capped(Good):
        max_items = None
    a = Capped(1, 2)
    sync.sync(db.connect(tmp_path / "t.db"), [a], _fetch(), tmp_path / "thumbs", sync.SyncOptions(), log=lambda *_: None)
    assert a.max_items == 24


def test_item_with_nothing_to_render_is_no_thumb_not_failure(tmp_path):
    class Code:
        info = SourceInfo("code", "Code", "https://c.test", 1)

        def collections(self, fetch):
            yield CollectionDraft("code/all", "snippet", "All"), [
                ItemDraft("code:1", "snippet", "Beams", "https://c.test/1", "https://raw.c.test/1.jsx", meta={"code": "x"})]
    conn = db.connect(tmp_path / "t.db")
    rep = sync.sync(conn, [Code()], FakeFetcher(), tmp_path / "thumbs", sync.SyncOptions(), log=lambda *_: None)
    r = rep.sources["code"]
    assert r["no_thumb"] == 1 and r["failures"] == [] and r["thumbs"] == 0 and r["new"] == 1
    assert conn.execute("select thumb from items").fetchone()[0] is None
    assert "1 no-thumb, 0 failures" in rep.summary()
    assert sync.ensure_thumbs(conn, FakeFetcher(), tmp_path / "thumbs", log=lambda m: (_ for _ in ()).throw(AssertionError(m))) == 0


def test_ensure_thumbs_survives_an_unexpected_exception(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "t.db")
    sync.sync(conn, [Good(1, 3)], FakeFetcher(), tmp_path / "thumbs", sync.SyncOptions(), log=lambda *_: None)
    real, calls = sync.make_item_thumb, []
    def flaky(item, *a, **k):
        calls.append(item["id"])
        if len(calls) == 1:
            raise RuntimeError("weird")
        return real(item, *a, **k)
    monkeypatch.setattr(sync, "make_item_thumb", flaky)
    logs = []
    n = sync.ensure_thumbs(conn, _fetch(), tmp_path / "thumbs", log=logs.append)
    assert n == 2 and len(calls) == 3 and any("weird" in m for m in logs)


class IconSource:
    info = SourceInfo("ico", "Ico", "https://i.test", 1)

    def collections(self, fetch):
        yield CollectionDraft("ico/all", "icon", "All"), [
            ItemDraft("ico:1", "icon", "a-b", "https://i.test/1", "https://raw.i.test/1.svg",
                      meta={"code": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M0 0h24v24H0z"/></svg>'})]


def test_icon_without_rasteriser_stays_thumbless_and_retries(tmp_path, monkeypatch):
    monkeypatch.setattr(sync.thumbs, "svg_to_png", lambda svg, dest: None)
    conn = db.connect(tmp_path / "t.db")
    rep = sync.sync(conn, [IconSource()], FakeFetcher(), tmp_path / "thumbs", sync.SyncOptions(), log=lambda *_: None)
    r = rep.sources["ico"]
    assert r["no_thumb"] == 1 and r["thumbs"] == 0 and r["failures"] == []
    assert conn.execute("select thumb from items").fetchone()[0] is None
    assert not list((tmp_path / "thumbs").glob("*.jpg")) if (tmp_path / "thumbs").exists() else True
    # once a rasteriser exists the next ensure_thumbs fills it
    def fake_png(svg, dest):
        Image.new("RGB", (40, 40), (5, 5, 5)).save(dest, "PNG")
        return dest
    monkeypatch.setattr(sync.thumbs, "svg_to_png", fake_png)
    assert sync.ensure_thumbs(conn, FakeFetcher(), tmp_path / "thumbs", log=lambda *_: None) == 1


def test_sync_stores_collection_error(tmp_path):
    class Bad:
        info = SourceInfo("bad", "Bad", "https://b.test", 1)

        def collections(self, fetch):
            yield CollectionDraft("bad/all", "image", "All", error="FetchError: boom"), []
    conn = db.connect(tmp_path / "t.db")
    sync.sync(conn, [Bad()], FakeFetcher(), tmp_path / "thumbs", sync.SyncOptions(), log=lambda *_: None)
    assert db.get_collection(conn, "bad/all")["error"] == "FetchError: boom"
    assert {"slug": "bad/all", "error": "FetchError: boom"} in db.stats(conn)["errors"]


def test_icon_svg_behind_a_leading_comment_still_gets_a_tile(tmp_path, monkeypatch):
    def fake_png(svg, dest):
        assert svg.startswith("<svg")       # the metadata comment was stripped
        Image.new("RGB", (40, 40), (5, 5, 5)).save(dest, "PNG")
        return dest
    monkeypatch.setattr(sync.thumbs, "svg_to_png", fake_png)
    class Tabler:
        info = SourceInfo("tab", "Tab", "https://t.test", 1)

        def collections(self, fetch):
            yield CollectionDraft("tab/all", "icon", "All"), [
                ItemDraft("tab:1", "icon", "a-b", "https://t.test/1", "https://raw.t.test/1.svg",
                          meta={"code": '<!--\ntags: [a]\n-->\n<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M0 0h24v24H0z"/></svg>'})]
    conn = db.connect(tmp_path / "t.db")
    rep = sync.sync(conn, [Tabler()], FakeFetcher(), tmp_path / "thumbs", sync.SyncOptions(), log=lambda *_: None)
    assert rep.sources["tab"]["failures"] == [] and rep.sources["tab"]["thumbs"] == 1 and rep.sources["tab"]["no_thumb"] == 0


def test_manual_source_needs_explicit(tmp_path):
    class Manual(Good):
        info = SourceInfo("man", "Manual", "https://m", 1, policy="manual")
    conn = db.connect(tmp_path / "t.db")
    rep = sync.sync(conn, [Manual(1, 1)], _fetch(), tmp_path / "thumbs", sync.SyncOptions(), log=lambda *_: None)
    assert rep.sources["man"]["new"] == 0 and "manual source" in rep.sources["man"]["failures"][0]
    rep = sync.sync(conn, [Manual(1, 1)], _fetch(), tmp_path / "thumbs", sync.SyncOptions(), log=lambda *_: None, explicit=True)
    assert rep.sources["man"]["new"] == 1
