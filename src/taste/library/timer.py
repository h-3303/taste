"""The maintainer's weekly sync as a systemd user timer: taste-sync.service/.timer (never the old dlib.* units)."""
import os
import shutil
import subprocess
from pathlib import Path

NAME = "taste-sync"
SERVICE = """[Unit]
Description=taste: weekly design-library sync

[Service]
Type=oneshot
{env}ExecStart={exe} maintainer sync
TimeoutStartSec=6h
"""
TIMER = """[Unit]
Description=Weekly taste library sync

[Timer]
OnCalendar=Sun *-*-* 04:00
Persistent=true
RandomizedDelaySec=30m

[Install]
WantedBy=timers.target
"""


class NotInstalled(Exception):
    """The `taste` command is not on PATH, so a unit could not run it."""


def _quote(v: str) -> str:
    return v.replace("%", "%%").replace("\\", "\\\\").replace('"', '\\"')


def install(run=subprocess.run, home: Path | None = None, exe: str | None = None, env=None, which=None) -> Path:
    exe = exe or (which or shutil.which)("taste")
    if not exe:
        raise NotInstalled("`taste` is not on PATH; install it (uv tool install / pip) before the timer")
    env = os.environ if env is None else env
    d = Path(home if home is not None else Path.home()) / ".config/systemd/user"
    d.mkdir(parents=True, exist_ok=True)
    line = f'Environment="TASTE_DATA={_quote(env["TASTE_DATA"])}"\n' if env.get("TASTE_DATA") else ""
    (d / f"{NAME}.service").write_text(SERVICE.format(env=line, exe=exe.replace("%", "%%")))
    (d / f"{NAME}.timer").write_text(TIMER)
    run(["systemctl", "--user", "daemon-reload"], check=True)
    run(["systemctl", "--user", "enable", "--now", f"{NAME}.timer"], check=True)
    return d
