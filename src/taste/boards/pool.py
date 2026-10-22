import shutil
import warnings
from pathlib import Path

import imagehash
from PIL import Image, UnidentifiedImageError

from .models import Candidate

MIN_SHORT = 400
MAX_LONG = 1600
DUP_DISTANCE = 4   # phash alone calls every flat-colour image identical, so colour is compared too


def dominant_colours(img: Image.Image, n: int = 5) -> list[str]:
    small = img.convert("RGB").resize((100, 100))
    q = small.quantize(colors=n, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()
    counts = sorted(q.getcolors(), reverse=True)
    return ["#{:02x}{:02x}{:02x}".format(*pal[i * 3:i * 3 + 3]) for _, i in counts[:n]]


def _flatten(im: Image.Image) -> Image.Image:
    im.seek(0) if getattr(im, "is_animated", False) else None
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.getchannel("A"))
        return bg
    return im.convert("RGB")


def build_pool(cands: list[Candidate], images_dir: Path) -> dict:
    images_dir = Path(images_dir)
    shutil.rmtree(images_dir, ignore_errors=True)
    images_dir.mkdir(parents=True)
    images, rejected, hashes = [], [], []
    for c in cands:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", Image.DecompressionBombWarning)   # big JPEGs load reduced below
                with Image.open(c.path) as raw:
                    if raw.format == "JPEG":
                        raw.draft("RGB", (MAX_LONG, MAX_LONG))
                    im = _flatten(raw)
        except Image.DecompressionBombError:
            rejected.append({"source": str(c.path), "reason": "too large"})
            continue
        except (UnidentifiedImageError, OSError):
            rejected.append({"source": str(c.path), "reason": "not an image"})
            continue
        w, h = im.size
        if min(w, h) < MIN_SHORT:
            rejected.append({"source": str(c.path), "reason": f"too small ({w}x{h})"})
            continue
        ph = imagehash.phash(im)
        avg = im.resize((1, 1)).getpixel((0, 0))
        dup = next((iid for iid, oph, oavg in hashes
                    if ph - oph <= DUP_DISTANCE and sum(abs(x - y) for x, y in zip(avg, oavg)) < 30), None)
        if dup:
            rejected.append({"source": str(c.path), "reason": f"duplicate of {dup}"})
            continue
        im.thumbnail((MAX_LONG, MAX_LONG))
        iid = f"i{len(images) + 1:03}"
        im.save(images_dir / f"{iid}.jpg", "JPEG", quality=85)
        hashes.append((iid, ph, avg))
        images.append({
            "id": iid, "file": f"{iid}.jpg", "kind": c.kind, "source_url": c.source_url,
            "source_note": c.source_note, "title": c.title, "style": c.style, "origin": Path(c.path).name,
            "width": im.size[0], "height": im.size[1], "colours": dominant_colours(im),
        })
    return {"images": images, "rejected": rejected}
