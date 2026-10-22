import re
from pathlib import Path

from taste.library import ids, paths


def test_data_root_honours_env(monkeypatch, tmp_path):
    monkeypatch.setenv("TASTE_DATA", str(tmp_path / "d"))
    assert paths.data_root() == tmp_path / "d" / "library"
    assert paths.db_path() == tmp_path / "d" / "library" / "library.db"
    assert paths.thumbs_dir() == tmp_path / "d" / "library" / "thumbs"


def test_ensure_dirs_creates_layout(monkeypatch, tmp_path):
    monkeypatch.setenv("TASTE_DATA", str(tmp_path / "d"))
    root = paths.ensure_dirs()
    for sub in ("thumbs", "cache", "snapshots", "logs"):
        assert (root / sub).is_dir()


def test_obscura_bin_comes_from_the_connector(monkeypatch, tmp_path):
    from taste import config
    monkeypatch.setenv("TASTE_DATA", str(tmp_path))
    config.save({"connectors": {"obscura": {"enabled": True, "bin": "/x/obscura"}}})
    assert paths.obscura_bin() == "/x/obscura"


def test_new_id_shape():
    seen = {ids.new_id() for _ in range(200)}
    assert len(seen) == 200
    assert all(re.fullmatch(r"[a-z2-7]{6}", i) for i in seen)
