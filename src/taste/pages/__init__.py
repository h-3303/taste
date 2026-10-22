"""Stage pages: one shared frame (db binding, votes, notes, requests) and the pages built on it."""
import json
import shutil
from pathlib import Path
from urllib.parse import urlsplit

from jinja2 import Environment, PackageLoader

from .. import rounds
from ..boards.run import Run, clean_text

env = Environment(loader=PackageLoader("taste.pages"), autoescape=True)

PAGES = {"broad": "broad.html.j2"}
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
