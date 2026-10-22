import hashlib
import json
import shutil
from pathlib import Path
from urllib.parse import quote_plus, urlsplit

from jinja2 import Environment, PackageLoader, select_autoescape

from .directions import style_errors
from .run import clean_text

env = Environment(loader=PackageLoader("taste.boards", "templates"), autoescape=select_autoescape(["j2", "html"]))



def _tilt(key: str) -> float:
    return (int(hashlib.md5(key.encode()).hexdigest()[:4], 16) % 70 - 35) / 10   # -3.5..3.4 deg


def _link(url: str) -> str:
    return url if urlsplit(url).scheme in ("http", "https") else ""


WEB_PX = 1000


def _web_copy(src: Path, dest: Path) -> None:
    """A copy for the canvas: long side at most WEB_PX, so big boards stay light to publish and browse."""
    from PIL import Image
    with Image.open(src) as im:
        if max(im.size) <= WEB_PX:
            shutil.copy2(src, dest)
            return
        im.thumbnail((WEB_PX, WEB_PX))
        im.convert("RGB").save(dest, "JPEG", quality=82)


def _lum(hex_: str) -> float:
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hex_[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a: str, b: str) -> float:
    """WCAG 2.x contrast ratio between two #rrggbb colours."""
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return round((la + 0.05) / (lb + 0.05), 2)


SECTION_LABELS = {"ui": "UI", "graphic": "Graphic", "texture": "Texture"}
VARIANT_LABELS = {"light": "Light", "dark": "Dark", "sunlight": "Sunlight"}


def _palettes(d: dict) -> list[dict]:
    out = []
    for variant, roles in (d.get("palettes") or {}).items():
        bg = roles.get("bg")
        ratios = {r: contrast(c, bg) for r, c in roles.items() if bg and r != "bg" and r in ("text", "muted", "accent")}
        out.append({"label": VARIANT_LABELS.get(variant, variant.title()), "roles": roles, "ratios": ratios})
    return out


def render_canvas(directions: dict, pool: dict, images_dir: Path, out_dir: Path, title: str) -> Path:
    """Render into out_dir, replacing an earlier render there (index.html, img/, files.json)."""
    errs = [e for d in directions["directions"] for e in style_errors(d)]
    if errs:
        raise ValueError("; ".join(errs))
    out_dir = Path(out_dir)
    shutil.rmtree(out_dir / "img", ignore_errors=True)
    for name in ("index.html", "files.json"):
        (out_dir / name).unlink(missing_ok=True)
    (out_dir / "img").mkdir(parents=True)
    by_id = {r["id"]: r for r in pool["images"]}
    files, fonts, boards = {}, set(), []
    for d in directions["directions"]:
        items = []
        for n, iid in enumerate(d["image_ids"]):
            rec = by_id[iid]
            rel = f"img/{rec['file']}"
            if rel not in files:
                _web_copy(Path(images_dir) / rec["file"], out_dir / rel)
                files[rel] = str((out_dir / rel).resolve())
            items.append({**rec, "src": rel, "tilt": _tilt(d["id"] + iid), "big": n in (0, 5),
                          "link": _link(rec["source_url"]),
                          "title": clean_text(rec["title"], markdown=False),
                          "source_note": clean_text(rec["source_note"], markdown=False)})
        fonts.update([d["type"]["display"], d["type"]["text"]])
        for pair in d.get("fonts") or []:
            fonts.update(f for f in (pair.get("display"), pair.get("text"), pair.get("mono")) if f)
        by_item = {it["id"]: it for it in items}
        groups, placed = [], set()
        for key, label in SECTION_LABELS.items():
            ids = [i for i in (d.get("sections") or {}).get(key, []) if i not in placed]
            if ids:
                groups.append({"label": label, "items": [by_item[i] for i in ids]})
                placed.update(ids)
        rest = [it for it in items if it["id"] not in placed]
        if groups and rest:
            groups.append({"label": "More", "items": rest})
        comps = [{**c, "link": _link(str(c.get("url", ""))),
                  "name": clean_text(c.get("name", ""), 60, markdown=False),
                  "note": clean_text(c.get("note", ""), 140, markdown=False),
                  "licence": clean_text(c.get("licence", ""), 30, markdown=False),
                  "kind": clean_text(c.get("kind", ""), 20, markdown=False)} for c in d.get("components") or []]
        boards.append({**d, "items": items, "groups": groups, "pals": _palettes(d), "comps": comps})
    font_urls = [f"https://fonts.googleapis.com/css2?family={quote_plus(f)}&display=swap" for f in sorted(fonts)]
    html = env.get_template("canvas.html.j2").render(title=title, boards=boards, font_urls=font_urls)
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    (out_dir / "files.json").write_text(json.dumps(files, indent=2), encoding="utf-8")
    return out_dir / "index.html"
