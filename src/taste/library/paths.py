import shutil
from pathlib import Path

from .. import config, paths as taste_paths

SAMPLE_COLLECTIONS = 3
SAMPLE_ITEMS = 24
BANNED_HOSTS = ("are.na", "artvee.com", "emuseum.ch", "gurafiku.tumblr.com", "designreviewed.com")


def data_root() -> Path:
    return taste_paths.library_dir()


def db_path() -> Path:
    return data_root() / "library.db"


def thumbs_dir() -> Path:
    return data_root() / "thumbs"


def cache_dir() -> Path:
    return data_root() / "cache"


def snapshots_dir() -> Path:
    return data_root() / "snapshots"


def logs_dir() -> Path:
    return data_root() / "logs"


def ensure_dirs() -> Path:
    root = data_root()
    for d in (thumbs_dir(), cache_dir(), snapshots_dir(), logs_dir()):
        d.mkdir(parents=True, exist_ok=True)
    return root


def obscura_bin() -> str | None:
    c = config.connector("obscura")
    if not c:
        return None
    return c.get("bin") or shutil.which("obscura")
