import pytest

from taste.library import timer


def _install(tmp_path, env=None, exe="/opt/bin/taste"):
    calls = []
    d = timer.install(run=lambda argv, **kw: calls.append(argv), home=tmp_path, exe=exe, env=env or {})
    return d, calls


def test_install_writes_taste_units_and_enables(tmp_path):
    d, calls = _install(tmp_path)
    assert d == tmp_path / ".config/systemd/user"
    assert (d / "taste-sync.timer").read_text().count("OnCalendar=Sun *-*-* 04:00") == 1
    svc = (d / "taste-sync.service").read_text()
    assert "ExecStart=/opt/bin/taste maintainer sync\n" in svc
    assert "dlib" not in svc and "Environment" not in svc
    assert calls == [["systemctl", "--user", "daemon-reload"], ["systemctl", "--user", "enable", "--now", "taste-sync.timer"]]


def test_install_never_touches_the_old_dlib_units(tmp_path):
    d = tmp_path / ".config/systemd/user"
    d.mkdir(parents=True)
    (d / "dlib.service").write_text("old service")
    (d / "dlib.timer").write_text("old timer")
    _install(tmp_path)
    assert (d / "dlib.service").read_text() == "old service" and (d / "dlib.timer").read_text() == "old timer"
    assert sorted(p.name for p in d.iterdir()) == ["dlib.service", "dlib.timer", "taste-sync.service", "taste-sync.timer"]


def test_install_carries_taste_data(tmp_path):
    d, _ = _install(tmp_path, env={"TASTE_DATA": "/data/my taste"})
    assert 'Environment="TASTE_DATA=/data/my taste"\n' in (d / "taste-sync.service").read_text()


def test_install_without_taste_on_path_refuses(tmp_path):
    with pytest.raises(timer.NotInstalled):
        timer.install(run=lambda argv, **kw: None, home=tmp_path, exe=None, env={}, which=lambda name: None)
    assert not (tmp_path / ".config").exists()
