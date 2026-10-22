import re
from collections import Counter
from itertools import combinations

HEX = re.compile(r"#[0-9a-fA-F]{6}")
FONT = re.compile(r"[A-Za-z0-9 ]+")   # values go into CSS font-family and a Google Fonts URL
AXES = ("palette", "density", "type", "imagery")
MIN_IMAGES, MAX_IMAGES = 8, 60


def style_errors(d: dict) -> list[str]:
    """Palette and font values the canvas writes into CSS; shared by validate and render_canvas."""
    errs, tag = [], f"direction {d.get('id')}"
    pal = d.get("palette", [])
    if len(pal) != 5 or not all(HEX.fullmatch(str(c)) for c in pal):
        errs.append(f"{tag}: palette must be 5 #rrggbb colours")
    t = d.get("type", {})
    fonts = [str(t.get("display", "")).strip(), str(t.get("text", "")).strip()]
    if not all(fonts):
        errs.append(f"{tag}: type needs display and text fonts")
    for f in (t.get("display"), t.get("text")):
        if f and not FONT.fullmatch(str(f)):
            errs.append(f"{tag}: bad font name {f!r} (letters, digits and spaces only)")
    return errs + _extras_errors(d, tag)


SECTIONS = ("ui", "graphic", "texture")


def _extras_errors(d: dict, tag: str) -> list[str]:
    """Optional big-board fields: palette variants, font pairings and image sections."""
    errs = []
    for variant, roles in (d.get("palettes") or {}).items():
        if not isinstance(roles, dict) or not all(HEX.fullmatch(str(c)) for c in roles.values()):
            errs.append(f"{tag}: palettes.{variant} must map roles to #rrggbb colours")
    for pair in d.get("fonts") or []:
        for role in ("display", "text", "mono"):
            f = pair.get(role)
            if f and not FONT.fullmatch(str(f)):
                errs.append(f"{tag}: bad font name {f!r} in fonts (letters, digits and spaces only)")
    imgs = set(d.get("image_ids", []))
    for name, ids in (d.get("sections") or {}).items():
        if name not in SECTIONS:
            errs.append(f"{tag}: section {name} is not one of {', '.join(SECTIONS)}")
        elif any(i not in imgs for i in ids):
            errs.append(f"{tag}: section {name} lists images that are not in image_ids")
    return errs


def validate(directions: dict, pool: dict) -> list[str]:
    errs = []
    ds = directions.get("directions", [])
    known = {r["id"] for r in pool["images"]}
    style_of = {r["id"]: r.get("style") for r in pool["images"]}
    if not ds:
        errs.append("need at least 1 direction")
    if [d.get("id") for d in ds] != [str(n) for n in range(1, len(ds) + 1)]:
        errs.append(f'ids must be "1" to "{len(ds)}" in order')
    usage = Counter()
    for d in ds:
        tag = f"direction {d.get('id')}"
        if not str(d.get("name", "")).strip():
            errs.append(f"{tag}: name is empty")
        r = str(d.get("rationale", "")).strip()
        if not r or r.count("\n") > 1 or len(r) > 240:
            errs.append(f"{tag}: rationale must be 1-2 lines, at most 240 chars")
        imgs = d.get("image_ids", [])
        if not MIN_IMAGES <= len(set(imgs)) <= MAX_IMAGES:
            errs.append(f"{tag}: needs {MIN_IMAGES}-{MAX_IMAGES} images, got {len(set(imgs))}")
        for i in imgs:
            if i not in known:
                errs.append(f"{tag}: unknown image {i}")
        usage.update(set(imgs))
        own = sum(style_of.get(i) == d.get("id") for i in set(imgs))
        if imgs and own * 2 <= len(set(imgs)):
            errs.append(f"{tag}: only {own} of {len(set(imgs))} images were gathered for style {d.get('id')} (need more than half)")
        errs += style_errors(d)
        if not 3 <= len(d.get("motifs", [])) <= 5:
            errs.append(f"{tag}: needs 3-5 motifs")
        if set(d.get("axes", {})) != set(AXES):
            errs.append(f"{tag}: axes must have {', '.join(AXES)}")
    for img, n in sorted(usage.items()):
        if n > 2:
            errs.append(f"image {img} used in {n} directions (max 2)")
    for a, b in combinations(ds, 2):
        xa, xb = a.get("axes", {}), b.get("axes", {})
        diff = sum(str(xa.get(k, "")).lower() != str(xb.get(k, "")).lower() for k in AXES)
        if diff < 2:
            errs.append(f"directions {a.get('id')} and {b.get('id')} differ on {diff} axes (need 2)")
    return errs


def suggest_palette(image_ids: list[str], pool: dict, n: int = 5) -> list[str]:
    by_id = {r["id"]: r for r in pool["images"]}
    counts = Counter()
    for i in image_ids:
        for rank, c in enumerate(by_id.get(i, {}).get("colours", [])):
            counts[c] += 5 - rank
    return [c for c, _ in counts.most_common(n)]
