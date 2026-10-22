# taste plugin (phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One shareable Claude Code plugin, `taste`, that merges moodboards and dlib into a broad-to-narrow taste funnel with repeatable stages, notes on everything, combinations, an open refine loop, a two-layer taste profile, a shippable library and optional connectors.

**Architecture:** Port both working packages verbatim into one Python package as `taste.boards` (moodboards, from its `n-directions` tip) and `taste.library` (dlib, from `master`), keep all their tests green, then add new modules around them: one data root and config, a renderer abstraction, licence classification and seed snapshots, additions, stage records, stage pages, combine, refine, profile, connectors and import. The skill files orchestrate; the CLI does the mechanical work; every page writes one artifact-db doc that the CLI ingests into a JSON record.

**Tech Stack:** Python ≥3.12, uv, argparse, sqlite3 + FTS5, httpx, Pillow, imagehash, Jinja2, Playwright (Chromium), pytest. Claude Code plugin (`.claude-plugin/plugin.json`, `marketplace.json`, `skills/`). Pages are claude.ai artifacts with `db` + `user` capabilities.

**Spec:** `docs/superpowers/specs/2026-10-22-taste-plugin-design.md`

## Global Constraints

- TDD for every behaviour change: failing test, watch it fail, minimal code, pass, commit.
- One CLI, `taste` (`[project.scripts] taste = "taste.cli:main"`); install with `uv tool install`.
- Data root: env `TASTE_DATA`, default `~/.taste/`. Runs keep the moodboards layout: `runs/<date>-<slug>/`.
- Asset cache cap 2 GB; thumbnails at 1 request/s per host; a bot challenge or 429 stops the source; robots.txt obeyed.
- Banned in code, never fetched or shipped: `are.na`, `artvee.com`, `emuseum.ch`, `gurafiku.tumblr.com`, `designreviewed.com`.
- Never ship scraped gallery thumbnails or screenshots; openly licensed items ship as files, gallery items as links, MetalForge and private items never.
- Playwright/Chromium is the default renderer; Obscura is an optional connector that takes over when enabled.
- No h-specific text, paths or defaults in shipped skills, pages or code (no "h", no `moiraidigital`, no `/home/h`).
- Refine loop updates `design/direction.md`, `design/taste.md` and the Design-canvas demo only, never project code.
- The general profile is never written without the user's confirmation on a review page.
- Every round's state and the profile are plain files (markdown + JSON); the artifact db is only the live input.
- "Beauty, not theme" and "style is not subject" stay the core rules of the skill text.
- Exit codes (from dlib): 0 ok, 1 user error, 2 missing renderer or unusable data dir.
- Nothing is pushed to GitHub and no repo is created or made public inside this plan; Task 17 ends by asking h.

## Review Focus

1. **Empty library on a fresh install** (no seed installed yet): the first round must say "run `taste seed install`" and exit 1, never crash or render an empty page. Test in Task 6.
2. **Dead or blocked image links on link-only items** during lazy thumbnails: mark dead (404/410/non-image), skip transient errors, and the round still renders from the remaining items. Test in Task 7.
3. **Page state from an older render** (the person voted on a previous version): every stage's ingest refuses a doc whose `at` is earlier than the pass's `rendered_at`, as the boards pick does today. Test in Task 9.
4. **Untrusted note text** (markdown, HTML, very long, newlines) flowing into pages, `taste.md` and `profile.md`: escaped and cut with `clean_text`, never breaking the file. Tests in Tasks 13 and 14.
5. **A note silently dropped on a repeat**: every note from every earlier pass of a run appears in `steering()` output that feeds the next pass. Test in Task 9.

---

## File Structure

```
~/dev/taste/
  .claude-plugin/plugin.json          plugin manifest (Task 17)
  .claude-plugin/marketplace.json     single-plugin marketplace, source "./" (Task 17)
  skills/taste/SKILL.md               the funnel: stages 1–4, repeats, notes, combinations (Task 17)
  skills/taste-refine/SKILL.md        refine loop + profile review (Task 17)
  skills/taste-library/SKILL.md       library: search, pluck, add, seed, sync, connectors (Task 17)
  README.md                           install and first run (Task 17)
  pyproject.toml                      package "taste" (Task 1)
  src/taste/
    cli.py                            top-level argparse; delegates to groups (Task 3)
    paths.py                          one data root and its subdirs (Task 2)
    config.py                         config.json: connectors on/off + settings (Task 2)
    render.py                         Renderer protocol, Playwright default, Obscura (Task 4)
    licences.py                       classify(item) -> file | link | never (Task 5)
    seed.py                           build (maintainer) and install seed snapshots (Task 6)
    lazythumbs.py                     on-demand thumbnails for link items, dead links (Task 7)
    additions.py                      `taste add`, page requests, gaps (Task 8)
    rounds.py                         stage records, ingest, steering (Task 9)
    combine.py                        parts across directions -> new direction (Task 12)
    refine.py                         refine pass options, apply to direction.md/taste.md (Task 13)
    profile.py                        general profile + project taste.md + review (Task 14)
    importer.py                       h's existing data into taste (Task 16)
    connectors/__init__.py            registry, enabled() (Task 15)
    connectors/folders.py             FolderImages, FolderNotes (Task 15)
    connectors/presets.py             obsidian-resources, instagram-media (Task 15)
    pages/__init__.py                 render_round(), render_library() (Tasks 10–14)
    pages/templates/_base.html.j2     tokens, theme, db load/save, notes, find-more, add field (Task 10)
    pages/templates/broad.html.j2     stage 1 (Task 10)
    pages/templates/boards.html.j2    stage 2 (Task 11)
    pages/templates/directions.html.j2 stage 3 (Task 12)
    pages/templates/refine.html.j2    stage 5 (Task 13)
    pages/templates/review.html.j2    profile review (Task 14)
    pages/templates/library.html.j2   library browser + add (Task 10)
    boards/…                          ported moodboards package (Task 1)
    library/…                         ported dlib package (Task 1)
  tests/boards/…, tests/library/…     ported tests (Task 1)
  tests/test_<module>.py              new tests, one file per new module
```

---

### Task 1: Scaffold the package and port both tools

**Files:**
- Create: `pyproject.toml`, `src/taste/__init__.py`, `src/taste/py.typed`
- Create (copied): `src/taste/boards/` from `git -C ~/dev/moodboards show n-directions` (`src/moodboards/*`), `src/taste/library/` from `~/dev/design-library` `master` (`src/dlib/*`)
- Create (copied): `tests/boards/` from moodboards `tests/` (with `fixtures/`, `conftest.py`), `tests/library/` from dlib `tests/`

**Interfaces:**
- Produces: packages `taste.boards` and `taste.library` with every module and public function of moodboards and dlib unchanged except the import root. Entry points `taste.boards.cli:main` and `taste.library.cli:main` still exist (Task 3 wraps them).

- [ ] **Step 1: Export the sources** with `git archive` (moodboards at `n-directions` = 4269c45, dlib at `master`), so no uncommitted state comes along; copy into the paths above.
- [ ] **Step 2: Rewrite imports** `moodboards` → `taste.boards`, `dlib` → `taste.library` in `src/` and `tests/` (absolute and `from moodboards.` forms; relative imports stay). Leave the subprocess calls to the `dlib` binary in `boards/cli.py` and `boards/scout.py` for Task 3.
- [ ] **Step 3: Write `pyproject.toml`**: name `taste`, version `0.1.0`, `requires-python = ">=3.12"`, dependencies = union of both (`httpx>=0.28.1`, `imagehash>=4.3.2`, `jinja2>=3.1.6`, `pillow>=12.3.0`, `playwright>=1.63.0`, `pyyaml>=6.0.3`), `uv_build` backend, script `taste = "taste.cli:main"` (create `src/taste/cli.py` with `def main(argv=None) -> int: raise SystemExit("not yet")` for now), pytest markers `browser` and `network`, package data for `boards/templates/*.j2`.
- [ ] **Step 4: Run all tests**

Run: `uv sync && uv run pytest -q`
Expected: 357 passed (141 moodboards + 216 dlib), plus whatever `browser`/`network` skips the sources already had.

- [ ] **Step 5: Commit** `feat: port moodboards (n-directions) and dlib into taste.boards and taste.library`

---

### Task 2: One data root and the config file

**Files:**
- Create: `src/taste/paths.py`, `src/taste/config.py`
- Modify: `src/taste/boards/run.py` (`data_root`, delete `vault_root`), `src/taste/library/paths.py` (`data_root`, `obscura_bin`), every caller of `vault_root` (`boards/cli.py` `cmd_new`, `cmd_gather`)
- Test: `tests/test_paths.py`, `tests/test_config.py`

**Interfaces:**
- Produces: `taste.paths.data_root() -> Path` (`TASTE_DATA` or `~/.taste`), `library_dir()` (= root/`library`), `runs_dir()`, `inbox_dir()`, `profile_path()` (= root/`profile.md`), `config_path()` (= root/`config.json`).
- Produces: `taste.config.load() -> dict` (`{"connectors": {name: {"enabled": bool, ...}}}`, missing file → `{"connectors": {}}`), `save(cfg: dict) -> Path`, `connector(name: str) -> dict | None` (settings only when enabled).
- `boards.run.data_root()` returns `paths.data_root()`; `library.paths.data_root()` returns `paths.library_dir()`; `library.paths.obscura_bin()` returns `config.connector("obscura")["bin"]` or `shutil.which("obscura")` only when the connector is enabled, else `None`.

- [ ] **Step 1: Write the failing tests**

```python
def test_data_root_defaults_to_dot_taste(monkeypatch, tmp_path):
    monkeypatch.delenv("TASTE_DATA", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert paths.data_root() == tmp_path / ".taste"
    assert paths.library_dir() == tmp_path / ".taste" / "library"

def test_both_packages_share_the_root(monkeypatch, tmp_path):
    monkeypatch.setenv("TASTE_DATA", str(tmp_path))
    assert boards_run.data_root() == tmp_path
    assert library_paths.db_path() == tmp_path / "library" / "library.db"

def test_no_vault_default_left():
    assert not hasattr(boards_run, "vault_root")

def test_connector_off_by_default(monkeypatch, tmp_path):
    monkeypatch.setenv("TASTE_DATA", str(tmp_path))
    assert config.connector("obscura") is None
    assert library_paths.obscura_bin() is None

def test_connector_enabled_round_trip(monkeypatch, tmp_path):
    monkeypatch.setenv("TASTE_DATA", str(tmp_path))
    config.save({"connectors": {"obscura": {"enabled": True, "bin": "/x/obscura"}}})
    assert config.connector("obscura") == {"enabled": True, "bin": "/x/obscura"}
```

- [ ] **Step 2: Run** `uv run pytest tests/test_paths.py tests/test_config.py -q`. Expected: FAIL (module not found).
- [ ] **Step 3: Implement** the two modules and the delegations. `cmd_new` writes `library.json` from the `obsidian-resources` connector only once Task 15 exists; until then it writes `[]`. Update the ported tests that set `MOODBOARDS_DATA`/`DLIB_DATA`/`MOODBOARDS_VAULT` to set `TASTE_DATA` (vault tests move to Task 15; mark them `xfail(reason="connector, Task 15")` now).
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: all pass except the marked xfails.
- [ ] **Step 5: Commit** `feat: one TASTE_DATA root and config.json connectors`

---

### Task 3: The `taste` CLI

**Files:**
- Modify: `src/taste/cli.py`, `src/taste/boards/cli.py` (`dlib_pluck`), `src/taste/boards/scout.py` (`_default_dlib_add`)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `taste.boards.cli.main`, `taste.library.cli.main`.
- Produces: `taste.cli.main(argv: list[str] | None = None) -> int` with:
  - every moodboards command at the top level (`taste new|gather|inbox-add|scout|keep|sheet|palette|validate|canvas|brief|survey-add|survey-keep|survey-canvas …`), same arguments;
  - every dlib user command under `taste lib …` (`search|show|collections|status|sources|pluck|cache|collection|add`), same arguments, `--json` kept;
  - `taste sync [source …]`: dlib sync limited to tier-1 adapters (API/repo); a tier-2/3 slug exits 1 with `"<slug> needs a renderer: maintainer only (taste maintainer sync)"`;
  - `taste maintainer sync|install-timer` (dlib's full sync with `--full/--snapshot`, and timer);
  - `taste connect <name> [--path P] [--bin B]`, `taste disconnect <name>`, `taste connectors` (Task 2 config);
  - `taste --version` prints `taste 0.1.0`.
- `dlib_pluck` and `_default_dlib_add` call `taste.library` functions directly (no subprocess, no `shutil.which("dlib")`).

- [ ] **Step 1: Write the failing tests**: `main(["--version"])` prints `taste 0.1.0`; `main(["lib", "search", "grain", "--json"])` on an empty tmp library returns 0 and `{"match": "none", "results": []}`; `main(["sync", "cosmos"])` returns 1 with the message above; `main(["connect", "obscura", "--bin", "/x"])` then `config.connector("obscura")["bin"] == "/x"`; `boards.cli.dlib_pluck` works with `shutil.which` patched to return `None`.
- [ ] **Step 2: Run** `uv run pytest tests/test_cli.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** by building one parser that mounts the boards subcommands and a `lib` subparser that forwards `argv[1:]` to `taste.library.cli.main`; tier comes from each adapter's `SourceInfo.tier`.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: all pass.
- [ ] **Step 5: Commit** `feat: taste CLI with lib, sync, maintainer and connector commands`

---

### Task 4: Renderer: Playwright by default, Obscura when connected

**Files:**
- Create: `src/taste/render.py`
- Modify: `src/taste/library/fetch.py` (`Fetcher.render`, `Fetcher.screenshot` delegate), `src/taste/boards/scout.py` (`render_page`), `src/taste/boards/capture.py`
- Test: `tests/test_render.py`

**Interfaces:**
- Produces: `class Renderer(Protocol)`: `name: str`, `html(url: str, wait: int = 6, stealth: bool = False) -> str`, `screenshot(url: str, dest: Path, wait: int = 6) -> Path`.
- Produces: `PlaywrightRenderer()`, `ObscuraRenderer(bin: str)`, `get_renderer() -> Renderer` (Obscura when `config.connector("obscura")` is set and its `bin` exists, else Playwright), `class RendererMissing(RuntimeError)` whose message is `"Chromium is missing: run `playwright install chromium` (or `uv tool run --from taste playwright install chromium`)"`.
- `Fetcher(renderer: Renderer | None = None, …)`: robots.txt, banned hosts and the rate limiter stay in `Fetcher`; only the page rendering moves. `stealth` is passed to Obscura and ignored by Playwright.
- CLI maps `RendererMissing` to exit 2.

- [ ] **Step 1: Write the failing tests**: `get_renderer()` is `PlaywrightRenderer` with no config; is `ObscuraRenderer` after `config.save` with an existing fake bin (`tmp_path/"obscura"`, chmod +x); falls back to Playwright when the configured bin is gone; `Fetcher(renderer=fake).render("https://banned.are.na/x")` raises the existing banned error before calling `fake.html`; `Fetcher(renderer=fake).render(url)` returns `fake.html(url)`; `scout.render_page` uses `get_renderer()` (patch it).
- [ ] **Step 2: Run** `uv run pytest tests/test_render.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.** Move Obscura's subprocess code from `Fetcher._obscura` into `ObscuraRenderer`; the Playwright code from `scout.render_page`/`capture` into `PlaywrightRenderer` (one browser per call is fine).
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: all pass (ported Fetcher tests updated to pass a fake renderer).
- [ ] **Step 5: Commit** `feat: renderer abstraction, Playwright default, Obscura connector`

---

### Task 5: Licence classification

**Files:**
- Create: `src/taste/licences.py`
- Test: `tests/test_licences.py`

**Interfaces:**
- Produces: `Shipping = Literal["file", "link", "never"]`; `classify(source: str, license: str, page_url: str = "", asset_url: str = "") -> Shipping`.
- Rules, in order (from the spec's Library section):
  1. either URL on a banned host → `never`;
  2. `source` in `{"metalforge", "mine"}` (proprietary; the user's own additions are private) → `never`;
  3. `source` in `FILE_SOURCES = {"googlefonts", "fontsource", "fontshare", "collletttivo", "ambientcg", "polyhaven", "github-data", "react-bits", "magicui", "gl-transitions", "vanta", "tabler-icons", "lucide", "simple-icons", "animate-css"}` → `file`;
  4. `source == "lygia"` → `file` if `license.startswith("BSD")` else `link`;
  5. anything else with an http(s) `page_url` → `link`; otherwise `never`.

- [ ] **Step 1: Write the failing tests**: one parametrized case per rule, including `("cosmos", "see source page") → "link"`, `("curated", "curated: see origin") → "link"`, `("lospec", …) → "link"`, `("awwwards", "screenshot © site owner; reference only") → "link"`, `("lygia", "Prosperity") → "link"`, `("polyhaven", "CC0", page_url="https://www.are.na/x") → "never"`, `("unknown", "", page_url="") → "never"`.
- [ ] **Step 2: Run** `uv run pytest tests/test_licences.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** `classify`, reusing `taste.library.fetch.banned`.
- [ ] **Step 4: Run** `uv run pytest tests/test_licences.py -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: classify library items as file, link or never-ship`

---

### Task 6: Seed snapshots (build and install)

**Files:**
- Create: `src/taste/seed.py`
- Modify: `src/taste/cli.py` (`taste maintainer seed-build OUT`, `taste seed install [ARCHIVE]`), `src/taste/boards/cli.py` (`cmd_new` checks the library)
- Test: `tests/test_seed.py`

**Interfaces:**
- Consumes: `licences.classify`, `taste.library.db.connect`, `paths.library_dir()`.
- Produces: `@dataclass SeedReport(files: int, links: int, skipped: int)`; `build_seed(conn, thumbs_dir: Path, out: Path) -> SeedReport` writes `out` (a zip: `seed.db` with dlib's schema + `thumbs/` for `file` items only; `link` items keep title, tags, meta, licence, page_url, asset_url, `thumb = NULL`, `meta["shipping"] = "link"`; `never` items and any item with `meta["private"]` are absent; collections and item_collections only for shipped items).
- Produces: `install_seed(archive: Path, conn, thumbs_dir: Path) -> int` (upsert by `key`; never overwrites an existing row's `thumb` or the user's own `mine` items; returns rows added or updated). `taste seed install` with no path downloads `https://github.com/h-3303/taste/releases/latest/download/taste-seed.zip` to the data dir first.
- Produces: `library_is_empty(conn) -> bool`; `taste new` exits 1 with `"Your library is empty: run `taste seed install` first (or `taste add` your own)"` when true.

- [ ] **Step 1: Write the failing tests** with a tmp DB holding one item each from `polyhaven` (with thumb file), `cosmos` (with thumb file), `metalforge`, `mine`, and a `polyhaven` item with `meta.private = true`:

```python
def test_seed_ships_files_links_and_nothing_else(tmp_path, lib):
    rep = seed.build_seed(lib.conn, lib.thumbs, tmp_path / "s.zip")
    assert (rep.files, rep.links, rep.skipped) == (1, 1, 3)
    z = zipfile.ZipFile(tmp_path / "s.zip")
    thumbs = [n for n in z.namelist() if n.startswith("thumbs/")]
    assert thumbs == ["thumbs/" + lib.thumb_name("polyhaven")]   # no cosmos thumbnail inside
    rows = sqlite3.connect(extract(z, "seed.db")).execute("select source, thumb from items").fetchall()
    assert sorted(rows) == [("cosmos", None), ("polyhaven", lib.thumb_name("polyhaven"))]

def test_install_keeps_user_rows(tmp_path, lib, empty_lib): ...   # a "mine" row in empty_lib survives install
def test_new_refuses_empty_library(tmp_path, monkeypatch, capsys): ...   # exit 1 + the message above
```

- [ ] **Step 2: Run** `uv run pytest tests/test_seed.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.** Build by `ATTACH`ing a fresh `seed.db` created with `taste.library.db.SCHEMA` and inserting classified rows.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: all pass.
- [ ] **Step 5: Commit** `feat: seed snapshots that ship open files and gallery links only`

---

### Task 7: Lazy thumbnails and dead links

**Files:**
- Create: `src/taste/lazythumbs.py`
- Modify: `src/taste/library/search.py` (exclude `json_extract(meta,'$.dead') = 1`), `src/taste/library/sheet.py` (call `ensure_item_thumbs` for rows without a thumb before drawing)
- Test: `tests/test_lazythumbs.py`

**Interfaces:**
- Consumes: `taste.library.sync.make_item_thumb`, `taste.library.fetch.Fetcher`.
- Produces: `ensure_item_thumbs(conn, ids: list[str], fetch, thumbs_dir: Path) -> dict[str, Path | None]`: fetches only rows with `thumb IS NULL`; HTTP 404/410 or a non-image body sets `meta.dead = true` and returns `None`; timeouts, 5xx, 429 and challenges return `None` and leave the row alone (and 429/challenge stop the rest of that host, as dlib does).

- [ ] **Step 1: Write the failing tests** with dlib's fake fetcher (`tests/library/conftest.py` style): three link rows → one 200 image, one 404, one timeout. Assert the first gets a thumb path on disk, the second is `meta.dead` and missing from `search("…")`, the third has `thumb` NULL and is not dead; a sheet over the three draws two tiles plus no crash.
- [ ] **Step 2: Run** `uv run pytest tests/test_lazythumbs.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: all pass.
- [ ] **Step 5: Commit** `feat: fetch link-item thumbnails on first use, hide dead links`

---

### Task 8: Additions and thin-round prompts

**Files:**
- Create: `src/taste/additions.py`
- Modify: `src/taste/cli.py` (`taste add`, `taste gaps`)
- Test: `tests/test_additions.py`

**Interfaces:**
- Consumes: `get_renderer()` (page URLs), `Fetcher.download`, `taste.library.thumbs.make_thumb`, `taste.library.db` upsert functions.
- Produces: `add(conn, target: str, *, kind: str | None = None, tags: list[str] = [], language: str | None = None, fetch=None, renderer=None) -> list[str]` (new item ids). `target` is a file, a folder (each image inside, non-recursive), an image URL (downloaded) or a page URL (screenshotted). Items get `source = "mine"`, collection `mine/additions` (created on first use), the original under `library_dir()/mine/`. Kind inferred: `.jpg .jpeg .png .webp .gif .avif` → `image`, `.ttf .otf .woff .woff2` → `font`; anything else without `--kind` raises `ValueError("can't tell what <name> is: pass --kind")` (CLI exit 1). Banned hosts raise the banned error (exit 1).
- Produces: `gaps(run: Run) -> list[str]`: one plain sentence per gap, from the latest broad/boards round: a kind among `image, texture, font, palette` with zero likes → `"Nothing liked in <kind>s yet: add some, or ask for more"`; a direction with fewer than 8 images in `pool.json` → `"Direction <id> is thin (<n> images)"`.

- [ ] **Step 1: Write the failing tests**: a file add and a folder add (two images + one `.txt` ignored) produce `mine` items with thumbs; `classify("mine", …) == "never"` so `build_seed` skips them (reuse Task 6 fixture); an `.xyz` file raises with the message; `add(conn, "https://www.are.na/block/1")` raises banned; `gaps` on a fixture run with likes only for images lists the texture/font/palette sentences.
- [ ] **Step 2: Run** `uv run pytest tests/test_additions.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: all pass.
- [ ] **Step 5: Commit** `feat: taste add (files, folders, links) and taste gaps`

---

### Task 9: Stage records, page ingest and steering

**Files:**
- Create: `src/taste/rounds.py`
- Modify: `src/taste/cli.py` (`taste round ingest <run> <stage> <n> <doc.json>`, `taste round steer <run>`)
- Test: `tests/test_rounds.py`

**Interfaces:**
- Produces: `STAGES = ("broad", "boards", "directions", "final", "refine", "review")`.
- Produces: `@dataclass ItemState(vote: str | None, note: str = "")` (votes: `like|dislike` for broad, `keep|drop` for boards and directions, `pick` for refine and review, `None` = no vote).
- Produces: `@dataclass Round(stage: str, n: int, repeat_of: int | None, shown: list[str], items: dict[str, ItemState], combos: list[dict], prompts: list[str], requests: list[dict], note: str, rendered_at: str, at: str | None)`.
- Produces: `next_n(run, stage) -> int` (1-based), `start(run, stage, shown, repeat_of=None) -> Round` (writes `rounds/<stage>-<n>.json` with `rendered_at` now, UTC ISO 8601), `load(run, stage, n) -> Round`, `all_rounds(run, stage: str | None = None) -> list[Round]`.
- Produces: `class StalePage(ValueError)`; `ingest(run, stage, n, doc: dict) -> Round`. The page doc (written by every stage page to db path `rounds/<stage>-<n>`) is `{"items": {id: {"vote": str|None, "note": str}}, "combos": [{"name": str, "parts": {part: direction_id}, "note": str}], "prompts": [str], "requests": [{"type": "more-like", "id": str} | {"type": "add-url", "url": str}], "note": str, "at": iso}`. Unknown item ids are dropped; notes pass through `clean_text(limit=600, markdown=False)`; `doc.at < rendered_at` raises `StalePage("These votes were made on an older version of the page: ask to vote again")` (CLI exit 1).
- Produces: `record_final(run, comments: list[dict]) -> Round`: the final stage lives on a Design canvas, so its notes arrive as that artifact's comments (read with ArtifactComments, saved to a file by the skill); each `{"text": str, "anchor": str}` becomes item `pin-<k>` with its note, stored as the next `final` pass (`rendered_at` = the demo's publish time from `published.json`'s `demo_at`). CLI: `taste round final <run> <comments.json>`.
- Produces: `steering(run) -> dict` = `{"likes": [id], "dislikes": [id], "kept": [id], "dropped": [id], "notes": [{"stage", "n", "id" | None, "text"}], "combos": [...], "prompts": [...], "requests": [...]}` across every pass, later votes on the same id winning, every non-empty note kept.

- [ ] **Step 1: Write the failing tests**

```python
def test_repeat_links_and_numbers(run):
    a = rounds.start(run, "broad", ["s001", "s002"])
    b = rounds.start(run, "broad", ["s003"], repeat_of=a.n)
    assert (a.n, b.n, b.repeat_of) == (1, 2, 1)

def test_stale_doc_refused(run):
    r = rounds.start(run, "broad", ["s001"])
    with pytest.raises(rounds.StalePage):
        rounds.ingest(run, "broad", r.n, {"items": {}, "at": "2000-01-01T00:00:00Z"})

def test_no_note_dropped_across_repeats(run):
    r1 = rounds.start(run, "broad", ["s001", "s002"])
    rounds.ingest(run, "broad", 1, doc({"s001": ("like", "warmer"), "s002": (None, "why this?")}, note="more print"))
    rounds.start(run, "broad", ["s003"], repeat_of=1)
    rounds.ingest(run, "broad", 2, doc({"s003": ("dislike", "")}, note=""))
    texts = [n["text"] for n in rounds.steering(run)["notes"]]
    assert texts == ["warmer", "why this?", "more print"]

def test_unknown_ids_dropped_and_notes_cleaned(run): ...  # id not in shown is ignored; "a\n<b>" stays one line, cut at 600

def test_final_comments_become_notes(run):
    rounds.record_final(run, [{"text": "logo smaller", "anchor": "header"}])
    assert rounds.steering(run)["notes"][-1]["text"] == "logo smaller"
```

- [ ] **Step 2: Run** `uv run pytest tests/test_rounds.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest tests/test_rounds.py -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: stage records with repeats, stale-page check and steering`

---

### Task 10: Shared page frame, broad stage and library pages

**Files:**
- Create: `src/taste/pages/__init__.py`, `pages/templates/_base.html.j2`, `broad.html.j2`, `library.html.j2`
- Modify: `src/taste/cli.py` (`taste round render <run> <stage> --title T --out DIR [--repeat-of N]`, `taste library-page --out DIR [--query Q] [--kind K]`)
- Test: `tests/test_pages.py`

**Interfaces:**
- Consumes: `rounds.start`, `taste.boards.survey` (survey `items.json`), `taste.library.search`, `lazythumbs.ensure_item_thumbs`.
- Produces: `render_round(run, stage: str, title: str, out_dir: Path, repeat_of: int | None = None) -> Path` (returns `out_dir/index.html`; writes `out_dir/files.json` mapping published path → source path, as `boards.canvas` does; calls `rounds.start` so the record's `shown` matches the page).
- Produces: `render_library(conn, out_dir: Path, query: str = "", kind: str | None = None) -> Path`.
- `_base.html.j2` provides: colour tokens on `:root` with dark mode (`prefers-color-scheme` guarded by `:root:not([data-theme="light"])`, and `:root[data-theme="dark"]`), explicit `body` background, phone-width layout with 16 px gutters; the db binding (`window.claude.use("db")` → doc `rounds/<stage>-<n>`, load on open, save on every change with `at`); per-item vote buttons from a `votes` list, a note field on every item, a "find more like this" button (pushes `{"type": "more-like", "id"}`), a page-level note, an add-link field (pushes `{"type": "add-url", "url"}`), a "repeat of pass N" line when `repeat_of`, and a "Saved." status. Works with no `window.claude` (read-only, no errors).
- `broad.html.j2` is the survey page ported onto the frame (votes `like|dislike`).
- `library.html.j2`: a grid of library items (thumb, title, kind, licence, source link) with the add-link field; votes none, notes on.

- [ ] **Step 1: Write the failing tests**: rendering broad for a fixture run with 3 survey items yields `index.html` containing each item id, `data-votes="like dislike"`, three note fields plus the page note, the db doc path `rounds/broad-1`, and `files.json` keys `img/<file>` for each image; a second render with `repeat_of=1` targets `rounds/broad-2` and shows "repeat of pass 1"; every `{{ }}` field is autoescaped (an item title `<script>x</script>` appears escaped); `render_library` lists only non-dead items.
- [ ] **Step 2: Run** `uv run pytest tests/test_pages.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** with a Jinja `Environment(autoescape=True)` and `PackageLoader("taste.pages")`. Load the `artifact-design` skill before writing the templates.
- [ ] **Step 4: Run** `uv run pytest tests/test_pages.py -q`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: shared stage page frame, broad stage and library pages`

---

### Task 11: Boards stage with per-image notes

**Files:**
- Create: `src/taste/pages/templates/boards.html.j2`
- Modify: `src/taste/pages/__init__.py` (stage `boards`), `src/taste/boards/canvas.py` (expose its board/section/palette/font data builder for reuse)
- Test: `tests/test_pages.py`

**Interfaces:**
- Consumes: `directions.json` and `pool.json` as `boards.canvas.render_canvas` reads them today (any number of directions, sections, palette variants, font pairings, components from n-directions).
- Produces: `render_round(run, "boards", …)`: item ids are `d<direction id>` for each board and `<direction id>/<image id>` for each image on it; votes `keep|drop`; a note on every board and every image; the old one-pick button is gone (picking happens in stage 3).

- [ ] **Step 1: Write the failing tests**: for the n-directions canvas fixture with 3 directions, the page has 3 board items and one item per image, each with a note field; ingesting a doc with `"1/i004": {"vote": "drop", "note": "too glossy"}` lands in `steering()["dropped"]` and its note in `notes`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement**, keeping the ported canvas's look and big-slot layout.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: all pass (ported canvas tests untouched; `taste canvas` still works as before).
- [ ] **Step 5: Commit** `feat: boards stage with keep/drop and notes per board and image`

---

### Task 12: Directions stage with combinations

**Files:**
- Create: `src/taste/combine.py`, `src/taste/pages/templates/directions.html.j2`
- Modify: `src/taste/pages/__init__.py` (stage `directions`), `src/taste/boards/directions.py` (`validate` accepts mixes), `src/taste/cli.py` (`taste combine <run> --from-round N`)
- Test: `tests/test_combine.py`, `tests/test_pages.py`

**Interfaces:**
- Produces: `PARTS = ("palette", "type", "texture", "components", "imagery")`.
- Produces: `combine(directions: list[dict], parts: dict[str, str], name: str, note: str = "") -> dict`: a new direction with id `m<k>` (next free), `name`, `from: parts`, `note`, and each part copied from its source direction (`palette` → `palette` + palette variants; `type` → `type` + pairings; `texture` → images in the texture section; `components` → components; `imagery` → the rest of `image_ids`). Unknown part or direction id raises `ValueError`.
- Produces: `apply_combos(run, rnd: Round) -> list[dict]`: appends one direction per `rnd.combos` entry to `directions.json` and returns them; `validate(directions: dict, pool: dict) -> list[str]` (existing signature) returns `[]` for the result.
- Page: one column per direction, each split into the five parts with keep/drop + note per part (`<direction id>:<part>` ids) and a whole-direction keep; a "combine" control lets the person pick one source direction per part and name the mix (writes `combos`).

- [ ] **Step 1: Write the failing tests**

```python
def test_combine_takes_each_part_from_its_source(dirs):
    m = combine.combine(dirs, {"palette": "1", "type": "2", "texture": "2", "components": "1", "imagery": "1"}, "Plate + grid")
    assert m["id"] == "m1" and m["palette"] == dirs[0]["palette"] and m["type"] == dirs[1]["type"]
    assert m["from"]["type"] == "2"

def test_combine_rejects_unknown_direction(dirs):
    with pytest.raises(ValueError):
        combine.combine(dirs, {"palette": "9"}, "x")

def test_mix_passes_validate(run_with_dirs):
    rnd = ingest_with_combo(run_with_dirs)
    combine.apply_combos(run_with_dirs, rnd)
    assert validate(run_with_dirs.read("directions.json"), run_with_dirs.read("pool.json")) == []
```

- [ ] **Step 2: Run** `uv run pytest tests/test_combine.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** `combine`, `apply_combos`, the validate change and the page.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: all pass.
- [ ] **Step 5: Commit** `feat: directions stage with per-part notes and combinations`

---

### Task 13: Refine passes

**Files:**
- Create: `src/taste/refine.py`, `src/taste/pages/templates/refine.html.j2`
- Modify: `src/taste/pages/__init__.py` (stage `refine`), `src/taste/boards/brief.py` (a "Current finish" section that refine can rewrite), `src/taste/cli.py` (`taste refine check <run> <n>`, `taste refine apply <run> <n> [--project DIR]`)
- Test: `tests/test_refine.py`

**Interfaces:**
- Produces: `LAYERS = {"ui": ("ground", "cards", "depth", "ui", "type", "accent"), "graphic": ("ground", "type", "accent", "imagery", "texture")}`.
- Input written by the agent per pass: `<run>/refine/<n>-options.json` = `{"kind": "ui" | "graphic", "layers": {layer: [{"id": str, "label": str, "still": "<path under run>", "detail": str}]}}`; a layer may be left out; each listed layer has 2–6 options.
- Produces: `check_options(doc: dict) -> list[str]` (error strings, empty when valid: unknown layer, fewer than 2 or more than 6 options, duplicate ids, missing still file).
- Page: one row per layer, options as stills, one `pick` per layer (`<layer>:<option id>` ids), a note per option and per layer, a free prompt box (writes `prompts`), the page note.
- Produces: `apply_pass(run, n: int, project_dir: Path | None) -> Path`: appends `## Refine pass <n> (<date>)` to `<project>/design/taste.md` (run folder when no project) with one line per layer (`- <layer>: <label>` + note), the prompts and the page note, all through `clean_text(limit=600)`; rewrites the "Current finish" section of `design/direction.md` with the picked labels and details. Never touches other files.

- [ ] **Step 1: Write the failing tests**: `check_options` errors for 1 option, 7 options, duplicate ids, a missing still, layer `"floor"`; `apply_pass` on an ingested pass writes the section, leaves the rest of `direction.md` byte-identical, and a note `"## hijack\n[x](y)"` stays inside one escaped list line; two passes give two sections in order.
- [ ] **Step 2: Run** `uv run pytest tests/test_refine.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: all pass.
- [ ] **Step 5: Commit** `feat: refine passes that update direction.md and taste.md`

---

### Task 14: Taste profile, project file and review

**Files:**
- Create: `src/taste/profile.py`, `src/taste/pages/templates/review.html.j2`
- Modify: `src/taste/pages/__init__.py` (stage `review`), `src/taste/cli.py` (`taste profile show`, `taste profile project <run> --project DIR`, `taste profile apply <run> <n>`)
- Test: `tests/test_profile.py`

**Interfaces:**
- Produces: `SECTIONS = ("Liked traits", "Disliked traits", "Rules", "References", "Projects")`; `read_profile(path: Path) -> dict[str, list[str]]` (missing file → every section empty; unknown `## ` headings kept under their own key so hand edits survive); `write_profile(path: Path, data: dict[str, list[str]]) -> Path` (markdown: `# Taste profile`, one `## <section>` per key, one `- ` line per entry, `SECTIONS` order first).
- Produces: `write_project_taste(run, project_dir: Path | None) -> Path`: writes the head of `design/taste.md` (chosen direction or mix with its `from` parts, survey traits from `taste.json`, every note from `rounds.steering`), preserving existing `## Refine pass` sections.
- Input written by the agent: `<run>/proposals.json` = `[{"id": "p1", "section": one of SECTIONS[:4], "text": str, "default": bool}]`; the review page shows each with a tick (`pick` vote) pre-set from `default`, plus notes.
- Produces: `apply_review(run, n: int, profile_path: Path) -> dict` adds ticked proposals (deduped by case- and space-insensitive text, via `clean_text(limit=300)`) and always adds `"<date> <project or run slug>: <direction name>"` to `Projects`; unticked proposals are not written anywhere in the profile.

- [ ] **Step 1: Write the failing tests**: read/write round trip including a hand-added `## Fonts I own` section; `apply_review` with p1 ticked and p2 unticked writes p1 only, plus the Projects line; applying twice adds nothing new; a proposal text with a newline and `[link](x)` ends up on one escaped line; `write_project_taste` keeps an existing `## Refine pass 1` section.
- [ ] **Step 2: Run** `uv run pytest tests/test_profile.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: all pass.
- [ ] **Step 5: Commit** `feat: two-layer taste profile with a confirm-first review`

---

### Task 15: Connectors

**Files:**
- Create: `src/taste/connectors/__init__.py`, `connectors/folders.py`, `connectors/presets.py`
- Modify: `src/taste/boards/cli.py` (`cmd_new` library.json, `cmd_gather` vault media), remove `src/taste/boards/library.py` and `vaultmedia.py` after moving their logic into the presets (their ported tests move to `tests/test_connectors.py` and lose the Task 2 xfail)
- Test: `tests/test_connectors.py`

**Interfaces:**
- Produces: `class Connector(Protocol)`: `name: str`, `items() -> list[dict]` with dicts `{"path": str | None, "url": str | None, "title": str, "source_url": str, "note": str}`.
- Produces: `FolderImages(path: Path)` (images in the folder, recursive), `FolderNotes(path: Path)` (markdown files; each `![[…]]`/`![](…)` image embed and each http(s) URL becomes an item; title from the note's first heading or filename).
- Produces presets: `ObsidianResources(path: Path)` (the ported `load_library` behaviour: resource notes with `url`, `category`, `url_status`, returning the same dicts `library.json` holds today) and `InstagramMedia(path: Path)` (the ported `vault_media` behaviour over `<path>/<creator>/<code>_N.jpg`).
- Produces: `REGISTRY = {"folder-images": FolderImages, "folder-notes": FolderNotes, "obsidian-resources": ObsidianResources, "instagram-media": InstagramMedia}` (Obscura is handled by Task 4); `enabled() -> list[Connector]` from `config.load()`, each built with its configured `path`; a configured path that doesn't exist is skipped with a warning, not an error.
- `cmd_new` writes `library.json` from `ObsidianResources` when enabled, else `[]`; gather adds `InstagramMedia`, `FolderImages` and `FolderNotes` items only when enabled.

- [ ] **Step 1: Write the failing tests**: `enabled()` is `[]` with no config; after `taste connect folder-images --path <tmp>` it returns one connector listing the tmp images; `FolderNotes` over a note with one embed and two links gives three items; the ported vault-library and vault-media tests pass against the presets with a tmp vault; a missing path is skipped.
- [ ] **Step 2: Run** `uv run pytest tests/test_connectors.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** and remove the two old modules.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: all pass, no xfails left.
- [ ] **Step 5: Commit** `feat: optional connectors (folders, Obsidian resources, Instagram media)`

---

### Task 16: Import h's existing data

**Files:**
- Create: `src/taste/importer.py`
- Modify: `src/taste/cli.py` (`taste import [--dlib DIR] [--moodboards DIR] [--project DIR …]`)
- Test: `tests/test_importer.py`

**Interfaces:**
- Produces: `import_library(src_dir: Path, conn, thumbs_dir: Path) -> int`: copies every item, collection and thumbnail from a dlib data dir (`library.db`, `thumbs/`), upserting by `key`; rows whose `classify(...) == "never"` get `meta.private = true` (so `build_seed` never exports them); returns rows imported.
- Produces: `import_runs(src_dir: Path, dest: Path) -> int`: copies each `runs/<name>/` not already present (never overwrites).
- Produces: `import_profile(runs_dir: Path, profile_path: Path) -> dict`: writes nothing; returns proposals (`Liked traits`/`Disliked traits` from every `taste.json`, deduped) for the agent to show on a review page (Task 14), because the profile is confirm-first.
- Produces: `import_project(project_dir: Path) -> Path | None`: when `design/direction.md` exists and `design/taste.md` does not, writes a `design/taste.md` that points to it; otherwise does nothing.

- [ ] **Step 1: Write the failing tests**: a tmp dlib dir with a `cosmos`, a `metalforge` and a `curated` row imports all three, marks only `metalforge` private, and a following `build_seed` exports `cosmos` and `curated` as links and not `metalforge`; re-import changes nothing; `import_runs` skips an existing run; `import_profile` returns proposals and leaves `profile.md` absent; `import_project` leaves an existing `taste.md` alone.
- [ ] **Step 2: Run** `uv run pytest tests/test_importer.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: all pass.
- [ ] **Step 5: Commit** `feat: taste import for an existing dlib library, runs and projects`

---

### Task 17: Skills, plugin manifest, README and the shipping checks

**Files:**
- Create: `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `skills/taste/SKILL.md`, `skills/taste-refine/SKILL.md`, `skills/taste-library/SKILL.md`, `README.md`, `LICENSE` (leave the licence choice to h: write `LICENSE` only after asking; until then README says "licence: to be decided")
- Test: `tests/test_shipping.py`

**Interfaces:**
- `plugin.json`: `name "taste"`, `version "0.1.0"`, `description`, `author {"name": "h-3303"}`, `repository "https://github.com/h-3303/taste"`, `keywords`.
- `marketplace.json`: `$schema` as in Claude's marketplaces, `name "taste"`, `owner {"name": "h-3303"}`, one plugin `{"name": "taste", "source": "./", "category": "design"}`.
- `skills/taste/SKILL.md`: rewrite of the moodboards skill for any user: checks `taste --version` (else gives the README's install line); library check (`taste seed install` when empty); the funnel stages 1–4 with `taste round render/ingest`, repeats on request, steering from `taste round steer`, agent search (scout + `taste lib search` + Mobbin when available) on each repeat, `taste gaps` prompts, combinations via `taste combine`, final demo on a Design canvas as moodboards step 10; publishing each page with the Artifact tool (`root`, `files` from `files.json`, `capabilities {"db": {}, "user": {}}`), reading state with ArtifactData into a file then `taste round ingest`. Keeps the "Beauty, not theme" and "Style is not subject" sections and the banned-site rule verbatim except for the person's name.
- `skills/taste-refine/SKILL.md`: refine passes (write options + stills, `taste refine check`, render, publish, ingest, `taste refine apply`), never editing project code; the end-of-project review (`proposals.json`, review page, `taste profile apply`); reading `taste profile show` before any design work.
- `skills/taste-library/SKILL.md`: the dlib skill rewritten for `taste lib …`, plus `taste add`, `taste seed install`, `taste sync` (tier 1 only), connectors.
- README: what it is (one paragraph), install (`/plugin marketplace add h-3303/taste`, `/plugin install taste@taste`, `uv tool install git+https://github.com/h-3303/taste`, `playwright install chromium`, `taste seed install`), first run (`/taste <project>`), connectors, data dir, the shipping rule.

- [ ] **Step 1: Write the failing tests**

```python
SHIPPED = ["skills", "src/taste/pages", "README.md", ".claude-plugin"]
FORBIDDEN = [r"moiraidigital", r"/home/h\b", r"Documents/", r"\bh's\b", r"\bh (says|picks|wants|marks|likes|decides)\b"]

def test_no_personal_text_in_shipped_files():
    for path in shipped_text_files(SHIPPED):
        for pat in FORBIDDEN:
            assert not re.search(pat, path.read_text()), f"{pat} in {path}"

def test_manifests_parse_and_agree():
    plugin = json.loads(Path(".claude-plugin/plugin.json").read_text())
    market = json.loads(Path(".claude-plugin/marketplace.json").read_text())
    assert plugin["name"] == market["plugins"][0]["name"] == "taste"

def test_every_skill_has_frontmatter_name_and_description(): ...

def test_seed_from_a_mixed_library_ships_no_gallery_thumbnails(mixed_lib, tmp_path):
    # one row per source in the spec's Library section
    seed.build_seed(mixed_lib.conn, mixed_lib.thumbs, tmp_path / "s.zip")
    shipped = {source_of(n) for n in thumbs_in(tmp_path / "s.zip")}
    assert shipped <= licences.FILE_SOURCES | {"lygia"}
```

- [ ] **Step 2: Run** `uv run pytest tests/test_shipping.py -q`. Expected: FAIL.
- [ ] **Step 3: Write** the manifests, the three skills and the README.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: all pass.
- [ ] **Step 5: Commit** `feat: taste plugin manifest, skills and README`
- [ ] **Step 6: Stop and ask h** (outward-facing): which licence for the code, whether to create the public GitHub repo `h-3303/taste` now, push, and publish the first seed snapshot as a release (built with `taste maintainer seed-build` from h's imported library). Nothing is pushed before the answer.
