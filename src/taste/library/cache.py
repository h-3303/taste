from pathlib import Path


def record(conn, path: Path, item_id: str, now: str) -> None:
    p = Path(path)
    conn.execute("INSERT OR REPLACE INTO cache(path, item, bytes, last_used) VALUES (?,?,?,?)",
                 (str(p), item_id, p.stat().st_size if p.exists() else 0, now))
    conn.commit()


def touch(conn, path: Path, now: str) -> None:
    conn.execute("UPDATE cache SET last_used = ? WHERE path = ?", (now, str(path)))
    conn.commit()


def size(conn) -> int:
    return conn.execute("SELECT COALESCE(SUM(bytes), 0) FROM cache").fetchone()[0]


def prune(conn, cache_root: Path, max_bytes: int = 2 * 1024 ** 3) -> list[Path]:
    rows = [dict(r) for r in conn.execute("SELECT path, bytes, last_used FROM cache ORDER BY last_used ASC, path ASC")]
    for r in rows:
        if not Path(r["path"]).exists():
            conn.execute("DELETE FROM cache WHERE path = ?", (r["path"],))
    conn.commit()
    rows = [r for r in rows if Path(r["path"]).exists()]
    total, removed = sum(r["bytes"] for r in rows), []
    for r in rows:
        if total <= max_bytes:
            break
        Path(r["path"]).unlink(missing_ok=True)
        conn.execute("DELETE FROM cache WHERE path = ?", (r["path"],))
        total -= r["bytes"]
        removed.append(Path(r["path"]))
    conn.commit()
    return removed
