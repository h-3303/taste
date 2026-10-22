import subprocess
from pathlib import Path

SERVICE = """[Unit]
Description=dlib: weekly design-library sync (sample mode unless changed)

[Service]
Type=oneshot
ExecStart=%h/.local/bin/dlib sync
TimeoutStartSec=6h
"""
TIMER = """[Unit]
Description=Weekly dlib sync

[Timer]
OnCalendar=Sun *-*-* 04:00
Persistent=true
RandomizedDelaySec=30m

[Install]
WantedBy=timers.target
"""


def install(run=subprocess.run, home: Path = Path.home()) -> Path:
    d = Path(home) / ".config/systemd/user"
    d.mkdir(parents=True, exist_ok=True)
    (d / "dlib.service").write_text(SERVICE)
    (d / "dlib.timer").write_text(TIMER)
    run(["systemctl", "--user", "daemon-reload"], check=True)
    run(["systemctl", "--user", "enable", "--now", "dlib.timer"], check=True)
    return d
