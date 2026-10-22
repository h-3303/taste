import json
from pathlib import Path

import httpx

from taste.boards import archive

FIX = Path(__file__).parent / "fixtures"
ID = "flyer-for-untouchable-chicago-il-on-08-17-1996"


class FakeHttp:
    def __init__(self, fail_meta_for=()):
        self.fail_meta_for = set(fail_meta_for)
        self.calls = []

    def get_json(self, url, params=None):
        self.calls.append((url, params))
        if url.endswith("advancedsearch.php"):
            return json.loads((FIX / "ia_search.json").read_text())
        ident = url.rsplit("/", 1)[1]
        if ident in self.fail_meta_for:
            raise httpx.ConnectError("boom")
        meta = json.loads((FIX / "ia_meta.json").read_text())
        meta["metadata"]["identifier"] = ident
        return meta

    def download(self, url, dest):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"jpeg")
        return dest


def test_pick_image_url_is_encoded():
    files = json.loads((FIX / "ia_meta.json").read_text())["files"]
    url = archive.pick_image(ID, files)
    assert url == (
        "https://archive.org/download/" + ID + "/"
        "Flyer%20for%20Untouchable%2C%20Chicago%2C%20IL%20on%2008-17-1996%2C%20Front.jpg"
    )


def test_pick_image_skips_oversize_and_thumbs():
    files = [
        {"name": "big.jpg", "format": "JPEG", "size": "20000000"},
        {"name": "t_thumb.jpg", "format": "JPEG Thumb", "size": "1000"},
    ]
    assert archive.pick_image("x", files) is None


def test_pick_image_non_ascii_name():
    url = archive.pick_image("x", [{"name": "Zürich plakat.jpg", "format": "JPEG", "size": "10"}])
    assert url == "https://archive.org/download/x/Z%C3%BCrich%20plakat.jpg"


def test_fetch_builds_candidates(tmp_path):
    http = FakeHttp()
    cands, failures = archive.fetch(["rave flyer"], 2, tmp_path, http)
    assert failures == []
    assert [c.source_url for c in cands] == [
        "https://archive.org/details/" + ID,
        "https://archive.org/details/flyer-for-juice-chicago-on-06-07-1996",
    ]
    assert all(c.kind == "archive" and c.path.exists() for c in cands)
    assert cands[0].title == "Flyer For Untouchable, Chicago, IL On 08 17 1996"
    search_params = http.calls[0][1]
    assert search_params["q"] == "(rave flyer) AND mediatype:image"
    assert search_params["rows"] == 2


def test_fetch_records_failure_and_continues(tmp_path):
    http = FakeHttp(fail_meta_for={ID})
    cands, failures = archive.fetch(["rave flyer"], 2, tmp_path, http)
    assert len(cands) == 1
    assert len(failures) == 1 and ID in failures[0]


def test_fetch_reuses_existing_download(tmp_path):
    (tmp_path / f"archive-{ID}.jpg").write_bytes(b"old")
    http = FakeHttp()
    http.downloads = []
    orig = http.download
    http.download = lambda url, dest: (http.downloads.append(dest.name), orig(url, dest))[1]
    cands, failures = archive.fetch(["rave flyer"], 2, tmp_path, http)
    assert failures == [] and len(cands) == 2
    assert http.downloads == ["archive-flyer-for-juice-chicago-on-06-07-1996.jpg"]
    assert not any(url.endswith(ID) for url, _ in http.calls)          # no metadata call either
    assert (tmp_path / f"archive-{ID}.jpg").read_bytes() == b"old"
    assert cands[0].source_url == "https://archive.org/details/" + ID
    assert cands[0].title == "Flyer For Untouchable, Chicago, IL On 08 17 1996"
