import warnings
from pathlib import Path

import imagehash
from PIL import Image, ImageDraw, ImageFont

THUMB = 400
MAX_LONG = 1600


def _flatten(im: Image.Image) -> Image.Image:
    if getattr(im, "is_animated", False):
        im.seek(0)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.getchannel("A"))
        return bg
    return im.convert("RGB")


def make_thumb(src: Path, dest: Path) -> tuple[Path, str]:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", Image.DecompressionBombWarning)
        with Image.open(src) as raw:
            if raw.format == "JPEG":
                raw.draft("RGB", (MAX_LONG, MAX_LONG))
            im = _flatten(raw)
    im.thumbnail((THUMB, THUMB))
    im.save(dest, "JPEG", quality=80)
    return dest, str(imagehash.phash(im))


def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def swatch(colors: list[str], dest: Path) -> Path:
    im = Image.new("RGB", (THUMB, 120), (255, 255, 255))
    draw = ImageDraw.Draw(im)
    n = max(len(colors), 1)
    w = THUMB / n
    for i, c in enumerate(colors):
        draw.rectangle((int(i * w), 0, int((i + 1) * w), 120), fill=_hex(c))
    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    im.save(dest, "JPEG", quality=85)
    return Path(dest)


def _font(path, size):
    try:
        return ImageFont.truetype(str(path), size) if path else ImageFont.load_default(size)
    except OSError:
        return ImageFont.load_default(size)


def specimen(font_path, family: str, dest: Path) -> Path:
    im = Image.new("RGB", (THUMB, 220), (250, 250, 248))
    draw = ImageDraw.Draw(im)
    draw.text((16, 14), "Aa Bb Qq 123", font=_font(font_path, 72), fill=(20, 20, 20))
    draw.text((16, 120), "The quick brown fox", font=_font(font_path, 34), fill=(20, 20, 20))
    draw.text((16, 186), family[:40], font=ImageFont.load_default(16), fill=(120, 120, 120))
    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    im.save(dest, "JPEG", quality=85)
    return Path(dest)


def placeholder(size=(300, 300), label: str = "") -> Image.Image:
    im = Image.new("RGB", size, (60, 60, 60))
    if label:
        ImageDraw.Draw(im).text((8, size[1] // 2 - 8), label[:28], fill=(200, 200, 200))
    return im


def svg_to_png(svg_text: str, dest: Path) -> Path | None:
    """Rasterise an SVG with cairosvg when installed; otherwise return None (caller draws a labelled tile)."""
    try:
        import cairosvg   # optional, not a declared dependency
    except (ImportError, OSError):   # OSError: package present but libcairo missing
        return None
    try:
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        cairosvg.svg2png(bytestring=svg_text.encode(), write_to=str(dest), output_width=THUMB,
                         output_height=THUMB, background_color="white")
    except Exception:   # a bad icon must never abort a sync
        return None
    return Path(dest)
