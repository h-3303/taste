import pytest


@pytest.fixture(autouse=True)
def no_real_dlib(monkeypatch):
    """Tests must never file images into the real design library."""
    monkeypatch.setenv("MOODBOARDS_NO_DLIB", "1")


def fill_library():
    """Give the library under the current TASTE_DATA one item, so `taste new` accepts it."""
    from taste.library import db, paths
    conn = db.connect(paths.db_path())
    conn.execute("INSERT OR IGNORE INTO items(id,key,source,kind,title,added_at) VALUES ('x1','x:1','mine','image','x','t')")
    conn.commit()
    conn.close()
