from taste import paths
from taste.boards import run as boards_run
from taste.library import paths as library_paths


def test_data_root_defaults_to_dot_taste(monkeypatch, tmp_path):
    monkeypatch.delenv("TASTE_DATA", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert paths.data_root() == tmp_path / ".taste"
    assert paths.library_dir() == tmp_path / ".taste" / "library"


def test_named_locations_sit_under_the_root(monkeypatch, tmp_path):
    monkeypatch.setenv("TASTE_DATA", str(tmp_path))
    assert paths.runs_dir() == tmp_path / "runs"
    assert paths.inbox_dir() == tmp_path / "inbox"
    assert paths.profile_path() == tmp_path / "profile.md"
    assert paths.config_path() == tmp_path / "config.json"


def test_both_packages_share_the_root(monkeypatch, tmp_path):
    monkeypatch.setenv("TASTE_DATA", str(tmp_path))
    assert boards_run.data_root() == tmp_path
    assert library_paths.db_path() == tmp_path / "library" / "library.db"


def test_no_vault_default_left():
    assert not hasattr(boards_run, "vault_root")
