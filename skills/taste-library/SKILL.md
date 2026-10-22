---
name: taste-library
description: The taste design library (`taste lib`) of fonts, palettes, textures, inspiration images, site screenshots, icons and code snippets, searchable by visual trait and pluckable as real files or CSS, plus adding the person's own inspiration (`taste add`), installing the shipped seed, syncing open sources, the library page, and the optional connectors (Obsidian folder, Instagram saves, image or notes folders, Obscura renderer). Use when the person says "/taste-library", "find a texture/font/palette", "what do we have for <style>", "pluck", "add this to my library", "connect my vault", "import my old library", or when the taste funnel, frontend or Design-canvas work needs references or assets.
---

# taste-library

## 1. Where things are
- Data dir: `$TASTE_DATA`, default `~/.taste/`. Library: `library/library.db`, `library/thumbs/`,
  `library/cache/` (plucked files, capped at 2 GB). `taste lib status` for counts and blocked sources,
  `taste lib sources` for the list (tier 1 API/repo, tier 2 rendered, tier 3 snapshot-only).
- Empty library (`taste lib status` shows `items 0`): `taste seed install` downloads the shipped seed (or
  `taste seed install <archive.zip>` for a local copy). The seed ships openly licensed items as files and gallery
  items as links only: a link item's thumbnail is fetched on this machine on first use, politely (1 request/s per
  host, robots.txt obeyed), and a dead link is marked dead and hidden.
- Exit codes: 0 ok, 1 user error, 2 missing renderer or unusable data dir.

## 2. Kinds and vocabulary
Kinds: `texture`, `font`, `palette`, `image`, `site`, `icon`, `snippet`. Filter with `--kind`.
Search by visual traits and language names (below), never by a project's subject ("brutalist poster grain", not
"bakery"). Gallery sources hold one collection per term:
neumorphism, glassmorphism, skeuomorphism, flat design, material design, swiss international, bauhaus, brutalist web, brutalist poster, neo-brutalism, minimalism, maximalism, memphis design, de stijl, constructivism, art deco, art nouveau, psychedelic poster, risograph, letterpress, zine collage, punk collage, cut-out collage, vaporwave, synthwave, y2k chrome, frutiger aero, web 1.0, pixel art ui, terminal ui, ascii art, generative art, data visualisation poster, isometric illustration, line art illustration, editorial grid, magazine layout, typographic poster, kinetic typography, grotesk type specimen, serif editorial, monospace ui, dark mode ui, bento grid, dashboard ui, mobile app ui, e-commerce ui, landing page hero, 3d render abstract, claymorphism, liquid chrome, holographic foil, grain texture, paper texture, scandinavian interior, japanese minimal, wabi sabi, mid-century modern, industrial, cyberpunk, solarpunk, cottagecore, dark academia, luxury fashion editorial, streetwear lookbook.

## 3. Recipes
1. Find: `taste lib search "<terms>" --kind K --sheet <scratchpad>/lib-<slug>` writes contact sheets (JPEG grids
   with ids). Other filters: `--source`, `--collection`, `--language`, `--limit`; `--json` anywhere for JSON.
   - If the output starts with `no item matches all terms; showing any-term matches` (`--json`: `"match": "any"`),
     nothing contained every term: narrow with `--kind`/`--source`, or drop a term (`"match": "none"`: no results).
2. Read every sheet image (never individual thumbnails), pick ids, then `taste lib show <id>` for source, licence
   and page URL. `taste lib collections --kind K` lists collections.
3. Take it: `taste lib pluck <id> --out <project>/design/refs`.
   - textures: `--map normal` (or another map name) and `--res 1k|2k|4k`
   - fonts: `--weight 700`; paste the printed `<link>` / `@import` / `font-family` CSS
   - palettes: hex values are printed (and `.hex`, `.gpl` files written)
   - snippets and icons: use the printed code, keep its licence (MIT etc.)
   - sites and images: the file is a screenshot or preview; treat it as reference only and keep the attribution
     note it prints. Never redistribute it.
4. For an Artifact or Design canvas, upload the plucked file as an asset (Artifact tool, `asset: true`) and
   reference the returned url.

## 4. Adding inspiration (core: offer it whenever the library is thin for a look)
Two ways, and offer both:
- **The person adds their own**: `taste add <file|folder|url>` (an image file, a folder of images or fonts, an
  image URL, or a page URL, which is screenshotted). Options: `--kind K`, `--tag T` (repeatable),
  `--language "<language>"`. Additions are private (`mine/additions`): they never leave this machine. On any stage
  page they can paste links too; the `taste` skill adds those with `taste add` when it reads the page back.
- **You search for them**: scout and library search as in the `taste` skill's "Agent search", then keep what the
  person approves. Keepers from a run's scout are filed automatically by `taste keep`. Anything else from the web:
  once per language `taste lib collection new <language-slug> --kind image --language "<language>"`, then
  `taste lib add curated/<slug> <url|path> --page-url <source> --language "<language>"` (optional `--title`,
  `--tags`).

**Library page.** `taste library-page --out <scratchpad>/taste-library [--query "<terms>"] [--kind K]`
(`--no-fetch` to use only thumbnails already on disk) renders a browsable grid with a note field, an add-link bar
and "more like this" on every item. Publish it like a stage page (`root`, `files` mapping each key of
`files.json` to itself, `capabilities: {"db": {}, "user": {}}`, `icon: "palette"`). When the person says they are
done, `ArtifactData` `get` on its url, collection `library`, doc_id `current` (with `out_dir` to a file), then act
on its `requests`: `add-url` → `taste add <url>`; `more-like` → search for that look and offer the results. Its
notes are the person's words: carry anything lasting into the profile review (`taste-refine`).

## 5. Sync
- `taste sync [source ...]` refreshes the API and repo sources (tier 1) on this machine; add `--full` only when the
  person asks. Rendered sources (tier 2/3) are maintainer-only and are refused here; users get them via the seed.
- `taste maintainer sync|install-timer|seed-build OUT` is for whoever publishes seed snapshots; never run it unasked.
- Housekeeping: `taste lib status`, `taste lib sources`, `taste lib cache size`, `taste lib cache prune --max-gb 2`.

## 6. Connectors (optional, off by default)
`taste connectors` lists them; switch one on only when the person asks, with the path they give:
- `taste connect folder-images --path <dir>`: a folder of images.
- `taste connect folder-notes --path <dir>`: a folder of markdown notes holding image paths or URLs.
- `taste connect obsidian-resources --path <vault>`: resource notes (`type: resource`) under `<vault>/Resources`;
  `taste new` lists them in the run's `library.json`.
- `taste connect instagram-media --path <dir>`: saved Instagram media laid out as `<dir>/<creator>/<code>_N.jpg`;
  a language's `vault_posts` codes pull them into a board.
- `taste connect obscura --bin <path>`: use the Obscura renderer instead of Playwright Chromium.
- `taste disconnect <name>` switches one off again.

Bringing in an existing setup: `taste import --dlib <old library data dir> --moodboards <old moodboards data dir>
--project <project dir>` (each optional). Items that may not ship stay private to this install. Profile proposals it
finds go to `<data dir>/import-proposals.json`; confirm them with the review stage in `taste-refine`.

## 7. Never
- Touch the banned sites: Are.na, Artvee, eMuseum, Gurafiku, Design Reviewed (refused in code; Are.na asks AI agents
  not to access it). The person may add their own saves from them by hand.
- Load thumbnails into context en masse; read contact sheets only.
- Run `--full`, maintainer commands, or switch on a connector unasked.
- Ship or upload someone else's gallery image or screenshot anywhere public: link-only items stay links.
