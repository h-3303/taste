from taste.boards.vaultmedia import vault_media


def test_vault_media_finds_post_images(tmp_path):
    media = tmp_path / "Sources" / "media" / "someone"
    media.mkdir(parents=True)
    for n in ("ABC_1.jpg", "ABC_2.png", "ABC.mp4", "XYZ_1.jpg"):
        (media / n).write_bytes(b"x")
    cands = vault_media(tmp_path, ["ABC", "MISSING"])
    assert sorted(c.path.name for c in cands) == ["ABC_1.jpg", "ABC_2.png"]
    assert {c.source_note for c in cands} == {"ig-ABC"}
    assert cands[0].source_url == "https://www.instagram.com/p/ABC/"
    assert cands[0].kind == "vault"
