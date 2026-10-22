from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from . import cache, db
from .models import PluckResult
from .sources import base

GPL_HEADER = "GIMP Palette\nName: {name}\nColumns: 0\n#\n"


def _ext(url: str) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    return suffix if suffix and len(suffix) <= 6 else ".bin"


def _hex_rgb(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def pluck(conn, item_id: str, fetch, dest_dir: Path, opts: dict, cache_root: Path | None = None) -> PluckResult:
    item = db.get_item(conn, item_id)
    if not item:
        raise KeyError(f"no item {item_id}")
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    adapter = base.REGISTRY.get(item["source"])
    meta = item.get("meta") or {}
    if adapter is not None and base.has_pluck(adapter):
        result = adapter.pluck(item, fetch, dest_dir, opts)
    elif item["kind"] == "palette":
        colors = [c.lower() for c in meta.get("colors", [])]
        hex_path = dest_dir / f"{item_id}.hex"
        hex_path.write_text("\n".join(colors) + "\n")
        (dest_dir / f"{item_id}.gpl").write_text(GPL_HEADER.format(name=item["title"]) +
                                                 "".join("%3d %3d %3d\t%s\n" % (*_hex_rgb(c), c) for c in colors))
        result = PluckResult(item_id, hex_path, "\n".join(colors), meta.get("css", "") or item.get("page_url", ""))
    elif item["kind"] in ("snippet", "icon"):
        code = meta.get("code") or ""
        if not code:
            result = PluckResult(item_id, None, "", f"no code captured; open {item['page_url']}")
        else:
            path = dest_dir / f"{item_id}.{meta.get('language') or 'txt'}"
            path.write_text(code)
            result = PluckResult(item_id, path, code, f"{item.get('license', '')} · {meta.get('install', '')} · {item['page_url']}".strip(" ·"))
    else:
        url = item["asset_url"]
        if not url:
            result = PluckResult(item_id, None, "", f"no asset url; open {item['page_url']}")
        else:
            path = fetch.download(url, dest_dir / f"{item_id}{_ext(url)}")
            result = PluckResult(item_id, path, "", f"{item.get('license', '')} · {item['page_url']}".strip(" ·"))
    if cache_root and result.path and Path(result.path).is_relative_to(Path(cache_root)):
        cache.record(conn, result.path, item_id, datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    return result
