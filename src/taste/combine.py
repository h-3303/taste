"""Mixes: a new direction built from parts of existing ones (stage 3 combos)."""
from .boards.directions import MAX_IMAGES, MIN_IMAGES, MIX_ID, PARTS
from .boards.run import Run, clean_text

_AXIS_OF = {"palette": "palette", "type": "type", "imagery": "imagery", "density": "components"}


def _textures(d: dict) -> list[str]:
    return [i for i in (d.get("sections") or {}).get("texture", []) if i in d.get("image_ids", [])]


def combine(directions: list[dict], parts: dict[str, str], name: str, note: str = "") -> dict:
    """A new direction `m<k>` taking each of the five parts from the direction named for it in `parts`."""
    by_id = {str(d["id"]): d for d in directions}
    unknown = set(parts) - set(PARTS)
    if unknown:
        raise ValueError(f"unknown part(s) {', '.join(sorted(unknown))} (parts are {', '.join(PARTS)})")
    missing = [p for p in PARTS if p not in parts]
    if missing:
        raise ValueError(f"a mix needs a source for every part; missing {', '.join(missing)}")
    for p, src in parts.items():
        if str(src) not in by_id:
            raise ValueError(f"part {p}: no direction {src}")
    name = clean_text(name, 60, markdown=False)
    if not name:
        raise ValueError("a mix needs a name")
    src = {p: by_id[str(parts[p])] for p in PARTS}
    k = max((int(m.group(1)) for d in directions if (m := MIX_ID.fullmatch(str(d["id"])))), default=0) + 1

    texture = _textures(src["texture"])
    img = src["imagery"]
    imagery = [i for i in img["image_ids"] if i not in set(_textures(img))]
    ids = list(dict.fromkeys(texture + imagery))
    for i in img["image_ids"]:            # top up from the imagery source when the split leaves too few
        if len(ids) >= MIN_IMAGES:
            break
        if i not in ids:
            ids.append(i)
    ids = ids[:MAX_IMAGES]
    sections = {"texture": [i for i in texture if i in ids]}
    for key, vals in (img.get("sections") or {}).items():
        if key != "texture":
            sections[key] = [i for i in vals if i in ids and i not in sections["texture"]]
    sections = {key: v for key, v in sections.items() if v}

    motifs = list(dict.fromkeys(m for p in ("imagery", "palette", "type", "texture", "components")
                                for m in src[p].get("motifs", [])))[:5]
    pal, typ = src["palette"], src["type"]
    mix = {"id": f"m{k}", "name": name,
           "rationale": clean_text("Mix: " + ", ".join(f"{p} from {parts[p]}" for p in PARTS) + ".", 240, markdown=False),
           "from": {p: str(parts[p]) for p in PARTS}, "note": clean_text(note, 600, markdown=False),
           "image_ids": ids, "palette": list(pal["palette"]), "type": dict(typ["type"]),
           "motifs": motifs, "axes": {a: src[p].get("axes", {}).get(a, "") for a, p in _AXIS_OF.items()}}
    if pal.get("palettes"):
        mix["palettes"] = pal["palettes"]
    if typ.get("fonts"):
        mix["fonts"] = typ["fonts"]
    if src["components"].get("components"):
        mix["components"] = src["components"]["components"]
    if sections:
        mix["sections"] = sections
    return mix


def apply_combos(run, rnd) -> list[dict]:
    """Append one mix per combo in the round to directions.json (all or nothing) and return the new mixes."""
    run = run if isinstance(run, Run) else Run(run)
    data = run.read("directions.json")
    ds, new = list(data.get("directions", [])), []
    for c in rnd.combos:
        m = combine(ds, c.get("parts") or {}, c.get("name", ""), c.get("note", ""))
        ds.append(m)
        new.append(m)
    if new:
        run.write("directions.json", {**data, "directions": ds})
    return new
