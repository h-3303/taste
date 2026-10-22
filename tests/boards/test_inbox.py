from taste.boards.inbox import take_inbox


def test_take_inbox_moves_images_with_sources(tmp_path):
    inbox, dest = tmp_path / "inbox", tmp_path / "raw"
    inbox.mkdir()
    (inbox / "poster one.jpg").write_bytes(b"x")
    (inbox / "b.webp").write_bytes(b"x")
    (inbox / "notes.txt").write_text("ignore me")
    (inbox / "sources.txt").write_text("poster one.jpg\thttps://www.are.na/block/1\n\nbad line\n")
    cands = take_inbox(inbox, dest)
    by = {c.path.name: c for c in cands}
    assert set(by) == {"inbox-poster one.jpg", "inbox-b.webp"}
    assert by["inbox-poster one.jpg"].source_url == "https://www.are.na/block/1"
    assert by["inbox-b.webp"].source_url == ""
    assert all(c.path.parent == dest and c.kind == "inbox" for c in cands)
    assert not (inbox / "b.webp").exists()          # moved, not copied
    assert (inbox / "notes.txt").exists()            # non-images untouched
    assert not (inbox / "sources.txt").exists()      # consumed


def test_take_inbox_missing_folder(tmp_path):
    assert take_inbox(tmp_path / "nope", tmp_path / "raw") == []


def test_take_inbox_recollects_earlier_images(tmp_path):
    inbox, dest = tmp_path / "inbox", tmp_path / "raw"
    inbox.mkdir()
    (inbox / "a.jpg").write_bytes(b"first")
    (inbox / "sources.txt").write_text("a.jpg\thttps://x/a\n")
    take_inbox(inbox, dest)
    (inbox / "a.jpg").write_bytes(b"second")              # same name again: must not overwrite
    (inbox / "b.jpg").write_bytes(b"x")
    (inbox / "sources.txt").write_text("a.jpg\thttps://x/a2\nb.jpg\thttps://x/b\n")
    cands = take_inbox(inbox, dest)
    assert {c.path.name: c.source_url for c in cands} == {
        "inbox-a.jpg": "https://x/a", "inbox-a-2.jpg": "https://x/a2", "inbox-b.jpg": "https://x/b"}
    assert (dest / "inbox-a.jpg").read_bytes() == b"first"
    assert {c.title for c in cands} == {"a", "a-2", "b"}
    assert all(c.kind == "inbox" and c.source_note == "inbox" for c in cands)


def test_style_folders_tag_images_and_notes(tmp_path):
    inbox, dest = tmp_path / "inbox", tmp_path / "raw"
    (inbox / "2").mkdir(parents=True)
    (inbox / "2" / "card.webp").write_bytes(b"x")
    (inbox / "2" / "sources.txt").write_text("card.webp\thttps://mobbin.com/screens/1\tMobbin\n")
    (inbox / "loose.jpg").write_bytes(b"x")
    cands = take_inbox(inbox, dest)
    by = {c.title: c for c in cands}
    assert by["card"].style == "2" and by["card"].source_note == "Mobbin"
    assert by["card"].source_url == "https://mobbin.com/screens/1"
    assert by["loose"].style is None and by["loose"].source_note == "inbox"
    assert not (inbox / "2" / "sources.txt").exists()
    again = {c.title: (c.style, c.source_note) for c in take_inbox(inbox, dest)}   # re-gather keeps tags
    assert again == {"card": ("2", "Mobbin"), "loose": (None, "inbox")}


def test_non_style_subfolders_ignored(tmp_path):
    inbox, dest = tmp_path / "inbox", tmp_path / "raw"
    (inbox / "misc").mkdir(parents=True)
    (inbox / "misc" / "a.jpg").write_bytes(b"x")
    assert take_inbox(inbox, dest) == []
    assert (inbox / "misc" / "a.jpg").exists()


def test_sources_fourth_column_is_the_title(tmp_path):
    inbox, dest = tmp_path / "inbox", tmp_path / "raw"
    (inbox / "1").mkdir(parents=True)
    (inbox / "1" / "x1.jpg").write_bytes(b"x")
    (inbox / "1" / "sources.txt").write_text("x1.jpg\thttps://c/s\tCosmos\tCosmos · swiss poster #07\n")
    (c,) = take_inbox(inbox, dest)
    assert c.title == "Cosmos · swiss poster #07"
    (again,) = take_inbox(inbox, dest)
    assert again.title == "Cosmos · swiss poster #07"


def test_any_numbered_style_folder_is_tagged(tmp_path):
    inbox, dest = tmp_path / "inbox", tmp_path / "raw"
    (inbox / "10").mkdir(parents=True)
    (inbox / "10" / "a.jpg").write_bytes(b"x")
    got = take_inbox(inbox, dest)
    assert [c.style for c in got] == ["10"]
