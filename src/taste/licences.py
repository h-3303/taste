"""Decide whether a library item may ship with the plugin as a file, only as a link, or never."""

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


def classify(source: str, license: str, page_url: str = "", asset_url: str = "") -> Shipping:
    if banned(page_url) or banned(asset_url):
        return "never"
    if source in PRIVATE_SOURCES:
        return "never"
    if source in FILE_SOURCES:
        return "file"
    if source == "lygia":
        return "file" if license.startswith("BSD") else "link"
    if _is_http(page_url):
        return "link"
    return "never"
