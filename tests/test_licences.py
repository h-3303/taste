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
        # (the per-item header decides; see test_lygia_* below)
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


# the licence string every LYGIA item carries (from library/sources/github_code.py)
LYGIA_LICENSE = "BSD-3 (prosperity for some)"
LYGIA_BSD = """#include "../math/mod289.glsl"

/*
contributors: Patricio Gonzalez Vivo
description: Simple luma function
use: <float> luma(<vec3|vec4> color)
license:
    - Copyright (c) 2021 Patricio Gonzalez Vivo under the BSD-3-Clause license. (https://lygia.xyz/license)
*/

#ifndef FNC_LUMA
#define FNC_LUMA
float luma(vec3 c) { return dot(c, vec3(0.299, 0.587, 0.114)); }
#endif
"""
LYGIA_PROSPERITY = """/*
contributors: Patricio Gonzalez Vivo
description: Physically based lighting
use: <vec4> pbr(<Material> material)
license:
    - Copyright (c) 2021 Patricio Gonzalez Vivo under Prosperity License - https://prosperitylicense.com/versions/3.0.0
    - Copyright (c) 2021 Patricio Gonzalez Vivo under Patron License - https://lygia.xyz/license
*/

#ifndef FNC_PBR
#define FNC_PBR
#endif
"""
LYGIA_MIT = """/*
contributors: Stefan Gustavson, Ian McEwan
description: Simplex noise
license: MIT License (MIT) Copyright (c) 2011 Stefan Gustavson
*/
"""


def test_lygia_bsd_header_ships_as_file():
    assert classify("lygia", LYGIA_LICENSE, "https://lygia.xyz/color/luma", code=LYGIA_BSD) == "file"


def test_lygia_prosperity_header_ships_only_as_link():
    assert classify("lygia", LYGIA_LICENSE, "https://lygia.xyz/lighting/pbr", code=LYGIA_PROSPERITY) == "link"


@pytest.mark.parametrize("code", ["", "float f() { return 1.0; }", LYGIA_MIT, "/* no licence line */"])
def test_lygia_without_a_bsd_header_is_a_link(code):
    # the shared "BSD-3 (prosperity for some)" string alone decides nothing: unsure means link
    assert classify("lygia", LYGIA_LICENSE, "https://lygia.xyz/x", code=code) == "link"
    assert classify("lygia", "BSD-3-Clause", "https://lygia.xyz/x", code=code) == "link"
