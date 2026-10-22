from pathlib import Path

from PIL import Image, ImageDraw

COLS, CELL = 5, 300


def contact_sheets(pool: dict, images_dir: Path, out_dir: Path, per_sheet: int = 20) -> list[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("sheet-*.png"):
        old.unlink()
    groups: dict[str, list[dict]] = {}
    for rec in pool["images"]:
        groups.setdefault(rec.get("style") or "x", []).append(rec)   # "x": not gathered for a style
    paths = []
    for style in sorted(groups):
        paths += _sheets(groups[style], f"sheet-{style}", images_dir, out_dir, per_sheet)
    return paths


def _sheets(recs: list[dict], stem: str, images_dir: Path, out_dir: Path, per_sheet: int) -> list[Path]:
    paths = []
    for n, start in enumerate(range(0, len(recs), per_sheet), 1):
        chunk = recs[start:start + per_sheet]
        rows = -(-len(chunk) // COLS)
        sheet = Image.new("RGB", (COLS * CELL, rows * CELL), (24, 24, 24))
        draw = ImageDraw.Draw(sheet)
        for k, rec in enumerate(chunk):
            with Image.open(Path(images_dir) / rec["file"]) as im:
                im = im.convert("RGB")
                im.thumbnail((CELL - 8, CELL - 8))
            x, y = (k % COLS) * CELL, (k // COLS) * CELL
            sheet.paste(im, (x + (CELL - im.width) // 2, y + (CELL - im.height) // 2))
            draw.rectangle((x, y, x + 52, y + 22), fill=(0, 0, 0))
            draw.text((x + 6, y + 5), rec["id"], fill=(255, 255, 255))
        p = out_dir / f"{stem}-{n}.png"
        sheet.save(p)
        paths.append(p)
    return paths
