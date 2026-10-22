import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from taste.render import RendererMissing

from . import archive
from .brief import write_brief
from .canvas import render_canvas
from .directions import suggest_palette, validate
from .models import Candidate
from .inbox import is_style, take_inbox
from .pool import build_pool
from .run import Run, data_root
from .sheet import contact_sheets
from taste.connectors import enabled
from taste.connectors.folders import IMAGE_SUFFIXES
from taste.connectors.presets import InstagramMedia, ObsidianResources

MIN_POOL = 24


def cmd_new(a):
    from taste import seed
    from taste.library import db, paths
    if seed.library_is_empty(db.connect(paths.db_path())):
        print(seed.EMPTY_MESSAGE, file=sys.stderr)
        return 1
    run = Run.create(a.slug)
    lib = []
    obs = next((c for c in enabled() if isinstance(c, ObsidianResources)), None)
    if obs:
        lib = obs.load()
    run.write("library.json", lib)
    print(f"run: {run.path}\nlibrary: " + (f"{len(lib)} resource notes" if obs else "no Obsidian connector"))


def dlib_pluck(item_id: str, out: Path) -> dict | None:
    """Pluck one design-library image item into `out`; None when the item is missing or the pluck fails."""
    from taste.library import db, paths, pluck as pluck_mod
    from taste.library.fetch import FetchError, Fetcher
    try:
        paths.ensure_dirs()
        conn = db.connect(paths.db_path())
        f = Fetcher()
        try:
            r = pluck_mod.pluck(conn, item_id, f, out, {}, cache_root=paths.cache_dir())
        finally:
            f.close()
        if not r.path:
            return None
        meta = db.get_item(conn, item_id) or {}
    except (KeyError, ValueError, FetchError, OSError):
        return None
    return {"path": str(r.path), "title": meta.get("title", item_id), "page_url": meta.get("page_url", "")}


def connector_candidates(conns, dest: Path, http=None):
    """Untagged candidates from the folder connectors: local images as they are, image URLs downloaded,
    any other URL skipped (a link to a page is not an image)."""
    from taste.connectors.folders import FolderImages, FolderNotes, is_image_url
    cands, failures = [], []
    for c in conns:
        if not isinstance(c, (FolderImages, FolderNotes)):
            continue
        for n, it in enumerate(c.items()):
            if it["path"]:
                cands.append(Candidate("folder", Path(it["path"]), it["source_url"], it["note"] or c.name, it["title"]))
            elif it["url"] and is_image_url(it["url"]):
                from .net import Http
                http = http or Http()
                target = dest / "folder" / f"{c.name}-{n}{Path(it['url'].split('?')[0]).suffix.lower()}"
                try:
                    http.download(it["url"], target)
                except Exception as e:   # one dead link must not stop the gather
                    failures.append(f"{it['url']}: {e}")
                    continue
                cands.append(Candidate("folder", target, it["url"], it["note"] or c.name, it["title"]))
    return cands, failures


def cmd_gather(a):
    run = Run(a.run)
    refs = run.read("refs.json")
    styles = refs.get("styles")
    if not isinstance(styles, list):
        print('error: refs.json needs a "styles" list: [{"id", "name", "sites", "archive_queries", "vault_posts"}]')
        return 1
    cands, failures = [], []
    site_style = {s["url"]: st["id"] for st in styles for s in st.get("sites", [])}
    sites = [s for st in styles for s in st.get("sites", [])]
    if sites and not a.no_sites:
        from .capture import capture_sites   # imports Playwright only when needed
        c, f = capture_sites(sites, run.raw)   # RendererMissing is mapped to exit 2 in main
        for x in c:
            x.style = site_style.get(x.source_url)
        cands += c; failures += f
    http = None
    for st in styles:
        if st.get("archive_queries"):
            from .net import Http
            http = http or Http()
            c, f = archive.fetch(st["archive_queries"], a.per_query, run.raw, http)
            for x in c:
                x.style = x.style or st["id"]   # an item found for two styles keeps the first
            cands += c; failures += f
    conns = enabled()
    for st in styles:
        for c in conns:
            if isinstance(c, InstagramMedia):
                for it in c.for_codes(st.get("vault_posts", [])):
                    cands.append(Candidate("vault", Path(it["path"]), it["source_url"], it["note"], it["title"], st["id"]))
    c, f = connector_candidates(conns, run.raw, http)
    cands += c; failures += f
    for st in styles:
        for iid in [*st.get("dlib_ids", []), *(a.dlib or [])]:
            got = dlib_pluck(iid, run.raw / "dlib")
            if not got:
                failures.append(f"dlib {iid}: not plucked")
                continue
            cands.append(Candidate("library", Path(got["path"]), got["page_url"], f"dlib {iid}", got["title"], st["id"]))
    cands += take_inbox(data_root() / "inbox", run.raw)
    pool = build_pool(cands, run.images)
    pool["failures"] = failures
    run.write("pool.json", pool)
    kinds = Counter(r["kind"] for r in pool["images"])
    per_style = Counter(r["style"] for r in pool["images"])
    print(f"pool: {len(pool['images'])} images ({', '.join(f'{k} {n}' for k, n in sorted(kinds.items())) or 'none'})")
    for st in styles:
        print(f"style {st['id']} ({st.get('name', '')}): {per_style.get(st['id'], 0)}")
    if per_style.get(None):
        print(f"untagged (inbox root): {per_style[None]}")
    print(f"rejected: {len(pool['rejected'])}")
    for f in failures:
        print(f"failed: {f}")
    if len(pool["images"]) < MIN_POOL:
        print(f"warning: fewer than {MIN_POOL} images; widen the queries or add to the inbox")


def cmd_inbox_add(a):
    if not is_style(a.style):
        print("error: style must be a number (1, 2, ...)")
        return 1
    from urllib.parse import urlparse
    from .net import Http
    folder = data_root() / "inbox" / a.style
    folder.mkdir(parents=True, exist_ok=True)
    name = Path(urlparse(a.image_url).path).name or "image.jpg"
    if Path(name).suffix.lower() not in IMAGE_SUFFIXES:
        name += ".jpg"
    target, n = folder / name, 1
    while target.exists():
        n += 1
        target = folder / f"{Path(name).stem}-{n}{Path(name).suffix}"
    Http().download(a.image_url, target)
    with open(folder / "sources.txt", "a", encoding="utf-8") as f:
        title = a.title or f"{a.note} · {Path(urlparse(a.source).path).name or urlparse(a.source).netloc}"
        f.write(f"{target.name}\t{a.source}\t{a.note}\t{title}\n")
    print(f"added: {target}")


def cmd_scout(a):
    from . import scout
    if not (a.cosmos or a.designspiration):
        print("error: give --cosmos and/or --designspiration search terms")
        return 1
    try:
        res = scout.scout(Path(a.run), a.style, a.cosmos, a.designspiration, a.limit,
                          render=scout.render_page, download=scout._download)
    except ValueError as e:
        print(f"error: {e}")
        return 1
    print(f"{len(res['items'])} candidates for style {a.style}")
    for n in res["notes"]:
        print(f"note: {n}")
    for p in sorted((Path(a.run) / "scout").glob(f"sheet-{a.style}-*.png")):
        print(p)


def cmd_keep(a):
    from . import scout
    try:
        kept = scout.keep(Path(a.run), a.style, a.numbers, data_root() / "inbox")
    except (ValueError, FileNotFoundError) as e:
        print(f"error: {e}")
        return 1
    print(f"kept {len(kept)} into {data_root() / 'inbox' / a.style}")


def cmd_sheet(a):
    run = Run(a.run)
    for p in contact_sheets(run.read("pool.json"), run.images, run.path / "sheets"):
        print(p)


def cmd_palette(a):
    print(" ".join(suggest_palette(a.ids, Run(a.run).read("pool.json"))))


def _errors(run):
    return validate(run.read("directions.json"), run.read("pool.json"))


def cmd_validate(a):
    errs = _errors(Run(a.run))
    for e in errs:
        print(e)
    if errs:
        return 1
    print("directions ok")


def cmd_canvas(a):
    run = Run(a.run)
    errs = _errors(run)
    if errs:
        print("\n".join(errs))
        return 1
    try:
        index = render_canvas(run.read("directions.json"), run.read("pool.json"), run.images,
                              Path(a.out) if a.out else run.path / "canvas", a.title)
    except ValueError as e:
        print(f"error: {e}")
        return 1
    print(f"canvas: {index}\nfiles: {index.parent / 'files.json'}")


def cmd_brief(a):
    run = Run(a.run)
    dest = Path(a.project) / "design" if a.project else run.path
    project = Path(a.project).name if a.project else run.path.name
    try:
        p = write_brief(run.read("directions.json"), run.read("pool.json"), run.images, a.pick, a.note,
                        dest, project, force=a.force)
    except FileExistsError as e:
        print(f"exists: {e} (pass --force to overwrite)")
        return 2
    except KeyError as e:
        print(f"error: unknown pick {e}")
        return 1
    print(f"brief: {p}")


def cmd_survey_add(a):
    from . import survey
    try:
        item = survey.add(a.run, a.image, a.title, a.source, a.why, a.tag or "")
    except FileNotFoundError as e:
        print(f"error: no such image {e}")
        return 1
    print(f"{item['id']}: {item['title']} ({len(survey.load(a.run))} in survey)")


def cmd_survey_keep(a):
    from . import survey
    try:
        kept = survey.keep(a.run, a.numbers, a.why, a.tag or "")
    except (ValueError, FileNotFoundError) as e:
        print(f"error: {e}")
        return 1
    print(f"kept {', '.join(k['id'] for k in kept)} ({len(survey.load(a.run))} in survey)")


def cmd_survey_canvas(a):
    from . import survey
    try:
        index = survey.render(a.run, Path(a.out) if a.out else Path(a.run) / "survey" / "canvas", a.title)
    except ValueError as e:
        print(f"error: {e}")
        return 1
    print(f"canvas: {index}\nfiles: {index.parent / 'files.json'}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="moodboards")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("new"); p.add_argument("slug"); p.set_defaults(fn=cmd_new)
    p = sub.add_parser("gather"); p.add_argument("run"); p.add_argument("--per-query", type=int, default=6)
    p.add_argument("--no-sites", action="store_true")
    p.add_argument("--dlib", nargs="*", metavar="ID", help="design-library item ids to pluck in (applied to every style)")
    p.set_defaults(fn=cmd_gather)
    p = sub.add_parser("inbox-add", help="download an image into inbox/<style>/ with its source")
    p.add_argument("style"); p.add_argument("image_url"); p.add_argument("--source", required=True)
    p.add_argument("--note", default="inbox"); p.add_argument("--title", help="label shown in the brief and captions")
    p.set_defaults(fn=cmd_inbox_add)
    p = sub.add_parser("scout", help="search Cosmos/Designspiration for one style; numbered candidates + sheet")
    p.add_argument("run"); p.add_argument("style"); p.add_argument("--cosmos"); p.add_argument("--designspiration")
    p.add_argument("--limit", type=int, default=30); p.set_defaults(fn=cmd_scout)
    p = sub.add_parser("keep", help="move chosen scout candidates into inbox/<style>/")
    p.add_argument("run"); p.add_argument("style"); p.add_argument("numbers", nargs="+"); p.set_defaults(fn=cmd_keep)
    p = sub.add_parser("sheet"); p.add_argument("run"); p.set_defaults(fn=cmd_sheet)
    p = sub.add_parser("palette"); p.add_argument("run"); p.add_argument("ids", nargs="+"); p.set_defaults(fn=cmd_palette)
    p = sub.add_parser("validate"); p.add_argument("run"); p.set_defaults(fn=cmd_validate)
    p = sub.add_parser("canvas"); p.add_argument("run"); p.add_argument("--title", required=True)
    p.add_argument("--out", help="render into this folder (default <run>/canvas); an earlier render there is replaced")
    p.set_defaults(fn=cmd_canvas)
    p = sub.add_parser("brief"); p.add_argument("run"); p.add_argument("--pick", required=True)
    p.add_argument("--note", default=""); p.add_argument("--project"); p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_brief)
    p = sub.add_parser("survey-add", help="add one notable reference (image url or file) to the run's taste survey")
    p.add_argument("run"); p.add_argument("image"); p.add_argument("--title", required=True)
    p.add_argument("--source", required=True); p.add_argument("--why", required=True, help="why it's notable")
    p.add_argument("--tag", help="ui, web, poster, type, identity, motion, texture, ...")
    p.set_defaults(fn=cmd_survey_add)
    p = sub.add_parser("survey-keep", help="add numbered candidates from `scout <run> survey` to the survey")
    p.add_argument("run"); p.add_argument("numbers", nargs="+"); p.add_argument("--why", required=True)
    p.add_argument("--tag"); p.set_defaults(fn=cmd_survey_keep)
    p = sub.add_parser("survey-canvas", help="render the like/dislike survey canvas")
    p.add_argument("run"); p.add_argument("--title", required=True)
    p.add_argument("--out", help="render into this folder (default <run>/survey/canvas)")
    p.set_defaults(fn=cmd_survey_canvas)
    a = ap.parse_args(argv)
    try:
        return a.fn(a) or 0
    except FileNotFoundError as e:
        print(f"error: {e}")
        return 1
    except RendererMissing as e:
        print(f"error: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
