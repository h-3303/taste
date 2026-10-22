import re
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import Error as PwError
from playwright.sync_api import TimeoutError as PwTimeout

from taste.render import PlaywrightRenderer

from .models import Candidate
from .run import slugify

# These galleries forbid automated access; h brings their images in by hand through the inbox.
DENY = ("are.na", "artvee.com", "emuseum.ch", "gurafiku.tumblr.com", "designreviewed.com")
ACCEPT = re.compile(r"^\s*(accept( all)?|agree|i agree|allow all|got it|ok)\s*$", re.I)


def _dismiss_banners(page) -> None:
    try:
        page.get_by_role("button", name=ACCEPT).first.click(timeout=1500)
    except (PwTimeout, PwError):
        pass


def allowed(url: str) -> str | None:
    """None if capture may visit the URL, else the reason it is skipped."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        return "not an http(s) URL"
    host = (parts.hostname or "").lower()
    if any(host == d or host.endswith("." + d) for d in DENY):
        return "site forbids automated access"
    return None


def _shot(s: dict, path: Path) -> Candidate:
    return Candidate("site", path, s["url"], s["note"], s.get("title") or s["note"])


def capture_sites(sites: list[dict], dest: Path, idle_timeout_ms: int = 8000,
                  site_timeout_ms: int = 30000) -> tuple[list[Candidate], list[str]]:
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    cands, failures, visit = [], [], []
    for s in sites:
        stem = f"site-{slugify(s['note'])}"
        old = [dest / f"{stem}-{i}.png" for i in (1, 2)]
        if reason := allowed(s["url"]):
            failures.append(f"skipped {s['note']}: {reason}")
        elif all(p.exists() for p in old):
            cands.extend(_shot(s, p) for p in old)   # captured by an earlier gather
        else:
            visit.append(s)
    if not visit:
        return cands, failures
    with PlaywrightRenderer().browser() as browser:
        for s in visit:
            ctx = browser.new_context(viewport={"width": 1440, "height": 900})
            page = ctx.new_page()
            page.set_default_timeout(site_timeout_ms)
            stem = f"site-{slugify(s['note'])}"
            try:
                page.goto(s["url"], wait_until="domcontentloaded", timeout=site_timeout_ms)
                try:
                    page.wait_for_load_state("networkidle", timeout=idle_timeout_ms)
                except PwTimeout:
                    pass
                page.wait_for_timeout(2000)
                _dismiss_banners(page)
                shots = []
                for i, y in ((1, 0), (2, 900)):
                    page.evaluate(f"window.scrollTo(0, {y})")
                    page.wait_for_timeout(500)
                    out = dest / f"{stem}-{i}.png"
                    page.screenshot(path=str(out))
                    shots.append(_shot(s, out))
                cands.extend(shots)
            except (PwTimeout, PwError) as e:
                failures.append(f"site {s['note']} ({s['url']}): {str(e).splitlines()[0]}")
            finally:
                ctx.close()
    return cands, failures
