from taste.library.fetch import FakeFetcher, FetchError
from taste.library.sources import github_code, github_lists


def test_repo_table_is_complete():
    assert [r["slug"] for r in github_code.REPOS] == ["react-bits", "magicui", "vanta", "gl-transitions", "lygia", "animate-css", "tabler-icons", "lucide", "simple-icons"]


def test_react_bits_items(fixture):
    tree = fixture("github_code/tree.json")
    f = FakeFetcher(json={"react-bits/git/trees": tree}, text={"raw.githubusercontent.com/DavidHDev/react-bits": "export default function X(){}"})
    repo = github_code.REPOS[0]
    colls = list(github_code.repo_collections(repo, f))
    slugs = [c.slug for c, _ in colls]
    assert slugs and all(s.startswith("react-bits/") for s in slugs)
    it = colls[0][1][0]
    assert it.kind == "snippet" and it.meta["code"].startswith("export default") and it.meta["demo"].startswith("https://reactbits.dev/")
    assert it.key.startswith("react-bits:src/content/") and it.license == "MIT"


def test_react_bits_values_from_fixture(fixture):
    tree = fixture("github_code/tree.json")
    f = FakeFetcher(json={"git/trees": tree}, text={"raw.githubusercontent.com": "code"})
    (coll, items), = github_code.repo_collections(github_code.REPOS[0], f)
    assert coll.slug == "react-bits/animations" and coll.kind == "snippet"
    assert len(items) == 6
    it = next(i for i in items if "AnimatedContent" in i.key)
    assert it.key == "react-bits:src/content/Animations/AnimatedContent/AnimatedContent.jsx"
    assert it.title == "React Bits · AnimatedContent"
    assert it.page_url == it.meta["demo"] == "https://reactbits.dev/animations/animated-content"
    assert it.asset_url == it.meta["raw_url"] == "https://raw.githubusercontent.com/DavidHDev/react-bits/main/src/content/Animations/AnimatedContent/AnimatedContent.jsx"
    assert it.meta["truncated"] is False and it.meta["language"] == "jsx"
    assert "react-bits" in it.tags and "Animations" in it.tags
    assert ("get_json", "https://api.github.com/repos/DavidHDev/react-bits/git/trees/main?recursive=1") in f.calls


def test_two_groups_make_two_collections():
    tree = {"tree": [{"path": "src/content/Animations/A/A.jsx", "type": "blob"},
                     {"path": "src/content/TextAnimations/B/B.jsx", "type": "blob"},
                     {"path": "src/content/TextAnimations/B/B.css", "type": "blob"},
                     {"path": "src/content/TextAnimations/B", "type": "tree"}]}
    f = FakeFetcher(json={"git/trees": tree}, text={"raw.githubusercontent.com": "x"})
    colls = list(github_code.repo_collections(github_code.REPOS[0], f))
    assert [c.slug for c, _ in colls] == ["react-bits/animations", "react-bits/text-animations"]
    assert [len(i) for _, i in colls] == [1, 1]
    assert colls[1][1][0].meta["demo"] == "https://reactbits.dev/text-animations/b"


def test_ungrouped_repo_collection_and_icon_tags():
    tree = {"tree": [{"path": "icons/arrow-up.svg", "type": "blob"}, {"path": "icons/sub/x.svg", "type": "blob"}]}
    f = FakeFetcher(json={"git/trees": tree}, text={"raw.githubusercontent.com": "<svg/>"})
    repo = next(r for r in github_code.REPOS if r["slug"] == "lucide")
    (coll, items), = github_code.repo_collections(repo, f)
    assert coll.slug == "lucide/all" and coll.kind == "icon"
    assert len(items) == 1 and items[0].kind == "icon" and items[0].license == "ISC"
    assert items[0].meta["code"] == "<svg/>" and "icon" in items[0].tags


def test_code_is_truncated_at_8kb():
    f = FakeFetcher(json={"git/trees": {"tree": [{"path": "src/vanta.birds.js", "type": "blob"}]}},
                    text={"raw.githubusercontent.com": "x" * 20000})
    repo = next(r for r in github_code.REPOS if r["slug"] == "vanta")
    (_, items), = github_code.repo_collections(repo, f)
    assert len(items[0].meta["code"]) == 8192 and items[0].meta["truncated"] is True


def test_sample_cap_limits_raw_fetches():
    tree = {"tree": [{"path": f"icons/{n}.svg", "type": "blob"} for n in ("a", "b", "c", "d")]}
    f = FakeFetcher(json={"git/trees": tree}, text={"raw.githubusercontent.com": "<svg/>"})
    repo = next(r for r in github_code.REPOS if r["slug"] == "lucide")
    (_, items), = github_code.repo_collections(repo, f, max_items=2)
    assert len(items) == 2 and sum(1 for c in f.calls if c[0] == "get_text") == 2


def test_failed_raw_fetch_skips_the_file_not_the_repo():
    tree = {"tree": [{"path": f"icons/{n}.svg", "type": "blob"} for n in ("a", "b", "c")]}
    f = FakeFetcher(json={"git/trees": tree}, text={"/icons/b.svg": "<svg/>", "/icons/c.svg": "<svg id='c'/>"})
    repo = next(r for r in github_code.REPOS if r["slug"] == "lucide")
    (_, items), = github_code.repo_collections(repo, f)
    assert [i.key.rsplit("/", 1)[1] for i in items] == ["b.svg", "c.svg"]


def test_one_source_per_repo_and_list():
    from taste.library.sources import base
    slugs = [r["slug"] for r in github_code.REPOS] + [x["slug"] for x in github_lists.LISTS]
    assert len(slugs) == 14 and all(base.get(sl).info.tier == 1 for sl in slugs)
    info = base.get("lucide").info
    assert info.title == "Lucide" and info.home_url == "https://github.com/lucide-icons/lucide"
    assert base.get("awesome-fonts").info.home_url == "https://github.com/brabadu/awesome-fonts"


def test_repo_adapter_passes_cap():
    f = FakeFetcher(json={"git/trees": {"tree": [{"path": "icons/a.svg", "type": "blob"}, {"path": "icons/b.svg", "type": "blob"}]}},
                    text={"raw.githubusercontent.com": "<svg/>"})
    from taste.library.sources import base
    a = base.get("lucide")
    a.max_items = 1
    try:
        colls = list(a.collections(f))
    finally:
        a.max_items = None
    assert [c.slug for c, _ in colls] == ["lucide/all"] and len(colls[0][1]) == 1


def test_kebab_keeps_acronyms_together():
    assert github_code._kebab("ASCIIText") == "ascii-text"
    assert github_code._kebab("BlobCursor") == "blob-cursor"
    assert github_code._kebab("TextAnimations") == "text-animations"
    assert github_code._kebab("Aurora2D") in ("aurora2-d", "aurora-2d")


def test_icon_tags_are_deduped():
    f = FakeFetcher(json={"git/trees": {"tree": [{"path": "icons/a.svg", "type": "blob"}]}}, text={"raw.githubusercontent.com": "<svg/>"})
    (_, items), = github_code.repo_collections(next(r for r in github_code.REPOS if r["slug"] == "lucide"), f)
    assert items[0].tags == ["lucide", "icon"]


def test_parse_markdown_links_tables_and_bullets(fixture):
    rows = github_lists.parse_markdown_links(fixture("github_lists/design-resources.md"))
    assert rows and rows[0]["section"] and rows[0]["url"].startswith("http") and rows[0]["title"]
    rows2 = github_lists.parse_markdown_links(fixture("github_lists/awesome-design.md"))
    assert rows2 and all(r["url"].startswith("http") for r in rows2)


def test_parse_pins_values_from_each_fixture(fixture):
    rows = github_lists.parse_markdown_links(fixture("github_lists/design-resources.md"))
    assert next(r for r in rows if r["title"] == "Humaaans") == {"section": "UI Graphics", "title": "Humaaans", "url": "https://www.humaaans.com/", "description": "Cool illustrations of people with the ability to mix and match"}
    rows2 = github_lists.parse_markdown_links(fixture("github_lists/awesome-design.md"))
    assert next(r for r in rows2 if r["title"] == "Unsplash") == {"section": "Stock", "title": "Unsplash", "url": "https://unsplash.com/", "description": ""}
    assert next(r for r in rows2 if r["title"] == "Albumarium")["description"].startswith('"The best place')
    assert not any(r["section"].lower() == "table of contents" for r in rows)


def test_lists_collections(fixture):
    f = FakeFetcher(text={"design-resources-for-developers": fixture("github_lists/design-resources.md")})
    colls = list(github_lists.ADAPTERS[0].collections(f))
    assert colls and all(c.slug.startswith("design-resources/") and c.kind == "site" for c, _ in colls)
    assert colls[0][0].slug == "design-resources/ui-graphics"
    it = colls[0][1][0]
    assert it.key.startswith("design-resources:") and it.thumb_url is None and it.meta["description"] is not None
    f2 = FakeFetcher(text={"awesome-design/": fixture("github_lists/awesome-design.md")})
    c2 = list(github_lists.ADAPTERS[1].collections(f2))
    assert any(c.slug == "awesome-design/stock" for c, _ in c2)
