from taste.library import cache, db


def test_prune_lru(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    root = tmp_path / "c"; root.mkdir()
    for n, when in (("a", "2026-10-01"), ("b", "2026-10-03"), ("c", "2026-10-02")):
        (root / f"{n}.bin").write_bytes(b"x" * 100)
        cache.record(conn, root / f"{n}.bin", n, when)
    (root / "c.bin").unlink()                                  # already gone: row must be dropped, not counted
    removed = cache.prune(conn, root, max_bytes=150)
    assert [p.name for p in removed] == ["a.bin"] and (root / "b.bin").exists() and cache.size(conn) == 100
