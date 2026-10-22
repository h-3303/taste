from taste import config
from taste.library import paths as library_paths


def test_missing_file_loads_empty(monkeypatch, tmp_path):
    monkeypatch.setenv("TASTE_DATA", str(tmp_path))
    assert config.load() == {"connectors": {}}


def test_connector_off_by_default(monkeypatch, tmp_path):
    monkeypatch.setenv("TASTE_DATA", str(tmp_path))
    assert config.connector("obscura") is None
    assert library_paths.obscura_bin() is None


def test_connector_enabled_round_trip(monkeypatch, tmp_path):
    monkeypatch.setenv("TASTE_DATA", str(tmp_path))
    config.save({"connectors": {"obscura": {"enabled": True, "bin": "/x/obscura"}}})
    assert config.connector("obscura") == {"enabled": True, "bin": "/x/obscura"}
    assert library_paths.obscura_bin() == "/x/obscura"


def test_disabled_connector_is_none(monkeypatch, tmp_path):
    monkeypatch.setenv("TASTE_DATA", str(tmp_path))
    config.save({"connectors": {"obscura": {"enabled": False, "bin": "/x/obscura"}}})
    assert config.connector("obscura") is None
    assert library_paths.obscura_bin() is None


def test_enabled_without_bin_falls_back_to_path(monkeypatch, tmp_path):
    monkeypatch.setenv("TASTE_DATA", str(tmp_path))
    config.save({"connectors": {"obscura": {"enabled": True}}})
    monkeypatch.setattr("shutil.which", lambda n: "/usr/bin/obscura")
    assert library_paths.obscura_bin() == "/usr/bin/obscura"
