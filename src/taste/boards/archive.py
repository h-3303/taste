from pathlib import Path
from urllib.parse import quote

import httpx

from .models import Candidate

SEARCH = "https://archive.org/advancedsearch.php"
META = "https://archive.org/metadata/{}"
MAX_BYTES = 15_000_000


def pick_image(identifier: str, files: list[dict]) -> str | None:
    jpegs = [f for f in files if f.get("format") == "JPEG" and int(f.get("size") or 0) <= MAX_BYTES]
    if not jpegs:
        return None
    best = max(jpegs, key=lambda f: int(f.get("size") or 0))
    return f"https://archive.org/download/{identifier}/{quote(best['name'])}"


def fetch(queries: list[str], per_query: int, dest: Path, http) -> tuple[list[Candidate], list[str]]:
    cands, failures, seen = [], [], set()
    for q in queries:
        try:
            docs = http.get_json(SEARCH, {
                "q": f"({q}) AND mediatype:image", "fl[]": ["identifier", "title"],
                "rows": per_query, "output": "json",
            })["response"]["docs"]
        except (httpx.HTTPError, KeyError, ValueError) as e:
            failures.append(f"Internet Archive search '{q}': {e}")
            continue
        for doc in docs:
            ident = doc["identifier"]
            if ident in seen:
                continue
            seen.add(ident)
            path = Path(dest) / f"archive-{ident}.jpg"
            try:
                if not path.exists():   # an earlier gather already downloaded it
                    meta = http.get_json(META.format(ident))
                    url = pick_image(ident, meta.get("files", []))
                    if not url:
                        failures.append(f"Internet Archive {ident}: no usable JPEG")
                        continue
                    path = http.download(url, path)
            except (httpx.HTTPError, KeyError, ValueError) as e:
                failures.append(f"Internet Archive {ident}: {e}")
                continue
            cands.append(Candidate("archive", path, f"https://archive.org/details/{ident}",
                                   "Internet Archive", str(doc.get("title") or ident)))
    return cands, failures
