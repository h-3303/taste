import hashlib
import re

from ..models import CollectionDraft, ItemDraft, SourceInfo
from ..vocabulary import slugify
from .base import register

LISTS = [
    {"slug": "design-resources", "repo": "bradtraversy/design-resources-for-developers", "branch": "master", "file": "readme.md", "title": "Design Resources for Developers"},
    {"slug": "awesome-design", "repo": "gztchan/awesome-design", "branch": "master", "file": "README.md", "title": "Awesome Design"},
    {"slug": "awesome-design-tools", "repo": "goabstract/Awesome-Design-Tools", "branch": "master", "file": "README.md", "title": "Awesome Design Tools"},
    {"slug": "awesome-creative-coding", "repo": "terkelg/awesome-creative-coding", "branch": "main", "file": "readme.md", "title": "Awesome Creative Coding"},
    {"slug": "awesome-fonts", "repo": "brabadu/awesome-fonts", "branch": "master", "file": "README.md", "title": "Awesome Fonts"},
]
SECTION = re.compile(r"^#{2,3}\s+(.+?)\s*$")
TABLE = re.compile(r"^\|\s*\[([^\]]+)\]\((https?://[^)\s]+)\)\s*\|\s*([^|]*)\|")
BULLET = re.compile(r"^\s*[*-]\s+\[([^\]]+)\]\((https?://[^)\s]+)\)\s*(?:[-–—:]\s*)?(.*)$")
MIN_LINKS = 3


def parse_markdown_links(md: str) -> list[dict]:
    rows, section = [], ""
    for line in md.splitlines():
        s = SECTION.match(line)
        if s:
            section = s.group(1).strip("# ").strip()
            continue
        m = TABLE.match(line) or BULLET.match(line)
        if m and section and "table of contents" not in section.lower():
            rows.append({"section": section, "title": m.group(1).strip(), "url": m.group(2).strip(),
                         "description": (m.group(3) or "").strip().rstrip("|").strip()})
    return rows


def list_collections(lst: dict, fetch):
    url = f"https://raw.githubusercontent.com/{lst['repo']}/{lst['branch']}/{lst['file']}"
    rows = parse_markdown_links(fetch.get_text(url))
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(r["section"], []).append(r)
    for section, rs in groups.items():
        if len(rs) < MIN_LINKS:
            continue
        items = [ItemDraft(
            key=f"{lst['slug']}:{hashlib.sha1(r['url'].encode()).hexdigest()[:16]}", kind="site", title=r["title"],
            page_url=r["url"], asset_url=r["url"], thumb_url=None, tags=[slugify(section), lst["slug"]],
            meta={"description": r["description"], "list": lst["title"], "section": section}, license="list: see repo; site: its own")
            for r in rs]
        yield CollectionDraft(f"{lst['slug']}/{slugify(section)}", "site", f"{lst['title']}: {section}", query=section), items


class GithubListAdapter:
    """One registered source per LISTS entry."""

    def __init__(self, lst: dict):
        self.lst = lst
        self.info = SourceInfo(lst["slug"], lst["title"], f"https://github.com/{lst['repo']}", 1,
                               notes="link list parsed from a README; no thumbnails at sync (use --screenshots)")

    def collections(self, fetch):
        yield from list_collections(self.lst, fetch)


ADAPTERS = [register(GithubListAdapter(x)) for x in LISTS]
