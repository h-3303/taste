import copy

import pytest

from taste.boards.directions import suggest_palette, validate

POOL = {"images": [{"id": f"i{i:03}", "colours": ["#ff0000", "#00ff00"] if i % 2 else ["#0000ff"],
                    "style": str((i - 1) // 10 + 1)}          # i001-i010 gathered for style 1, ...
                   for i in range(1, 41)]}

AXES = [
    {"palette": "cool light", "density": "sparse", "type": "grotesk", "imagery": "print"},
    {"palette": "warm dark", "density": "dense", "type": "serif", "imagery": "photo"},
    {"palette": "neon", "density": "dense", "type": "display", "imagery": "3d"},
    {"palette": "earth", "density": "medium", "type": "mono", "imagery": "illustration"},
]


def good():
    return {"directions": [{
        "id": str(k + 1), "name": f"D{k}", "rationale": "Short reason.",
        "image_ids": [f"i{k * 10 + j:03}" for j in range(1, 10)],
        "palette": ["#111111", "#222222", "#333333", "#444444", "#555555"],
        "type": {"display": "Archivo Black", "text": "Inter"},
        "motifs": ["a", "b", "c"], "axes": AXES[k],
    } for k in range(4)]}


def test_good_is_valid():
    assert validate(good(), POOL) == []


@pytest.mark.parametrize("mutate,needle", [
    (lambda d: d["directions"].clear(), "at least 1 direction"),
    (lambda d: d["directions"][0].update(id="2"), 'ids must be "1" to "4" in order'),
    (lambda d: d["directions"][0].update(id=1), 'ids must be "1" to "4" in order'),
    (lambda d: d["directions"].reverse(), 'ids must be "1" to "4" in order'),
    (lambda d: d["directions"][0].update(palette=["#111111\n"] * 5), "palette"),
    (lambda d: d["directions"][0].update(type={"display": "Bad';x", "text": "Inter"}), "direction 1: bad font name"),
    (lambda d: d["directions"][0].update(type={"display": "Inter", "text": 'Bad"x'}), "direction 1: bad font name"),
    (lambda d: d["directions"][0].update(image_ids=["i001"] * 3), "8-60 images"),
    (lambda d: d["directions"][0]["image_ids"].__setitem__(0, "i999"), "unknown image i999"),
    (lambda d: d["directions"][0].update(palette=["#111"]), "palette"),
    (lambda d: d["directions"][0].update(rationale="a\nb\nc"), "rationale"),
    (lambda d: d["directions"][0].update(name=""), "name"),
    (lambda d: d["directions"][0].update(type={"display": "X"}), "type"),
    (lambda d: d["directions"][0].update(motifs=["a"]), "motifs"),
    (lambda d: d["directions"][1].update(axes=dict(AXES[0], imagery="photo")), "differ on"),
])
def test_invalid(mutate, needle):
    d = good()
    mutate(d)
    errors = validate(d, POOL)
    assert any(needle in e for e in errors), errors


def test_image_in_three_directions_rejected():
    d = good()
    for k in (1, 2):
        d["directions"][k]["image_ids"][0] = "i001"
    assert any("i001 used in 3 directions" in e for e in validate(d, POOL))


def test_suggest_palette_counts_colours():
    assert suggest_palette(["i001", "i003", "i002"], POOL, 2) == ["#ff0000", "#00ff00"]


def test_style_errors_shared_with_canvas():
    from taste.boards.directions import style_errors
    d = good()["directions"][1]
    assert style_errors(d) == []
    d["palette"][0] = "red;background:url(x)"
    assert style_errors(d) == ["direction 2: palette must be 5 #rrggbb colours"]


def test_board_must_be_mostly_its_own_style():
    d = good()
    d["directions"][0]["image_ids"] = [f"i{j:03}" for j in range(1, 5)] + [f"i{j:03}" for j in range(31, 36)]
    errs = validate(d, POOL)
    assert any("direction 1: only 4 of 9 images" in e for e in errs), errs
    d["directions"][0]["image_ids"] = [f"i{j:03}" for j in range(1, 6)] + [f"i{j:03}" for j in range(31, 35)]
    assert validate(d, POOL) == []                       # 5 of 9 own-style: a majority, borrowing allowed


def ten():
    pool = {"images": [{"id": f"i{i:03}", "colours": ["#ff0000"], "style": str((i - 1) // 50 + 1)}
                       for i in range(1, 501)]}
    pals, dens = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"], ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"]
    d = {"directions": [{
        "id": str(k + 1), "name": f"D{k}", "rationale": "Short reason.",
        "image_ids": [f"i{k * 50 + j:03}" for j in range(1, 51)],
        "palette": ["#111111", "#222222", "#333333", "#444444", "#555555"],
        "type": {"display": "Archivo Black", "text": "Inter"},
        "motifs": ["a", "b", "c"],
        "axes": {"palette": pals[k], "density": dens[k], "type": "t", "imagery": "m"},
    } for k in range(10)]}
    return d, pool


def test_any_number_of_directions_with_big_boards():
    d, pool = ten()
    assert validate(d, pool) == []                      # ten boards of fifty images each
    d["directions"] = d["directions"][:3]
    assert validate(d, pool) == []


def test_board_over_sixty_images_rejected():
    d, pool = ten()
    d["directions"][0]["image_ids"] += [f"i{j:03}" for j in range(451, 462)]   # 61, some borrowed
    assert any("8-60 images" in e for e in validate(d, pool))
