"""Messages and usage lines name commands that exist (taste, taste lib), never the old tools."""
import pytest

from taste import cli
from taste.boards import cli as boards_cli
from taste.library import cli as lib_cli, curated, db, sync


def test_curated_add_names_taste_lib_collection_new(tmp_path):
    conn = db.connect(tmp_path / "l.db")
    with pytest.raises(KeyError) as e:
        curated.add(conn, "curated/nope", "https://ex.test/a.png", None, tmp_path)
    assert "taste lib collection new nope --kind <kind>" in str(e.value) and "dlib" not in str(e.value)


def test_manual_source_message_names_taste_sync(tmp_path):
    from taste.library.models import SourceInfo

    class Manual:
        info = SourceInfo("archive", "Internet Archive", "https://archive.org", 1, policy="manual")

        def collections(self, fetch):
            raise AssertionError("synced a manual source")
    rep = sync.sync(db.connect(tmp_path / "l.db"), [Manual()], None, tmp_path / "t", sync.SyncOptions(), log=lambda *_: None)
    msg = rep.sources["archive"]["failures"][0]
    assert "`taste sync archive`" in msg and "dlib" not in msg


def test_parsers_are_named_taste(capsys):
    assert lib_cli.build_parser().prog == "taste lib"
    with pytest.raises(SystemExit):
        boards_cli.main(["--help"])
    assert capsys.readouterr().out.startswith("usage: taste ")


def test_pyproject_description():
    import tomllib
    from pathlib import Path
    meta = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())
    assert meta["project"]["description"] == "Taste curator for Claude Code"
