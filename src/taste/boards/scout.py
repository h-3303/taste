"""Scout gallery searches for a style: download candidates, number them, sheet them; keep the good ones."""
import json
import re
import shutil
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

import httpx

from .inbox import is_style
from .sheet import _sheets

COSMOS = "https://www.cosmos.so/search/elements/{q}"
DESIGNSPIRATION = "https://www.designspiration.com/search/saves/?q={q}"
# result tiles only (not avatars or logos); Cosmos serves any width, Designspiration's largest public size is 692x
_COSMOS_IMG = re.compile(r'<img[^>]*data-testid="element-image-img"[^>]*src="https://cdn\.cosmos\.so/([^"?]+)')
_DSP_IMG = re.compile(r'<img[^>]*src="https://dspncdn\.com/a1/media/\d+x/([^"]+)"[^>]*class="gridItemContent"'
                      r'|<img[^>]*class="gridItemContent"[^>]*src="https://dspncdn\.com/a1/media/\d+x/([^"]+)"')


def _unique(items):
    return list(dict.fromkeys(items))


def parse_cosmos(html: str) -> list[str]:
    return _unique(f"https://cdn.cosmos.so/{i}?format=jpeg&w=1600" for i in _COSMOS_IMG.findall(html))


def parse_designspiration(html: str) -> list[str]:
    return _unique(f"https://dspncdn.com/a1/media/692x/{a or b}" for a, b in _DSP_IMG.findall(html))


def render_page(url: str, settle_ms: int = 6000) -> str:
    """Rendered HTML of a search page (both galleries build their grids in script), through the polite fetcher:
    banned hosts refused, robots.txt obeyed, paced per host (FetchError otherwise)."""
    from taste.library import fetch as lfetch
    f = lfetch.Fetcher()
    try:
        return f.render(url, wait=settle_ms // 1000)
    finally:
        f.close()


def _download(url: str, dest: Path) -> Path:
    from .net import Http
    return Http().download(url, dest)


def _parse(render, page, parse, notes) -> list[str]:
    """A page that fails to render is a note, not a crash: the other gallery can still supply images."""
    from taste.library.fetch import FetchError
    from taste.render import RenderError
    try:
        return parse(render(page))
    except (RenderError, FetchError) as e:
        notes.append(f"render failed {page}: {e}")
        return []


def scout(run_dir: Path, style: str, cosmos: str | None, designspiration: str | None, limit: int = 30,
          render=render_page, download=_download) -> dict:
    """Search Cosmos and/or Designspiration for one style; Designspiration also covers a Cosmos page that comes back empty."""
    if not (is_style(style) or style == "survey"):
        raise ValueError(f"style must be a number (1, 2, ...) or survey, got {style!r}")
    root = Path(run_dir) / "scout"
    folder = root / style
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    notes, found = [], []
    if cosmos:
        page = COSMOS.format(q=quote(cosmos))
        urls = _parse(render, page, parse_cosmos, notes)
        if urls:
            found += [(u, page, "Cosmos") for u in urls]
        else:
            notes.append(f"Cosmos returned nothing for {cosmos!r} (it throttles repeated searches)")
    if designspiration:
        page = DESIGNSPIRATION.format(q=quote(designspiration))
        urls = _parse(render, page, parse_designspiration, notes)
        found += [(u, page, "Designspiration") for u in urls]
        if not urls:
            notes.append(f"Designspiration returned nothing for {designspiration!r}")
    items = []
    for url, page, note in found:
        if len(items) >= limit:
            break
        n = f"{len(items) + 1:02d}"
        dest = folder / f"{n}.jpg"
        try:
            download(url, dest)
        except (OSError, httpx.HTTPError) as e:
            notes.append(f"download failed {url}: {e}")
            continue
        items.append({"n": n, "file": dest.name, "image_url": url, "source": page, "note": note})
    for old in root.glob(f"sheet-{style}-*.png"):
        old.unlink()
    _sheets([{"id": i["n"], "file": i["file"]} for i in items], f"sheet-{style}", folder, root, 35)
    result = {"style": style, "items": items, "notes": notes}
    (folder / "scout.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def _query(page: str) -> str:
    u = urlparse(page)
    return parse_qs(u.query).get("q", [""])[0] or unquote(u.path.rstrip("/").rsplit("/", 1)[-1])


def _default_dlib_add(path: Path, source: str, language: str) -> None:
    """File a keeper into the design library (curated/<language slug>); MOODBOARDS_NO_DLIB disables it."""
    import os
    from .run import slugify
    if os.environ.get("MOODBOARDS_NO_DLIB"):
        return
    from taste.library import curated, db, paths
    from taste.library.fetch import FetchError, Fetcher
    slug = f"curated/{slugify(language)}"
    try:
        paths.ensure_dirs()
        conn = db.connect(paths.db_path())
        curated.new_collection(conn, slug, "image", None, [language])
        f = Fetcher()
        try:
            curated.add(conn, slug, str(path), f, paths.thumbs_dir(), "", [], source, language)
        finally:
            f.close()
    except (KeyError, ValueError, FetchError, OSError) as e:
        print(f"dlib add failed for {path.name}: {str(e)[:200]}")


def keep(run_dir: Path, style: str, numbers: list[str], inbox: Path, dlib_add=_default_dlib_add) -> list[Path]:
    """Move chosen scout images into inbox/<style>/, record their sources and file them into the design library."""
    folder = Path(run_dir) / "scout" / style
    found = json.loads((folder / "scout.json").read_text(encoding="utf-8"))
    by_n = {i["n"]: i for i in found["items"]}
    wanted = [f"{int(n):02d}" if n.isdigit() else n for n in numbers]
    missing = [n for n in wanted if n not in by_n]
    if missing:
        raise ValueError(f"no scouted image {', '.join(missing)} for style {style}")
    try:
        brief = json.loads((Path(run_dir) / "brief.json").read_text(encoding="utf-8"))
        language = next((s["name"] for s in brief.get("styles", []) if s.get("id") == style), f"style {style}")
    except (OSError, ValueError):
        language = f"style {style}"
    dest = Path(inbox) / style
    dest.mkdir(parents=True, exist_ok=True)
    stamp = Path(run_dir).name
    kept = []
    with open(dest / "sources.txt", "a", encoding="utf-8") as f:
        for n in wanted:
            item = by_n[n]
            target, k = dest / f"scout-{stamp}-{style}-{n}.jpg", 1
            while target.exists():               # a later scout reuses numbers 01..30
                k += 1
                target = dest / f"scout-{stamp}-{style}-{n}-{k}.jpg"
            shutil.move(folder / item["file"], target)
            title = f"{item['note']} · {_query(item['source'])} #{n}"
            f.write(f"{target.name}\t{item['source']}\t{item['note']}\t{title}\n")
            kept.append(target)
            if dlib_add:
                try:
                    dlib_add(target, item["source"], language)
                except Exception as e:   # never block a keep on the library
                    print(f"dlib add failed: {e}")
    return kept
