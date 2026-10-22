from taste.library import timer


def test_install_writes_units_and_enables(tmp_path):
    calls = []
    d = timer.install(run=lambda argv, **kw: calls.append(argv), home=tmp_path)
    assert (d / "dlib.timer").read_text().count("OnCalendar=Sun *-*-* 04:00") == 1
    assert "ExecStart=%h/.local/bin/dlib sync" in (d / "dlib.service").read_text()
    assert calls[-1][-2:] == ["--now", "dlib.timer"]
