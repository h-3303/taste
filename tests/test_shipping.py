"""Shipping checks: what goes out with the plugin carries no personal text, the manifests agree, every skill is
well formed and names only real commands, and a seed built from a mixed library holds no gallery thumbnails."""
import json
import re
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from taste import cli, licences, seed
from taste.connectors import REGISTRY
from taste.library import db

ROOT = Path(__file__).resolve().parent.parent
SHIPPED = ["skills", "src/taste", "README.md", ".claude-plugin"]
FORBIDDEN = [r"moiraidigital", r"/home/h\b", r"Documents/", r"\bh's\b", r"\bh (says|picks|wants|marks|likes|decides)\b"]
SKILLS = ("taste", "taste-refine", "taste-library")
_BINARY = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pyc", ".zip", ".db", ".ico", ".woff", ".woff2"}


def shipped_text_files(roots):
    out = []
    for name in roots:
        p = ROOT / name
        assert p.exists(), f"{name} is missing"
        for f in ([p] if p.is_file() else sorted(p.rglob("*"))):
            if f.is_file() and "__pycache__" not in f.parts and f.suffix.lower() not in _BINARY:
                out.append(f)
    return out


def test_no_personal_text_in_shipped_files():
    hits = []
    for path in shipped_text_files(SHIPPED):
        text = path.read_text(encoding="utf-8")
        for pat in FORBIDDEN:
            for m in re.finditer(pat, text):
                hits.append(f"{path.relative_to(ROOT)}: {m.group(0)!r}")
    assert not hits, "\n".join(hits)


def test_manifests_parse_and_agree():
    plugin = json.loads((ROOT / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    market = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
    assert plugin["name"] == market["plugins"][0]["name"] == market["name"] == "taste"
    assert plugin["version"] == "0.1.0" == cli.VERSION.split()[-1]
    assert plugin["author"] == {"name": "h-3303"} and market["owner"] == {"name": "h-3303"}
    assert plugin["repository"] == "https://github.com/h-3303/taste"
    assert plugin["description"] and plugin["keywords"]
    assert market["$schema"] == "https://anthropic.com/claude-code/marketplace.schema.json"
    assert len(market["plugins"]) == 1
    assert market["plugins"][0]["source"] == "./" and market["plugins"][0]["category"] == "design"


def _frontmatter(text: str) -> dict:
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    assert m, "no YAML frontmatter"
    out = yaml.safe_load(m.group(1))   # Claude Code parses it as YAML: a bare ": " in a value breaks it
    assert isinstance(out, dict)
    return out


@pytest.mark.parametrize("name", SKILLS)
def test_every_skill_has_frontmatter_name_and_description(name):
    fm = _frontmatter((ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8"))
    assert fm.get("name") == name
    assert len(fm.get("description", "")) > 40
    assert "Use when" in fm["description"]


def test_no_skill_folder_without_a_skill():
    assert sorted(p.name for p in (ROOT / "skills").iterdir() if p.is_dir()) == sorted(SKILLS)


def test_taste_skill_keeps_the_judgement_rules():
    text = (ROOT / "skills/taste/SKILL.md").read_text(encoding="utf-8")
    for phrase in ("**Beauty, not theme.**", "**Style is not subject.**",
                   "Never scrape Are.na, Artvee, eMuseum, Gurafiku or Design Reviewed",
                   '"db": {}, "user": {}', "demo_at", "files.json", "`pass: <stage> <n>`"):
        assert phrase in text, phrase


_SUBS = {"round": {"render", "ingest", "steer", "final"}, "refine": {"check", "apply"},
         "profile": {"show", "project", "apply"}, "lib": cli._LIB_USER, "seed": {"install"},
         "maintainer": {"sync", "install-timer", "seed-build"}}
_SUBS["connect"] = _SUBS["disconnect"] = {*REGISTRY, "obscura"}


def _named_commands():
    """Every `taste <cmd> [<sub>]` written in backticks in the skills and README."""
    found = set()
    for path in [*(ROOT / "skills").rglob("SKILL.md"), ROOT / "README.md"]:
        for code in re.findall(r"`([^`\n]+)`", path.read_text(encoding="utf-8")):
            for m in re.finditer(r"(?:^|[\s(|;&])taste ([a-z][a-z-]*|--version)(?: ([a-z][a-z-]*))?", code):
                found.add((m.group(1), m.group(2), path.name))
    return found


def _boards_command(cmd: str) -> bool:
    try:
        cli.main([cmd, "--help"])
    except SystemExit as e:
        return e.code == 0
    return False


def test_every_command_the_docs_name_exists(capsys):
    named = _named_commands()
    assert len({c for c, _, _ in named}) >= 15, "the skills should name the real command surface"
    bad = []
    for cmd, sub, where in sorted(named, key=str):
        if cmd == "--version" or cmd in cli._COMMANDS:
            if cmd in _SUBS and sub is not None and sub not in _SUBS[cmd]:
                bad.append(f"{where}: taste {cmd} {sub}")
        elif not _boards_command(cmd):
            bad.append(f"{where}: taste {cmd}")
    capsys.readouterr()
    assert not bad, "\n".join(bad)


# one row per source in the spec's Library section (plus a banned-site row and the user's own additions)
FILE_ROWS = ["googlefonts", "fontsource", "fontshare", "collletttivo", "ambientcg", "polyhaven", "github-data",
             "react-bits", "magicui", "gl-transitions", "vanta", "tabler-icons", "lucide", "simple-icons", "animate-css"]
LINK_ROWS = ["cosmos", "designspiration", "savee", "pinterest", "behance", "cari", "archive", "lospec",
             "design-resources", "awesome-design", "awwwards", "darkdesign", "siteinspire", "landbook", "godly",
             "texturelabs", "curated"]


@pytest.fixture
def mixed_lib(tmp_path):
    thumbs = tmp_path / "thumbs"; thumbs.mkdir()
    conn = db.connect(tmp_path / "lib.db")
    source_of = {}
    rows = ([(s, "OFL", "https://ex.test/p") for s in FILE_ROWS]
            + [("lygia", "BSD-3-Clause", "https://lygia.xyz/a"), ("lygia", "Prosperity", "https://lygia.xyz/b")]
            + [(s, "", "https://ex.test/p") for s in LINK_ROWS]
            + [("metalforge", "proprietary", "https://ex.test/p"), ("mine", "", "https://ex.test/p"),
               ("cosmos", "", "https://www.are.na/block/1")])
    for k, (src, lic, page) in enumerate(rows):
        iid = f"it{k:03d}"
        (thumbs / f"{iid}.jpg").write_bytes(b"jpg")
        conn.execute("INSERT OR IGNORE INTO sources(slug, title, tier, policy) VALUES (?,?,?,?)", (src, src, 1, "sync"))
        conn.execute("INSERT INTO items(id,key,source,kind,title,page_url,asset_url,thumb,tags,meta,license,added_at,last_seen)"
                     " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (iid, f"{src}:{k}", src, "image", f"t{k}", page, "", f"thumbs/{iid}.jpg", "[]", "{}", lic, "t", "t"))
        source_of[iid] = (src, lic)
    conn.commit()
    return SimpleNamespace(conn=conn, thumbs=thumbs, source_of=source_of)


def thumbs_in(archive: Path) -> list[str]:
    return [Path(n).stem for n in zipfile.ZipFile(archive).namelist() if n.startswith("thumbs/")]


def test_seed_from_a_mixed_library_ships_no_gallery_thumbnails(mixed_lib, tmp_path):
    rep = seed.build_seed(mixed_lib.conn, mixed_lib.thumbs, tmp_path / "s.zip")
    shipped = [mixed_lib.source_of[n] for n in thumbs_in(tmp_path / "s.zip")]
    assert {s for s, _ in shipped} <= licences.FILE_SOURCES | {"lygia"}
    assert {s for s, _ in shipped} == set(FILE_ROWS) | {"lygia"}
    assert ("lygia", "Prosperity") not in shipped
    assert (rep.files, rep.links, rep.skipped) == (len(FILE_ROWS) + 1, len(LINK_ROWS) + 1, 3)


def test_refine_skill_takes_pass_numbers_from_render():
    text = (ROOT / "skills/taste-refine/SKILL.md").read_text(encoding="utf-8")
    assert text.count("`pass: refine <n>`") >= 1 and "`pass: review <n>`" in text
