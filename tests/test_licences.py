import pytest

from taste.licences import FILE_SOURCES, classify


@pytest.mark.parametrize(
    ("source", "license", "page_url", "asset_url", "expected"),
    [
        # rule 1: a banned host on either URL is never shipped, whatever the source
        ("polyhaven", "CC0", "https://www.are.na/x", "", "never"),
        ("cosmos", "see source page", "", "https://artvee.com/a.jpg", "never"),
        ("googlefonts", "OFL", "https://designreviewed.com/x", "https://designreviewed.com/a.png", "never"),
        ("lygia", "BSD-3-Clause", "", "https://emuseum.ch/a.png", "never"),
        # rule 2: proprietary and private sources never ship
        ("metalforge", "CC0", "https://example.com/p", "", "never"),
        ("mine", "", "https://example.com/p", "https://example.com/a.png", "never"),
        ("mine", "", "", "", "never"),
        # rule 4: lygia ships as a file only under BSD, otherwise as a link
        ("lygia", "BSD-3-Clause", "https://lygia.xyz/x", "", "file"),
        ("lygia", "Prosperity", "https://lygia.xyz/x", "", "link"),
        ("lygia", "Prosperity", "", "", "link"),
        # rule 5: any other source with an http(s) page is a link
        ("cosmos", "see source page", "https://www.cosmos.so/x", "", "link"),
        ("curated", "curated: see origin", "https://example.com/x", "", "link"),
        ("lospec", "CC-BY", "https://lospec.com/x", "", "link"),
        ("awwwards", "screenshot © site owner; reference only", "https://www.awwwards.com/x", "", "link"),
        # rule 5: no usable http(s) page URL means never
        ("unknown", "", "", "", "never"),
        ("unknown", "", "ftp://example.com/x", "", "never"),
        ("unknown", "", "notaurl", "", "never"),
    ],
)
def test_classify(source, license, page_url, asset_url, expected):
    assert classify(source, license, page_url=page_url, asset_url=asset_url) == expected


@pytest.mark.parametrize("source", sorted(FILE_SOURCES))
def test_file_sources_ship_as_file(source):
    # rule 3: every file source ships as a file, and empty URLs do not count as banned
    assert classify(source, "OFL", page_url="https://example.com/p") == "file"
    assert classify(source, "OFL") == "file"


def test_file_sources_are_the_brief_list():
    assert FILE_SOURCES == {
        "googlefonts", "fontsource", "fontshare", "collletttivo", "ambientcg", "polyhaven",
        "github-data", "react-bits", "magicui", "gl-transitions", "vanta", "tabler-icons",
        "lucide", "simple-icons", "animate-css",
    }
