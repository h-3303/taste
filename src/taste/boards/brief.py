import shutil
from datetime import date
from pathlib import Path

from .run import clean_text


def write_brief(directions: dict, pool: dict, images_dir: Path, pick: str, note: str,
                dest_dir: Path, project: str, force: bool = False) -> Path:
    d = next((x for x in directions["directions"] if x["id"] == pick), None)
    if d is None:
        raise KeyError(f"no direction with id {pick!r}")
    dest_dir = Path(dest_dir)
    out = dest_dir / "direction.md"
    if out.exists() and not force:
        raise FileExistsError(out)
    if force:
        shutil.rmtree(dest_dir / "refs", ignore_errors=True)
    (dest_dir / "refs").mkdir(parents=True, exist_ok=True)
    by_id = {r["id"]: r for r in pool["images"]}
    lines = [
        f"# Design direction: {d['name']}", "",
        f"Project: {project} · chosen {date.today().isoformat()} via /taste", "",
        d["rationale"], "",
    ]
    if note:
        lines += [f"**Note:** {note}", ""]
    lines += ["## Palette", ""] + [f"- `{c}`" for c in d["palette"]] + [""]
    lines += ["## Type", "", f"- Display: {d['type']['display']}", f"- Text: {d['type']['text']}", ""]
    lines += ["## Motifs", ""] + [f"- {m}" for m in d["motifs"]] + [""]
    lines += ["## Current finish", "", "Not refined yet.", ""]
    lines += ["## References", ""]
    for iid in d["image_ids"]:
        r = by_id[iid]
        shutil.copy2(Path(images_dir) / r["file"], dest_dir / "refs" / r["file"])
        lines.append(f"- [{clean_text(r['title'])}]({r['source_url']}) · library: [[{r['source_note']}]] · `refs/{r['file']}`")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out
