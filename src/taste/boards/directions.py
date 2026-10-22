import re
from collections import Counter
from itertools import combinations

HEX = re.compile(r"#[0-9a-fA-F]{6}")
FONT = re.compile(r"[A-Za-z0-9 ]+")   # values go into CSS font-family and a Google Fonts URL
AXES = ("palette", "density", "type", "imagery")
MIN_IMAGES, MAX_IMAGES = 8, 60
PARTS = ("palette", "type", "texture", "components", "imagery")   # what a mix ("m<k>") takes from its sources
MIX_ID = re.compile(r"m([1-9]\d*)")


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


def _roots(ds: list[dict]) -> dict:
    """For each mix, the plain directions it descends from (its images were gathered for those styles)."""
    by_id, out = {d.get("id"): d for d in ds}, {}

    def walk(i, seen):
        d = by_id.get(i)
        if d is None or i in seen or not isinstance(d.get("from"), dict):
            return {i}
        return set().union(*(walk(v, seen | {i}) for v in d["from"].values())) if d["from"] else {i}
    for d in ds:
        if isinstance(d.get("from"), dict):
            out[d.get("id")] = walk(d.get("id"), set())
    return out


def _mix_errors(ds: list[dict]) -> list[str]:
    errs, earlier = [], {}
    for d in ds:
        i, tag = d.get("id"), f"direction {d.get('id')}"
        is_mix = isinstance(i, str) and bool(MIX_ID.fullmatch(i))
        frm = d.get("from")
        if not is_mix:
            if "from" in d:
                errs.append(f"{tag}: only a mix (m1, m2, ...) has a from field")
        elif not isinstance(frm, dict) or set(frm) != set(PARTS):
            errs.append(f"{tag}: from must name a source direction for each of {', '.join(PARTS)}")
        elif any(str(v) not in earlier for v in frm.values()):
            errs.append(f"{tag}: from names a direction that is not listed before it")
        else:
            pool = set().union(*(earlier[str(v)].get("image_ids", []) for v in frm.values()))
            stray = [x for x in d.get("image_ids", []) if x not in pool]
            if stray:
                errs.append(f"{tag}: images {', '.join(stray[:5])} are not in its source directions")
        earlier[str(i)] = d
    return errs


def validate(directions: dict, pool: dict) -> list[str]:
    errs = []
    ds = directions.get("directions", [])
    known = {r["id"] for r in pool["images"]}
    style_of = {r["id"]: r.get("style") for r in pool["images"]}
    if not ds:
        errs.append("need at least 1 direction")
    mixes = [d for d in ds if isinstance(d.get("id"), str) and MIX_ID.fullmatch(d["id"])]
    n, k = len(ds) - len(mixes), len(mixes)
    if [d.get("id") for d in ds] != [str(i) for i in range(1, n + 1)] + [f"m{i}" for i in range(1, k + 1)]:
        errs.append(f'ids must be "1" to "{n}" in order' + (f', then "m1" to "m{k}"' if k else ""))
    errs += _mix_errors(ds)
    roots = _roots(ds)
    usage = Counter()
    for d in ds:
        tag = f"direction {d.get('id')}"
        mix = d in mixes
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
        if not mix:
            usage.update(set(imgs))       # a mix reuses its sources' images by design
        styles = roots.get(d.get("id"), {d.get("id")})
        own = sum(style_of.get(i) in styles for i in set(imgs))
        if imgs and own * 2 <= len(set(imgs)):
            errs.append(f"{tag}: only {own} of {len(set(imgs))} images were gathered for style "
                        f"{', '.join(sorted(map(str, styles)))} (need more than half)")
        errs += style_errors(d)
        if not 3 <= len(d.get("motifs", [])) <= 5:
            errs.append(f"{tag}: needs 3-5 motifs")
        if set(d.get("axes", {})) != set(AXES):
            errs.append(f"{tag}: axes must have {', '.join(AXES)}")
    for img, n in sorted(usage.items()):
        if n > 2:
            errs.append(f"image {img} used in {n} directions (max 2)")
    for a, b in combinations([d for d in ds if d not in mixes], 2):   # a mix is meant to sit close to its sources
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
