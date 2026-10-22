import re
from pathlib import Path

from taste.library import ids, paths


def test_data_root_honours_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DLIB_DATA", str(tmp_path / "d"))
    assert paths.data_root() == tmp_path / "d"
    assert paths.db_path() == tmp_path / "d" / "library.db"
    assert paths.thumbs_dir() == tmp_path / "d" / "thumbs"


def test_ensure_dirs_creates_layout(monkeypatch, tmp_path):
    monkeypatch.setenv("DLIB_DATA", str(tmp_path / "d"))
    root = paths.ensure_dirs()
    for sub in ("thumbs", "cache", "snapshots", "logs"):
        assert (root / sub).is_dir()


def test_obscura_bin_prefers_env(monkeypatch, tmp_path):
    exe = tmp_path / "obscura"
    exe.write_text("")
    monkeypatch.setenv("DLIB_OBSCURA", str(exe))
    assert paths.obscura_bin() == str(exe)


def test_new_id_shape():
    seen = {ids.new_id() for _ in range(200)}
    assert len(seen) == 200
    assert all(re.fullmatch(r"[a-z2-7]{6}", i) for i in seen)
