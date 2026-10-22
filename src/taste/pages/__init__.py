"""Stage pages: one shared frame (db binding, votes, notes, requests) and the pages built on it."""
import json
import shutil
from pathlib import Path
from urllib.parse import urlsplit

from jinja2 import Environment, PackageLoader

from .. import rounds
from ..boards.run import Run, clean_text

env = Environment(loader=PackageLoader("taste.pages"), autoescape=True)

PAGES = {"broad": "broad.html.j2", "boards": "boards.html.j2", "directions": "directions.html.j2",
         "refine": "refine.html.j2", "review": "review.html.j2"}
NEGATIVE = ("dislike", "drop")
LIBRARY_DOC = "library/current"


def _link(url) -> str:
    return url if isinstance(url, str) and urlsplit(url).scheme in ("http", "https") else ""


def _fresh(out_dir: Path) -> Path:
    """Clear an earlier render in out_dir (index.html, img/, files.json)."""
    out_dir = Path(out_dir)
    shutil.rmtree(out_dir / "img", ignore_errors=True)
    for name in ("index.html", "files.json"):
        (out_dir / name).unlink(missing_ok=True)
    (out_dir / "img").mkdir(parents=True)
    return out_dir


def _write(out_dir: Path, template: str, files: dict, **ctx) -> Path:
    (out_dir / "index.html").write_text(env.get_template(template).render(**ctx), encoding="utf-8")
    (out_dir / "files.json").write_text(json.dumps(files, indent=2), encoding="utf-8")
    return out_dir / "index.html"


def _votes(stage: str) -> list[dict]:
    return [{"value": v, "label": v.title(), "tone": "neg" if v in NEGATIVE else "pos"} for v in rounds.VOTES[stage]]


def render_round(run, stage: str, title: str, out_dir: Path, repeat_of: int | None = None) -> Path:
    """Render the page for a new pass of `stage` and start its record, so the page and record show the same items."""
    if stage not in PAGES:
        raise ValueError(f"stage {stage} has no page yet")
    run = run if isinstance(run, Run) else Run(run)
    if stage == "boards":
        return _render_boards(run, stage, title, Path(out_dir), repeat_of)
    if stage == "directions":
        return _render_directions(run, stage, title, Path(out_dir), repeat_of)
    if stage == "refine":
        return _render_refine(run, stage, title, Path(out_dir), repeat_of)
    if stage == "review":
        return _render_review(run, stage, title, Path(out_dir), repeat_of)
    from ..boards import survey
    items = survey.load(run.path)
    if not items:
        raise ValueError("the survey is empty: add items with survey-add first")
    out_dir = _fresh(out_dir)
    files, cards = {}, []
    for it in items:
        rel = f"img/{it['file']}"
        src = run.path / "survey" / "img" / it["file"]
        shutil.copy2(src, out_dir / rel)
        files[rel] = str(src.resolve())
        tag = clean_text(it.get("tag", ""), 24, markdown=False)
        cards.append({"id": it["id"], "src": rel, "link": _link(it.get("source_url")), "tag": tag,
                      "title": clean_text(it["title"], markdown=False),
                      "sub": " · ".join(x for x in (clean_text(it.get("why", ""), 160, markdown=False), tag, it["id"]) if x)})
    r = rounds.start(run, stage, [c["id"] for c in cards], repeat_of=repeat_of)
    return _write(out_dir, PAGES[stage], files, title=clean_text(title, markdown=False), items=cards,
                  tags=sorted({c["tag"] for c in cards if c["tag"]}), votes=_votes(stage),
                  doc=f"rounds/{stage}-{r.n}", repeat_of=repeat_of, n=r.n)


def _render_boards(run: Run, stage: str, title: str, out_dir: Path, repeat_of: int | None) -> Path:
    """One item per board (`d<direction id>`) and per image on it (`<direction id>/<image id>`)."""
    from ..boards.canvas import build_boards, check_directions
    directions, pool = run.read("directions.json"), run.read("pool.json")
    check_directions(directions)
    out_dir = _fresh(out_dir)
    boards, files, font_urls = build_boards(directions, pool, run.images, out_dir)
    shown = [x for b in boards for x in (f"d{b['id']}", *(f"{b['id']}/{it['id']}" for it in b["items"]))]
    r = rounds.start(run, stage, shown, repeat_of=repeat_of)
    return _write(out_dir, PAGES[stage], files, title=clean_text(title, markdown=False), boards=boards, items=boards,
                  font_urls=font_urls, tags=[], votes=_votes(stage), doc=f"rounds/{stage}-{r.n}",
                  repeat_of=repeat_of, n=r.n)


def _render_directions(run: Run, stage: str, title: str, out_dir: Path, repeat_of: int | None) -> Path:
    """One column per direction: the whole direction (`<id>`) and its five parts (`<id>:<part>`), plus the mixer."""
    from ..boards.canvas import build_boards, check_directions
    from ..combine import PARTS
    directions, pool = run.read("directions.json"), run.read("pool.json")
    check_directions(directions)
    out_dir = _fresh(out_dir)
    boards, files, font_urls = build_boards(directions, pool, run.images, out_dir)
    for b in boards:
        tex = set((b.get("sections") or {}).get("texture", []))
        b["texture"] = [it for it in b["items"] if it["id"] in tex]
        b["imagery"] = [it for it in b["items"] if it["id"] not in tex]
        b["name"] = clean_text(b["name"], 60, markdown=False)
        b["rationale"] = clean_text(b.get("rationale", ""), 240, markdown=False)
    shown = [x for b in boards for x in (b["id"], *(f"{b['id']}:{p}" for p in PARTS))]
    r = rounds.start(run, stage, shown, repeat_of=repeat_of)
    return _write(out_dir, PAGES[stage], files, title=clean_text(title, markdown=False), boards=boards, items=boards,
                  parts=PARTS, names={b["id"]: b["name"] for b in boards}, font_urls=font_urls, tags=[], votes=_votes(stage), doc=f"rounds/{stage}-{r.n}",
                  repeat_of=repeat_of, n=r.n)


def _render_refine(run: Run, stage: str, title: str, out_dir: Path, repeat_of: int | None) -> Path:
    """One row per layer: its note (`<layer>`) and its options as stills (`<layer>:<option id>`), one pick each."""
    from .. import refine
    n = rounds.next_n(run, stage)
    doc = refine.load_options(run, n)
    errs = refine.check_options(doc, root=run.path)
    if errs:
        raise ValueError(f"{refine.options_name(n)}: " + "; ".join(errs))
    out_dir = _fresh(out_dir)
    files, layers = {}, []
    for layer in refine.layers_of(doc):
        opts = []
        for o in doc["layers"][layer]:
            src = (run.path / o["still"]).resolve()
            rel = f"img/{layer}-{o['id']}{src.suffix.lower()}"
            shutil.copy2(src, out_dir / rel)
            files[rel] = str(src)
            opts.append({"id": f"{layer}:{o['id']}", "src": rel, "label": clean_text(o["label"], 80, markdown=False),
                         "detail": clean_text(o.get("detail", ""), 240, markdown=False)})
        layers.append({"name": layer, "options": opts})
    r = rounds.start(run, stage, refine.shown_ids(doc), repeat_of=repeat_of)
    return _write(out_dir, PAGES[stage], files, title=clean_text(title, markdown=False), layers=layers, items=[],
                  kind=doc["kind"], tags=[], votes=_votes(stage), doc=f"rounds/{stage}-{r.n}",
                  repeat_of=repeat_of, n=r.n)


def _render_review(run: Run, stage: str, title: str, out_dir: Path, repeat_of: int | None) -> Path:
    """One tick (`pick`) per proposal for the general profile, grouped by section, pre-set from its default."""
    from .. import profile
    proposals = profile.load_proposals(run)
    out_dir = _fresh(out_dir)
    groups = []
    for sec in profile.PROPOSAL_SECTIONS:
        props = [{"id": p["id"], "text": clean_text(p["text"], profile.LIMIT, markdown=False),
                  "default": bool(p["default"])} for p in proposals if p["section"] == sec]
        if props:
            groups.append({"name": sec, "proposals": props})
    r = rounds.start(run, stage, [it["id"] for g in groups for it in g["proposals"]], repeat_of=repeat_of)
    run.write(profile.snapshot_name(r.n), proposals)   # apply_review reads only what this page showed
    return _write(out_dir, PAGES[stage], {}, title=clean_text(title, markdown=False), groups=groups, items=[],
                  tags=[], votes=_votes(stage), doc=f"rounds/{stage}-{r.n}", repeat_of=repeat_of, n=r.n)


def render_library(conn, out_dir: Path, query: str = "", kind: str | None = None, fetch=None,
                   thumbs_dir: Path | None = None, limit: int = 200) -> Path:
    """A grid of live library items. With `fetch`, missing thumbnails are fetched first (gone links turn dead)."""
    from ..library import db, paths, search
    thumbs_dir = Path(thumbs_dir) if thumbs_dir else paths.thumbs_dir()
    rows = search.search(conn, query or None, kind=kind, limit=limit)
    if fetch is not None and rows:
        from ..lazythumbs import ensure_item_thumbs
        ensure_item_thumbs(conn, [r["id"] for r in rows], fetch, thumbs_dir)
        rows = [r for r in (db.get_item(conn, r["id"]) for r in rows) if r and not r["meta"].get("dead")]
    out_dir = _fresh(out_dir)
    files, cards = {}, []
    for r in rows:
        src = thumbs_dir / Path(r["thumb"]).name if r.get("thumb") else None
        rel = ""
        if src and src.is_file():
            rel = f"img/{src.name}"
            shutil.copy2(src, out_dir / rel)
            files[rel] = str(src.resolve())
        k = clean_text(r.get("kind", ""), 24, markdown=False)
        lic = clean_text(r.get("license", ""), 40, markdown=False)
        cards.append({"id": r["id"], "src": rel, "link": _link(r.get("page_url")), "tag": k,
                      "title": clean_text(r.get("title") or r["id"], markdown=False),
                      "sub": " · ".join(x for x in (k, lic or "licence unknown", clean_text(r.get("source", ""), 40, markdown=False)) if x)})
    heading = clean_text(query, 60, markdown=False) if query else ""
    return _write(out_dir, "library.html.j2", files, title="Design library", query=heading, kind=kind or "",
                  items=cards, tags=sorted({c["tag"] for c in cards if c["tag"]}), votes=[], doc=LIBRARY_DOC,
                  repeat_of=None, n=None)
