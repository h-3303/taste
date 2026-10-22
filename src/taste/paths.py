import os
from pathlib import Path


def data_root() -> Path:
    return Path(os.environ.get("TASTE_DATA") or Path.home() / ".taste")


def library_dir() -> Path:
    return data_root() / "library"


def runs_dir() -> Path:
    return data_root() / "runs"


def inbox_dir() -> Path:
    return data_root() / "inbox"


def profile_path() -> Path:
    return data_root() / "profile.md"


def config_path() -> Path:
    return data_root() / "config.json"
