"""Taste survey: ~100 notable design references h marks like/dislike before any language is proposed."""
import json
import shutil
from pathlib import Path
from urllib.parse import urlsplit

from .canvas import _link, env
from .run import clean_text
from taste.connectors.folders import IMAGE_SUFFIXES


def _dir(run_dir) -> Path:
    return Path(run_dir) / "survey"


def load(run_dir) -> list[dict]:
    f = _dir(run_dir) / "items.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else []


def _default_download(url: str, dest: Path) -> Path:
    from .net import Http
    Http().download(url, dest)
    return dest


def add(run_dir, image: str, title: str, source: str, why: str, tag: str = "",
        download=_default_download, key: str | None = None) -> dict:
    """Copy or download one image into <run>/survey/img and record it.

    An image already in the survey (same `key`, by default the image url or resolved path) is returned as is;
    several images may share one source page (a gallery front page).
    """
    items = load(run_dir)
    remote = urlsplit(image).scheme in ("http", "https")
    key = key or (image if remote else str(Path(image).resolve()))
    for it in items:
        if it.get("key") == key:
            return it
    if not remote and not Path(image).is_file():
        raise FileNotFoundError(image)
    sid = f"s{len(items) + 1:03d}"
    suffix = Path(urlsplit(image).path if remote else image).suffix.lower()
    dest = _dir(run_dir) / "img" / f"{sid}{suffix if suffix in IMAGE_SUFFIXES else '.jpg'}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if remote:
        download(image, dest)
    else:
        shutil.copy2(image, dest)
    item = {"id": sid, "file": dest.name, "title": title, "source_url": source, "why": why, "tag": tag, "key": key}
    items.append(item)
    (_dir(run_dir) / "items.json").write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
    return item


def render(run_dir, out_dir, title: str) -> Path:
    """Render the survey canvas into out_dir (index.html, img/, files.json), replacing an earlier render."""
    items = load(run_dir)
    if not items:
        raise ValueError("the survey is empty: add items with survey-add first")
    out_dir = Path(out_dir)
    shutil.rmtree(out_dir / "img", ignore_errors=True)
    for name in ("index.html", "files.json"):
        (out_dir / name).unlink(missing_ok=True)
    (out_dir / "img").mkdir(parents=True)
    files, cards = {}, []
    for it in items:
        rel = f"img/{it['file']}"
        src = _dir(run_dir) / "img" / it["file"]
        shutil.copy2(src, out_dir / rel)
        files[rel] = str(src.resolve())
        cards.append({**it, "src": rel, "link": _link(it["source_url"]),
                      "title": clean_text(it["title"], markdown=False),
                      "why": clean_text(it["why"], 160, markdown=False),
                      "tag": clean_text(it.get("tag", ""), 24, markdown=False)})
    tags = sorted({c["tag"] for c in cards if c["tag"]})
    html = env.get_template("survey.html.j2").render(title=title, items=cards, tags=tags)
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    (out_dir / "files.json").write_text(json.dumps(files, indent=2), encoding="utf-8")
    return out_dir / "index.html"


def keep(run_dir, numbers: list[str], why: str, tag: str = "") -> list[dict]:
    """Add numbered candidates from `scout <run> survey` to the survey; the image url is their source (the search page is shared)."""
    scouted = json.loads((Path(run_dir) / "scout" / "survey" / "scout.json").read_text(encoding="utf-8"))
    by_n = {i["n"]: i for i in scouted["items"]}
    wanted = [f"{int(n):02d}" for n in numbers]
    missing = [n for n in wanted if n not in by_n]
    if missing:
        raise ValueError(f"no scouted survey image {', '.join(missing)}")
    folder = Path(run_dir) / "scout" / "survey"
    return [add(run_dir, str(folder / by_n[n]["file"]), title=f"{by_n[n]['note']} · {n}",
                source=by_n[n]["image_url"], why=why, tag=tag, key=by_n[n]["image_url"]) for n in wanted]
