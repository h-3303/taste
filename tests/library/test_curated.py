from PIL import Image

from taste.library import curated, db
from taste.library.fetch import FakeFetcher


def _png(path):
    Image.new("RGB", (500, 500), (1, 2, 3)).save(path)
    return path


def test_new_collection_prefixes_and_is_idempotent(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    a = curated.new_collection(conn, "swiss", "image", languages=["swiss international"])
    b = curated.new_collection(conn, "curated/swiss", "image")
    assert a == b and db.get_collection(conn, "curated/swiss")["languages"] == ["swiss international"]


def test_add_local_file(tmp_path, monkeypatch):
    monkeypatch.setenv("TASTE_DATA", str(tmp_path / "data"))
    conn = db.connect(tmp_path / "t.db")
    curated.new_collection(conn, "swiss", "image")
    iid = curated.add(conn, "curated/swiss", str(_png(tmp_path / "pic.png")), FakeFetcher(), tmp_path / "thumbs", title="Grid poster",
                      tags=["grid"], page_url="https://x/poster", language="swiss international")
    it = db.get_item(conn, iid)
    assert it["kind"] == "image" and it["thumb"] and it["title"] == "Grid poster" and it["page_url"] == "https://x/poster"
    assert (tmp_path / "data" / "library" / "cache" / "curated" / f"{iid}.png").exists()
    assert db.get_collection(conn, "curated/swiss")["languages"] == ["swiss international"]


def test_add_url_and_snippet(tmp_path, monkeypatch):
    monkeypatch.setenv("TASTE_DATA", str(tmp_path / "data"))
    conn = db.connect(tmp_path / "t.db")
    curated.new_collection(conn, "bits", "snippet")
    (tmp_path / "glass.css").write_text(".glass{backdrop-filter:blur(8px)}")
    iid = curated.add(conn, "curated/bits", str(tmp_path / "glass.css"), FakeFetcher(), tmp_path / "thumbs")
    assert db.get_item(conn, iid)["meta"]["code"].startswith(".glass")
    import io
    b = io.BytesIO(); Image.new("RGB", (450, 450)).save(b, "JPEG")
    iid2 = curated.add(conn, "curated/bits", "https://cdn.x/a.jpg", FakeFetcher(files={"cdn.x/a.jpg": b.getvalue()}), tmp_path / "thumbs")
    assert db.get_item(conn, iid2)["kind"] == "image" and db.get_item(conn, iid2)["asset_url"] == "https://cdn.x/a.jpg"


def test_add_unknown_collection(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    import pytest
    with pytest.raises(KeyError):
        curated.add(conn, "curated/nope", "x.png", FakeFetcher(), tmp_path)


def test_bad_image_leaves_no_trace(tmp_path, monkeypatch):
    import pytest
    monkeypatch.setenv("TASTE_DATA", str(tmp_path / "data"))
    conn = db.connect(tmp_path / "t.db")
    curated.new_collection(conn, "swiss", "image")
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"not an image")
    with pytest.raises((OSError, ValueError)):
        curated.add(conn, "curated/swiss", str(bad), FakeFetcher(), tmp_path / "thumbs")
    assert db.query_items(conn, None, collection="curated/swiss") == []
    assert list((tmp_path / "data" / "library" / "cache" / "curated").iterdir()) == []
    assert not (tmp_path / "thumbs").exists() or list((tmp_path / "thumbs").iterdir()) == []


def test_failed_download_leaves_no_temp(tmp_path, monkeypatch):
    import pytest
    from taste.library.fetch import FetchError
    monkeypatch.setenv("TASTE_DATA", str(tmp_path / "data"))
    conn = db.connect(tmp_path / "t.db")
    curated.new_collection(conn, "swiss", "image")

    class Boom(FakeFetcher):
        def download(self, url, dest, headers=None):
            Path(dest).write_bytes(b"partial")
            raise FetchError("boom")

    from pathlib import Path
    with pytest.raises(FetchError):
        curated.add(conn, "curated/swiss", "https://x/a.jpg", Boom(), tmp_path / "thumbs")
    assert not list((tmp_path / "data" / "library" / "cache" / "curated").glob("incoming-*"))


def test_icon_without_rasteriser_gets_no_thumb(tmp_path, monkeypatch):
    monkeypatch.setenv("TASTE_DATA", str(tmp_path / "data"))
    monkeypatch.setattr(curated.thumbs, "svg_to_png", lambda svg, dest: None)
    conn = db.connect(tmp_path / "t.db")
    curated.new_collection(conn, "icons", "icon")
    svg = tmp_path / "a.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M0 0h24v24H0z"/></svg>')
    iid = curated.add(conn, "curated/icons", str(svg), FakeFetcher(), tmp_path / "thumbs")
    assert db.get_item(conn, iid)["thumb"] is None
    assert not (tmp_path / "thumbs" / f"{iid}.jpg").exists()
