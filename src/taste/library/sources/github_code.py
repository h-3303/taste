import re

from ..fetch import Blocked, FetchError
from ..models import CollectionDraft, ItemDraft, SourceInfo
from ..vocabulary import slugify
from .base import register

MAX_CODE = 8192
REPOS = [
    {"slug": "react-bits", "repo": "DavidHDev/react-bits", "branch": "main", "kind": "snippet", "license": "MIT", "title": "React Bits",
     "include": r"^src/content/(?P<group>[^/]+)/(?P<name>[^/]+)/(?P=name)\.jsx$", "demo": "https://reactbits.dev/{group_kebab}/{kebab}", "install": "copy the component; see the demo page"},
    {"slug": "magicui", "repo": "magicuidesign/magicui", "branch": "main", "kind": "snippet", "license": "MIT", "title": "Magic UI",
     "include": r"^apps/www/registry/magicui/(?P<name>[a-z0-9-]+)\.tsx$", "demo": "https://magicui.design/docs/components/{name}", "install": "npx shadcn@latest add \"https://magicui.design/r/{name}\""},
    {"slug": "vanta", "repo": "tengbao/vanta", "branch": "master", "kind": "snippet", "license": "MIT", "title": "Vanta.js",
     "include": r"^src/vanta\.(?P<name>[a-z0-9]+)\.js$", "demo": "https://www.vantajs.com/?effect={name}", "install": "npm i vanta three"},
    {"slug": "gl-transitions", "repo": "gl-transitions/gl-transitions", "branch": "master", "kind": "snippet", "license": "MIT", "title": "GL Transitions",
     "include": r"^transitions/(?P<name>[^/]+)\.glsl$", "demo": "https://gl-transitions.com/editor/{name}", "install": "npm i gl-transitions"},
    {"slug": "lygia", "repo": "patriciogonzalezvivo/lygia", "branch": "main", "kind": "snippet", "license": "BSD-3 (prosperity for some)", "title": "LYGIA shader library",
     "include": r"^(?P<group>color|generative|filter|lighting|sdf|draw)/(?P<name>[^/]+)\.glsl$", "demo": "https://lygia.xyz/{group}/{name}", "install": "#include \"lygia/{group}/{name}.glsl\""},
    {"slug": "animate-css", "repo": "animate-css/animate.css", "branch": "main", "kind": "snippet", "license": "Hippocratic 2.1", "title": "animate.css",
     "include": r"^source/(?P<group>[^/_][^/]*)/(?P<name>[^/]+)\.css$", "demo": "https://animate.style/#{name}", "install": "npm i animate.css"},
    {"slug": "tabler-icons", "repo": "tabler/tabler-icons", "branch": "main", "kind": "icon", "license": "MIT", "title": "Tabler Icons",
     "include": r"^icons/(?P<group>outline|filled)/(?P<name>[^/]+)\.svg$", "demo": "https://tabler.io/icons/icon/{name}", "install": "npm i @tabler/icons"},
    {"slug": "lucide", "repo": "lucide-icons/lucide", "branch": "main", "kind": "icon", "license": "ISC", "title": "Lucide",
     "include": r"^icons/(?P<name>[^/]+)\.svg$", "demo": "https://lucide.dev/icons/{name}", "install": "npm i lucide-react"},
    {"slug": "simple-icons", "repo": "simple-icons/simple-icons", "branch": "develop", "kind": "icon", "license": "CC0", "title": "Simple Icons",
     "include": r"^icons/(?P<name>[^/]+)\.svg$", "demo": "https://simpleicons.org/?q={name}", "install": "npm i simple-icons"},
]


def _kebab(s: str) -> str:
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", re.sub(r"(.)([A-Z][a-z]+)", r"\1-\2", s))
    return s.lower().replace("_", "-")


def repo_collections(repo: dict, fetch, max_items: int | None = None):
    url = f"https://api.github.com/repos/{repo['repo']}/git/trees/{repo['branch']}?recursive=1"
    tree = fetch.get_json(url).get("tree", [])
    rx = re.compile(repo["include"])
    groups: dict[str, list[tuple[str, dict]]] = {}
    for t in tree:
        m = rx.match(t.get("path", ""))
        if m and t.get("type", "blob") == "blob":
            g = m.groupdict()
            groups.setdefault(g.get("group") or "", []).append((t["path"], g))
    for group, paths in sorted(groups.items()):
        items = []
        for path, g in paths[:max_items] if max_items else paths:
            raw = f"https://raw.githubusercontent.com/{repo['repo']}/{repo['branch']}/{path}"
            try:
                code = fetch.get_text(raw)
            except Blocked:
                raise
            except FetchError:
                continue   # one unreadable file skips that item only
            name = g["name"]
            fmt = {"name": name, "group": group, "kebab": _kebab(name), "group_kebab": _kebab(group)}
            items.append(ItemDraft(
                key=f"{repo['slug']}:{path}", kind=repo["kind"], title=f"{repo['title']} · {name}",
                page_url=repo["demo"].format(**fmt), asset_url=raw, thumb_url=None,
                tags=list(dict.fromkeys([repo["slug"], repo["kind"], *(["icon"] if repo["kind"] == "icon" else []), *([group] if group else [])])),
                meta={"code": code[:MAX_CODE], "truncated": len(code) > MAX_CODE, "raw_url": raw, "demo": repo["demo"].format(**fmt),
                      "install": repo["install"].format(**fmt), "path": path, "language": path.rsplit(".", 1)[-1]},
                license=repo["license"]))
        slug = f"{repo['slug']}/" + (slugify(_kebab(group)) if group else "all")
        yield CollectionDraft(slug, repo["kind"], f"{repo['title']}" + (f": {group}" if group else ""), query=group), items


class GithubRepoAdapter:
    """One registered source per REPOS entry; binds one config to the shared repo_collections."""
    max_items: int | None = None   # set by sync before collections() runs

    def __init__(self, repo: dict):
        self.repo = repo
        self.info = SourceInfo(repo["slug"], repo["title"], f"https://github.com/{repo['repo']}", 1,
                               notes="one tree call, raw files from raw.githubusercontent.com")

    def collections(self, fetch):
        yield from repo_collections(self.repo, fetch, self.max_items)


ADAPTERS = [register(GithubRepoAdapter(r)) for r in REPOS]
