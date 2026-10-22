import pytest


@pytest.fixture(autouse=True)
def no_real_dlib(monkeypatch):
    """Tests must never file images into the real design library."""
    monkeypatch.setenv("MOODBOARDS_NO_DLIB", "1")
