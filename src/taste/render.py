"""Page rendering behind one protocol: Playwright by default, Obscura when its connector is enabled."""
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol

from . import config


class RenderError(RuntimeError):
    """A page could not be rendered or screenshotted."""


class RendererMissing(RuntimeError):
    def __init__(self, msg: str | None = None):
        super().__init__(msg or "Chromium is missing: run `playwright install chromium` "
                                "(or `uv tool run --from taste playwright install chromium`)")


class Renderer(Protocol):
    name: str

    def html(self, url: str, wait: int = 6, stealth: bool = False) -> str: ...

    def screenshot(self, url: str, dest: Path, wait: int = 6) -> Path: ...


class PlaywrightRenderer:
    name = "playwright"
    viewport = {"width": 1440, "height": 900}

    @contextmanager
    def browser(self):
        """A launched Chromium; RendererMissing when Playwright or its browser is not installed."""
        try:
            from playwright.sync_api import Error as PwError
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            raise RendererMissing() from e
        with sync_playwright() as pw:
            try:
                browser = pw.chromium.launch()
            except PwError as e:
                raise RendererMissing() from e
            try:
                yield browser
            finally:
                browser.close()

    def html(self, url: str, wait: int = 6, stealth: bool = False, **_) -> str:
        from playwright.sync_api import Error as PwError   # TimeoutError subclasses Error
        with self.browser() as browser:
            try:
                page = browser.new_page(viewport=self.viewport)
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(wait * 1000)
                page.mouse.wheel(0, 2500)
                page.wait_for_timeout(min(wait * 1000, 2500))
                return page.content()
            except PwError as e:
                raise RenderError(f"playwright {url}: {str(e).splitlines()[0]}") from e

    def screenshot(self, url: str, dest: Path, wait: int = 6) -> Path:
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        from playwright.sync_api import Error as PwError
        with self.browser() as browser:
            try:
                page = browser.new_page(viewport=self.viewport)
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(wait * 1000)
                page.screenshot(path=str(dest))
            except PwError as e:
                raise RenderError(f"playwright {url}: {str(e).splitlines()[0]}") from e
        return dest


class ObscuraRenderer:
    name = "obscura"

    def __init__(self, bin: str, runner=subprocess.run):
        self.bin, self.runner = bin, runner

    def _run(self, args: list[str], timeout: int) -> subprocess.CompletedProcess:
        try:
            return self.runner([self.bin, *args], capture_output=True, text=True, timeout=timeout + 30)
        except subprocess.TimeoutExpired as e:
            raise RenderError(f"obscura timed out: {e}") from e

    def html(self, url: str, wait: int = 6, stealth: bool = False, obey_robots: bool = True, timeout: int = 40) -> str:
        flags = (["--stealth"] if stealth else []) + (["--obey-robots"] if obey_robots else [])
        p = self._run([*flags, "fetch", url, "--timeout", str(timeout), "--wait", str(wait), "--dump", "html",
                       "--quiet"], timeout)
        if p.returncode != 0:
            raise RenderError(f"obscura fetch {url}: {p.stderr.strip()[:300]}")
        return p.stdout

    def screenshot(self, url: str, dest: Path, wait: int = 6, stealth: bool = False, timeout: int = 40) -> Path:
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        flags = (["--stealth"] if stealth else []) + ["--obey-robots"]
        p = self._run([*flags, "fetch", url, "--timeout", str(timeout), "--wait", str(wait), "-s", str(dest),
                       "--quiet"], timeout)
        if p.returncode != 0 or not dest.exists():
            raise RenderError(f"obscura screenshot {url}: {p.stderr.strip()[:300]}")
        return dest


def get_renderer() -> Renderer:
    c = config.connector("obscura")
    if c:
        from .library.paths import obscura_bin
        b = obscura_bin()
        if b and Path(b).exists():
            return ObscuraRenderer(b)
    return PlaywrightRenderer()
