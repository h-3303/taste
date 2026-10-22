import json

import pytest
from PIL import Image

from taste import additions, cli, licences, seed
from taste.library import db, fetch, paths


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("TASTE_DATA", str(tmp_path / "data"))
    paths.ensure_dirs()
    return db.connect(paths.db_path())


def png(path, color="red"):
    Image.new("RGB", (40, 30), color).save(path)
    return path


class FakeFetch:
    def __init__(self):
        self.downloads, self.shots = [], []

    def download(self, url, dest):
        self.downloads.append(url)
        return png(dest, "blue")

    def screenshot(self, url, dest):
        self.shots.append(url)
        return png(dest, "green")


def test_file_add_makes_mine_item_with_thumb(env, tmp_path):
    src = png(tmp_path / "a.png")
    ids = additions.add(env, str(src), tags=["warm"], language="brutalist")
    assert len(ids) == 1
    it = db.get_item(env, ids[0])
    assert it["source"] == "mine" and it["kind"] == "image" and "warm" in it["tags"]
    assert (paths.thumbs_dir() / f"{ids[0]}.jpg").exists() and it["thumb"] == f"thumbs/{ids[0]}.jpg"
    from taste.paths import library_dir
    assert list((library_dir() / "mine").glob("*.png"))
    coll = db.get_collection(env, "mine/additions")
    assert coll and coll["item_count"] == 1


def test_folder_add_ignores_other_files(env, tmp_path):
    d = tmp_path / "pics"; d.mkdir()
    png(d / "one.jpg"); png(d / "two.png"); (d / "notes.txt").write_text("x")
    ids = additions.add(env, str(d))
    assert len(ids) == 2


def test_mine_is_never_seeded(env, tmp_path):
    additions.add(env, str(png(tmp_path / "a.png")))
    assert licences.classify("mine", "") == "never"
    rep = seed.build_seed(env, paths.thumbs_dir(), tmp_path / "s.zip")
    assert (rep.files, rep.links) == (0, 0)


def test_unknown_extension_needs_kind(env, tmp_path):
    f = tmp_path / "thing.xyz"; f.write_bytes(b"x")
    with pytest.raises(ValueError, match=r"can't tell what thing.xyz is: pass --kind"):
        additions.add(env, str(f))


def test_banned_host_raises(env):
    with pytest.raises(fetch.FetchError, match="banned"):
        additions.add(env, "https://www.are.na/block/1", fetch=FakeFetch())


def test_image_url_downloads_and_page_url_screenshots(env):
    f = FakeFetch()
    a = additions.add(env, "https://ex.test/x/pic.jpg?w=1", fetch=f)
    b = additions.add(env, "https://ex.test/some/page", fetch=f)
    assert f.downloads == ["https://ex.test/x/pic.jpg?w=1"] and f.shots == ["https://ex.test/some/page"]
    assert db.get_item(env, b[0])["page_url"] == "https://ex.test/some/page"
    assert len(a) == len(b) == 1


def test_cli_add_exit_codes(env, tmp_path, capsys):
    assert cli.main(["add", str(png(tmp_path / "ok.png"))]) == 0
    bad = tmp_path / "t.xyz"; bad.write_bytes(b"x")
    assert cli.main(["add", str(bad)]) == 1
    assert cli.main(["add", "https://are.na/block/2"]) == 1


def test_cli_renderer_missing_exits_2(env, monkeypatch, capsys):
    from taste import render

    def boom():
        raise render.RendererMissing()
    monkeypatch.setattr(render, "get_renderer", boom)
    assert cli.main(["add", "https://ex.test/page"]) == 2
    assert "Chromium is missing" in capsys.readouterr().err


def test_cli_data_dir_failure_exits_2(tmp_path, monkeypatch, capsys):
    blocker = tmp_path / "file"; blocker.write_text("x")
    monkeypatch.setenv("TASTE_DATA", str(blocker / "sub"))
    assert cli.main(["add", str(png(tmp_path / "a.png"))]) == 2
    assert "error" in capsys.readouterr().err


def test_corrupt_image_is_valueerror_and_stores_nothing(env, tmp_path, capsys):
    bad = tmp_path / "bad.png"; bad.write_text("not an image")
    with pytest.raises(ValueError, match="cannot thumbnail"):
        additions.add(env, str(bad))
    assert env.execute("select count(*) from items").fetchone()[0] == 0
    assert not list((paths.thumbs_dir()).glob("*.jpg"))
    assert cli.main(["add", str(bad)]) == 1
