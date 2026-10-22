import html as _html
import re


def og_image(page: str) -> str | None:
    m = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', page) or \
        re.search(r'<meta[^>]+content="([^"]+)"[^>]+property="og:image"', page)
    return _html.unescape(m.group(1)) if m else None


def title(page: str) -> str:
    m = re.search(r"<title>([^<]*)</title>", page)
    return _html.unescape(m.group(1)).strip() if m else ""


def unique(seq):
    return list(dict.fromkeys(seq))
