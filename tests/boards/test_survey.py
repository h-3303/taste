import json
import re

import pytest
from PIL import Image

from taste.boards import survey
from taste.boards.cli import main


def img(path, size=(900, 700)):
    Image.new("RGB", size, (120, 80, 40)).save(path)
    return path


def test_add_copies_local_image_and_records_it(tmp_path):
    src = img(tmp_path / "a.png")
    item = survey.add(tmp_path / "run", str(src), title="Godly SOTD", source="https://godly.website/x",
                      why="most-liked this week", tag="web")
    assert item["id"] == "s001"
    assert (tmp_path / "run" / "survey" / "img" / item["file"]).exists()
    items = json.loads((tmp_path / "run" / "survey" / "items.json").read_text())
    assert items == [item]
    assert item["why"] == "most-liked this week" and item["tag"] == "web"


def test_add_numbers_items_and_skips_a_repeated_image(tmp_path):
    run = tmp_path / "run"
    a = survey.add(run, str(img(tmp_path / "a.jpg")), title="A", source="https://gallery/", why="new")
    b = survey.add(run, str(img(tmp_path / "b.jpg")), title="B", source="https://gallery/", why="new")
    again = survey.add(run, str(tmp_path / "a.jpg"), title="A2", source="https://elsewhere/", why="new")
    assert (a["id"], b["id"]) == ("s001", "s002")              # a shared gallery page is not a duplicate
    assert again["id"] == "s001"                                # the same image is
    assert len(survey.load(run)) == 2


def test_add_downloads_a_url(tmp_path):
    def fake_download(url, dest):
        img(dest)
        return dest
    item = survey.add(tmp_path / "run", "https://cdn.cosmos.so/abc?format=jpeg&w=1600", title="C",
                      source="https://www.cosmos.so/e/1", why="trending", download=fake_download)
    assert (tmp_path / "run" / "survey" / "img" / item["file"]).exists()


def test_add_rejects_a_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        survey.add(tmp_path / "run", str(tmp_path / "nope.jpg"), title="X", source="https://x", why="y")


def test_render_has_a_vote_per_item_and_saves_to_db(tmp_path):
    run = tmp_path / "run"
    for n in range(3):
        survey.add(run, str(img(tmp_path / f"{n}.jpg")), title=f"<T{n}>", source=f"https://x/{n}",
                   why="award", tag="poster")
    out = tmp_path / "out"
    html = survey.render(run, out, "Waymark").read_text()
    assert html.count('class="item"') == 3
    assert html.count('<button type="button" data-vote="like"') == 3 and html.count('<button type="button" data-vote="dislike"') == 3
    assert "&lt;T0&gt;" in html and "<T0>" not in html
    assert 'claude.use("db")' in html and '"survey/current"' in html
    files = json.loads((out / "files.json").read_text())
    assert sorted(files) == sorted(re.findall(r'<img src="([^"]+)"', html))
    assert all((out / f).exists() for f in files)


def test_render_refuses_an_empty_survey(tmp_path):
    with pytest.raises(ValueError):
        survey.render(tmp_path / "run", tmp_path / "out", "X")


def test_cli_survey_add_and_canvas(tmp_path, capsys):
    run = tmp_path / "run"
    src = img(tmp_path / "a.jpg")
    assert main(["survey-add", str(run), str(src), "--title", "A", "--source", "https://x/1",
                 "--why", "new release", "--tag", "type"]) == 0
    assert "s001" in capsys.readouterr().out
    assert main(["survey-canvas", str(run), "--title", "Waymark", "--out", str(tmp_path / "out")]) == 0
    assert (tmp_path / "out" / "index.html").exists()


def test_keep_from_scout_records_the_search_page(tmp_path):
    run = tmp_path / "run"
    folder = run / "scout" / "survey"; folder.mkdir(parents=True)
    img(folder / "01.jpg"); img(folder / "02.jpg")
    (folder / "scout.json").write_text(json.dumps({"style": "survey", "notes": [], "items": [
        {"n": "01", "file": "01.jpg", "image_url": "https://cdn/1", "source": "https://www.cosmos.so/search/a", "note": "Cosmos"},
        {"n": "02", "file": "02.jpg", "image_url": "https://cdn/2", "source": "https://www.cosmos.so/search/a", "note": "Cosmos"}]}))
    kept = survey.keep(run, ["02", "1"], why="trending on Cosmos", tag="ui")
    assert [k["id"] for k in kept] == ["s001", "s002"]
    assert kept[0]["source_url"] == "https://cdn/2" and kept[0]["why"] == "trending on Cosmos"
    with pytest.raises(ValueError):
        survey.keep(run, ["09"], why="x")


def test_cli_survey_keep_reports_unknown_numbers(tmp_path, capsys):
    run = tmp_path / "run"
    folder = run / "scout" / "survey"; folder.mkdir(parents=True)
    img(folder / "01.jpg")
    (folder / "scout.json").write_text(json.dumps({"items": [
        {"n": "01", "file": "01.jpg", "image_url": "https://cdn/1", "source": "https://s", "note": "Cosmos"}]}))
    assert main(["survey-keep", str(run), "01", "--why", "trending", "--tag", "web"]) == 0
    assert "s001" in capsys.readouterr().out
    assert main(["survey-keep", str(run), "05", "--why", "x"]) == 1
