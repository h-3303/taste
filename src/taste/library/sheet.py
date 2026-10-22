from pathlib import Path

from PIL import Image, ImageDraw

from . import db
from .thumbs import placeholder


def contact_sheets(items: list[dict], thumbs_root: Path, out_dir: Path, stem: str = "sheet", per_sheet: int = 35,
                   cols: int = 5, cell: int = 300, conn=None, fetch=None, thumbs_dir: Path | None = None) -> list[Path]:
    if conn is not None and fetch is not None and thumbs_dir is not None:
        from ..lazythumbs import ensure_item_thumbs   # link rows get their thumbnail on first use; dead ones drop out
        ensure_item_thumbs(conn, [r["id"] for r in items if not r.get("thumb")], fetch, thumbs_dir)
        items = [fresh for r in items if (fresh := db.get_item(conn, r["id"])) and not fresh["meta"].get("dead")]
    items = [r for r in items if not (r.get("meta") or {}).get("dead")]
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob(f"{stem}-*.png"):
        old.unlink()
    paths = []
    for n, start in enumerate(range(0, len(items), per_sheet), 1):
        chunk = items[start:start + per_sheet]
        rows = -(-len(chunk) // cols)
        sheet = Image.new("RGB", (cols * cell, rows * cell), (24, 24, 24))
        draw = ImageDraw.Draw(sheet)
        for k, rec in enumerate(chunk):
            x, y = (k % cols) * cell, (k // cols) * cell
            im = None
            if rec.get("thumb"):
                try:
                    with Image.open(Path(thumbs_root) / rec["thumb"]) as raw:
                        im = raw.convert("RGB")
                        im.thumbnail((cell - 8, cell - 8))
                except OSError:
                    im = None
            if im is None:
                im = placeholder((cell - 8, cell - 8), rec.get("title", ""))
            sheet.paste(im, (x + (cell - im.width) // 2, y + (cell - im.height) // 2))
            draw.rectangle((x, y, x + 64, y + 22), fill=(0, 0, 0))
            draw.text((x + 6, y + 5), rec["id"], fill=(255, 255, 255))
        p = out_dir / f"{stem}-{n}.png"
        sheet.save(p)
        paths.append(p)
    return paths
