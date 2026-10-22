"""Decide whether a library item may ship with the plugin as a file, only as a link, or never."""

import re
from typing import Literal
from urllib.parse import urlparse

from taste.library.fetch import banned

Shipping = Literal["file", "link", "never"]

# proprietary, or the user's own additions: private, never shipped
PRIVATE_SOURCES = {"metalforge", "mine"}

# licences that allow redistributing the file itself
FILE_SOURCES = {
    "googlefonts", "fontsource", "fontshare", "collletttivo", "ambientcg", "polyhaven",
    "github-data", "react-bits", "magicui", "gl-transitions", "vanta", "tabler-icons",
    "lucide", "simple-icons", "animate-css",
}


def _is_http(url: str) -> bool:
    parts = urlparse(url)
    return parts.scheme in ("http", "https") and bool(parts.netloc)


_HEADER = re.compile(r"/\*(.*?)\*/", re.S)


def lygia_header_is_bsd(code: str) -> bool:
    """LYGIA files mix BSD-3 and Prosperity/Patron; only the licence line in a file's own header comment tells."""
    m = _HEADER.search(code[:4096] if code else "")
    if not m:
        return False
    head = m.group(1).lower()
    at = head.find("license")
    if at < 0:
        return False
    lic = head[at:]
    if "prosperity" in lic or "patron" in lic:
        return False
    return "bsd" in lic


def classify(source: str, license: str, page_url: str = "", asset_url: str = "", code: str = "") -> Shipping:
    if banned(page_url) or banned(asset_url):
        return "never"
    if source in PRIVATE_SOURCES:
        return "never"
    if source in FILE_SOURCES:
        return "file"
    if source == "lygia":
        # the shared licence string ("BSD-3 (prosperity for some)") decides nothing; unsure means link
        return "file" if lygia_header_is_bsd(code) else "link"
    if _is_http(page_url):
        return "link"
    return "never"
