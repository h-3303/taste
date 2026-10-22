---
name: taste
description: Find out what the person likes before designing anything. Runs a broad-to-narrow funnel for one project (about 100 notable references marked like/dislike, then collage boards of design languages grown from the likes, then a few full directions whose parts can be mixed, then the chosen direction on the project's real main screen on a claude.ai Design canvas), every stage repeatable and steered by all votes and notes so far, and writes the result into the project as design/direction.md and design/taste.md. Use when the person says "/taste", "design directions", "design language options", "moodboards for <project>", "style directions", "give me some directions to pick from", "what's my taste", or starts the visual design of a project.
---

# taste: the funnel

Gather what the person likes, then narrow it to one design direction for one project:
**broad** (single images) → **boards** (design languages as collages) → **directions** (full directions in parts,
mixable) → **final** (the real main screen on a Design canvas). Refining after that, and the end-of-project
profile review, are the `taste-refine` skill. Finding and adding inspiration is the `taste-library` skill.

Everything is plain files in the data dir (`$TASTE_DATA`, default `~/.taste/`): runs at `runs/<date>-<slug>/`,
one record per stage pass at `<run>/rounds/<stage>-<n>.json`. The pages are claude.ai artifacts; their database is
only the live input, `taste round ingest` turns it into the record.

**Beauty, not theme.** An app is not a theme park. The point of a design language is to look beautiful; it is never chosen because it echoes what the project is about. A travel app does not get a map, survey, ticket or passport look; a camera app does not get a film or darkroom look; a roofing app does not get a blueprint look. Before proposing a language, test it: would it be an equally strong pick for an unrelated product? If its main argument is the subject, drop it. The project only contributes practical constraints (legibility outdoors, density, platform, one-handed use) and whatever the person's taste survey (stage 1) shows they like.

**Style is not subject.** The same rule for images: a board shows what a design language looks like (its UI, type, texture, colour, layout and graphic treatments), whatever the pictures depict. Never search for or pick images by what the project is about (a drawing app's boards are not pictures of drawings).

Never scrape Are.na, Artvee, eMuseum, Gurafiku or Design Reviewed: they block automated access (gather skips them too, and anything that isn't http(s)). Only the inbox brings their images in.

Rules that hold at every stage:
- **Never force the person forward.** Every stage can be repeated as often as they like, and they may skip ahead
  at any time. Nothing they noted is ever dropped: notes live in the round records and reach `design/taste.md`.
- **Stop and wait** after giving a page link until the person says they are done. Do not poll.
- **Read the profile first**: `taste profile show` before proposing anything; its liked/disliked traits and rules
  steer every stage (a rule such as "no brown" is binding).

## 0. Setup (every session)

1. `taste --version`. If the command is missing, give the person the install lines and stop:
   `uv tool install git+https://github.com/h-3303/taste`, then `playwright install chromium` (if `playwright`
   is not on PATH: `~/.local/share/uv/tools/taste/bin/playwright install chromium`).
2. `taste lib status`. If it shows `items 0`, run `taste seed install` (downloads the shipped seed library). If
   that fails offline, the person can still start with their own: `taste add <file|folder|url>`.
3. `taste connectors` lists the optional sources (Obsidian folder, Instagram saves, image or notes folders,
   Obscura renderer). They are off by default; never switch one on unasked (see `taste-library`).

## Publishing a page (same for every stage)

Every stage page is rendered by the CLI into a folder and published with the Artifact tool:

- `taste round render <run> <stage> --title … --out …` prints two lines: the page path, then
  `pass: <stage> <n>`. **Take `<n>` from that line** for everything about this pass (the `published.json` key, the
  database doc, `taste round ingest`, `--repeat-of` on the next pass); never guess or count it yourself. Each render
  starts a new pass with its own record, so render once per pass: do not re-render to "refresh" a page the person
  is voting on.

- Render into the session scratchpad (the Artifact tool only accepts files under the working directory or the
  scratchpad): `--out <scratchpad>/taste-<slug>-<stage>`. A re-render replaces the earlier one in that folder;
  never `cp` into it.
- Load the `artifact-design` skill if it is not loaded this session.
- Publish `file_path` = `<out>/index.html`, `root` = `<out>`, `files` = an object mapping each key of
  `<out>/files.json` to itself (e.g. `{"img/i001.jpg": "img/i001.jpg", ...}`; the absolute values in `files.json`
  are not used for publishing), `capabilities: {"db": {}, "user": {}}`, `icon: "palette"` on the first publish,
  and a one-line description ("Taste survey for <project>", "Boards for <project>", ...). Publish each new pass of
  a stage from the same `file_path` so the link stays the same; each pass writes to its own database doc.
- After each publish, merge an entry into `<run>/published.json` (an object; keep what is there):
  `"<stage>-<n>": {"url": "<artifact url>", "at": "<publish time, UTC ISO 8601>"}`.

## Reading a page back (same for every stage)

When the person says they are done with pass `<n>` of `<stage>`:

1. Load `ArtifactData` (ToolSearch `select:ArtifactData`) and `get` on the page's url, collection `rounds`,
   doc_id `<stage>-<n>`, with `out_dir` = `<run>/page-state`. It saves `<run>/page-state/rounds/<stage>-<n>.json`.
2. `taste round ingest <run> <stage> <n> <run>/page-state/rounds/<stage>-<n>.json`.
   - Exit 1 with "older version of the page" or "no timestamp" (a stale page): tell the person their votes were made
     on an older version of the page and ask them to vote again on the current one. Do not ingest around it.
   - An empty or missing doc means they have not voted yet: say so and wait.
3. Act on the page's requests (they are in the record and in `taste round steer <run>`):
   - `add-url`: `taste add <url>` (and for the broad stage also `taste survey-add`, below), then confirm it was added.
   - `more-like` on an item or board: search for more of that look (see "Agent search") and offer them in the next pass.
4. `taste gaps <run>` prints what is thin ("Nothing liked in textures yet", "Direction 3 is thin (5 images)"). Tell
   the person each gap in one line and offer both ways to fill it: you search, or they add their own (paste links
   on the page, or `taste add`).

## Agent search (on every repeat of stages 1-3, and for every more-like request)

Steer it with `taste round steer <run>` (likes, dislikes, kept, dropped, notes, combos, prompts, requests) and
the profile. Search by visual traits, never by the project's subject.
- Library: `taste lib search "<style terms>" --kind image --sheet <run>/scout/lib-<label>` and Read the sheets
  (never individual thumbnails); `taste lib show <id>` for source and licence.
- Web scouting: `taste scout <run> <style id|survey> --cosmos "<terms>" --designspiration "<terms>"` (headless,
  ~30 s; numbered candidates and contact sheets `<run>/scout/sheet-<style>-N.png`). Read every sheet and keep only
  images that genuinely show the look.
- Mobbin (UI looks, only when its MCP is connected and the person's plan allows): `search_screens` /
  `search_sections` (`image_format: "jpg"`, `limit` 10-15) with a concrete screen described in the look's
  visible traits; Mobbin image urls expire, so download keepers at once (below).

## 1. Broad (single images)

Languages come from the person's taste and from what is genuinely good right now, not from the project's subject.

- The argument is a project directory or free text. `taste new <slug>` creates the run and prints its path (it
  refuses when the library is empty: see Setup).
- Pull in about **100 design references worth mentioning for whatever reason**: highly liked or most-saved, newly
  released, trending this month, award winners (site of the day, type of the year), much-shared studio work. Spread
  wide: app UI, websites, posters and print, type specimens and new typefaces, identities, motion stills,
  illustration, texture. No filtering by the project's subject, and no single style dominating (no more than ~10
  of one look). Lean towards the profile's liked traits but keep a third of the set outside them.
- Sources: the library (`taste lib search`, Read the sheets, then add each pick as below), any enabled connectors,
  then scouting: `taste scout <run> survey --cosmos "<terms>" --designspiration "<terms>"`, Read the sheet,
  `taste survey-keep <run> 03 07 … --why "<why notable>" --tag <tag>`. Anything else (a gallery front page, a
  foundry's new release, a library image, a Mobbin screen):
  `taste survey-add <run> <image url|file> --title "…" --source <page url> --why "…" --tag <tag>`. Every item needs
  a real reason in `--why` (e.g. "Godly, most-liked October", "new from Pangram Pangram", "Awwwards SOTD
  2026-10-14"). Tags: ui, web, poster, type, identity, motion, illustration, texture, palette.
- `taste round render <run> broad --title "<Project>" --out <scratchpad>/taste-<slug>-broad`, publish, and give the
  person the link: "Like or dislike what catches your eye, add a note anywhere, then tell me."
- **Stop until they say they're done.** Read the page back (ingest broad pass `<n>`).
- Write `<run>/taste.json`: `{"likes": [ids], "dislikes": [ids], "note": str, "traits_liked": [str],
  "traits_disliked": [str]}`, from `taste round steer <run>`, the traits being what the liked and disliked items
  have in common (palette, type, density, finish), stated plainly. Rewrite it after every broad pass.
- **Repeat on request** (or offer one when fewer than ~15 items were liked): add a fresh set from agent search,
  steered by the likes, dislikes and notes, then `taste round render <run> broad --title … --out … --repeat-of <n>`.
  The new pass shows the whole survey again with the new items in it.

## 2. Boards (design languages)

- Read the project: its `CLAUDE.md`, README and main screen for practical constraints (audience, what the UI must
  not compete with, existing look or brand, platform and tech limits). Free text: use it as-is.
- Propose **design languages** drawn from the survey (default 6, any count the person asks for): each grows out of a
  cluster of liked items (cite their ids) and steers clear of the disliked traits and the profile's rules. They
  must differ clearly from each other (and from any look the project already has, unless the person asks to refine
  it). Apply the beauty-not-theme test to each. For each: a name, one line on **what makes it beautiful** plus any
  practical fit, never a link to the subject; whether it is mainly **UI** or **graphic/print**; the liked survey ids
  it comes from; and 2-4 **style search terms** naming visual traits (e.g. "neumorphic ui", "soft extruded
  buttons"; "swiss grid poster", "akzidenz grotesk").
- **Stop:** show the languages in a short table and ask the person to keep, swap or rename. Carry on only with the
  confirmed set, numbered 1, 2, 3 …
- Write `<run>/brief.json`: `{"project": str|null, "project_dir": str|null, "summary": str, "audience": str,
  "constraints": [str], "styles": [{"id": "1", "name": str, "why": str, "kind": "ui"|"graphic",
  "survey_ids": [str], "terms": [str]}, ...]}`.

### References per language
- **Library first.** For each language `taste lib search "<style terms>" --kind image --sheet <run>/scout/lib-<id>`
  (also `--kind texture`, `--kind font` where the language needs them), Read the sheets. Keepers go into `refs.json`
  as `"dlib_ids": ["<item id>", …]` on that style; `taste gather` plucks them in.
- Sites whose **look exemplifies the language** (portfolio sites, galleries with a browsable front page), 0-6 per
  language, each under one language only. With the Obsidian connector on, `<run>/library.json` lists the person's
  saved resources; pick from it the same way.
- Instagram saves (connector) only if they show the language: their post codes go in `vault_posts`.
- Internet Archive is **opt-in**: add `archive_queries` only for material it actually holds (historic maps, scanned
  zines, type specimens), and expect to discard most of it.
- Write `<run>/refs.json`: `{"styles": [{"id": "1", "name": str, "sites": [{"url", "note", "title"}],
  "archive_queries": [], "vault_posts": [str], "dlib_ids": [str]}, ...]}`.

### Scout each language
This is where most of a board comes from. For every language:
1. `taste scout <run> <style id> --cosmos "<style terms>" --designspiration "<style terms>"`. If Cosmos throttles it
   says so and Designspiration covers; for a second try use different terms.
2. **Read every sheet** and keep only images that genuinely show the language: its UI, type, texture, colour,
   layout. Drop off-style results, stock photos of people or products, and anything about the project's subject.
3. `taste keep <run> <style id> 01 04 07 …` moves the keepers into the inbox (`<data dir>/inbox/<id>/`) with their
   source pages and files them into the library (`curated/<language slug>`). Aim for 12-16 keepers per language;
   scout again with other terms if short.

Never point scout, a browser or anything else automated at Are.na, Gurafiku, Artvee, eMuseum or Design Reviewed
(Are.na asks AI agents not to access it). If scout fails outright (Chromium missing, both galleries empty) and the
person has a browser extension connected, the same galleries can be read there: Cosmos result tiles are
`img[data-testid="element-image-img"]` on `cdn.cosmos.so/<id>` (append `?format=jpeg&w=1600`), Designspiration
tiles are `img.gridItemContent` on `dspncdn.com/a1/media/<size>/<path>` (use `692x`); feed them through
`taste inbox-add <id> "<image url>" --source "<search page>" --note Cosmos|Designspiration`.
Mobbin keepers: `taste inbox-add <id> "<image_url>" --source "<mobbin_url>" --note Mobbin`.

**The person's own saves** (optional, never wait on them): offer per-language search links for the galleries you
may not automate, `https://www.are.na/search/<q>` · `https://gurafiku.tumblr.com/search/<q>` ·
`https://artvee.com/?s=<q>` · `https://www.emuseum.ch/search/<q>` (URL-encode the style terms as `<q>`); their
saves go in `<data dir>/inbox/<id>/` (optional `sources.txt`: `filename<TAB>url[<TAB>note]`), or `taste add`.

### Gather, directions file, render
- `taste gather <run>` (a few minutes with sites) folds in site screenshots, connector media, library plucks, any
  Archive queries and the inbox, and prints counts per language; report them in two lines. Each language needs at
  least 8 good images; scout more if not. Exit 2 means Chromium is missing: give the person
  `playwright install chromium`. Re-running gather rebuilds the pool and reuses earlier downloads.
- `taste sheet <run>` writes one set of sheets per language; Read every sheet, and `pool.json` for sources, colours
  and each image's `style`.
- Board N **is** language N (same id). Choose 8-12 images (up to 60 with sections) that best show the language, the
  strongest first (slots 1 and 6 are drawn big). **More than half must be tagged with its own style**; an image may
  sit in at most two boards. Drop images that don't show the language even if they were gathered for it.
- Rationale ≤2 lines: what defines the language and why it suits the project. Motifs: 3-5 visual traits.
- Axes (palette / density / type / imagery): each pair of directions must differ on at least two.
- Palette: `taste palette <run> <image ids...>` suggests one; choose and order 5 hex, each `#rrggbb`.
- Type: one display + one text family typical of the language, Google Fonts family names written with only
  letters, digits and spaces.
- Write `<run>/directions.json` and run `taste validate <run>` until it prints `directions ok`. Shape:
  `{"directions": [{"id": "1", "name": "...", "rationale": "...", "image_ids": ["i004", ...],
  "palette": ["#rrggbb" x5], "type": {"display": "...", "text": "..."}, "motifs": ["...", 3-5],
  "axes": {"palette": "...", "density": "...", "type": "...", "imagery": "..."}}, ...]}`
  (optional per direction: `sections` {"ui"|"graphic"|"texture": [image ids]}, palette variants, font pairings,
  `components`, as `taste validate` accepts them).
- `taste round render <run> boards --title "<Project>" --out <scratchpad>/taste-<slug>-boards`, publish, and give the
  link: "Keep or drop whole boards or single images, note anything, then tell me."
- **Stop**, then read the page back (ingest boards pass `<n>`). Board votes are ids `d<direction id>`, image votes
  `<direction id>/<image id>`.
- **Repeat on request**: copy `directions.json` to `directions-boards-<n>.json` first (the record keeps ids only),
  then rework it from `taste round steer <run>`: replace dropped boards with new languages grown from the notes and
  likes, swap out dropped images, scout for more-like requests, gather, validate, and
  `taste round render <run> boards … --repeat-of <n>`.

## 3. Directions (parts, combinable)

- Narrow `directions.json` to the kept boards (keep a copy as above), without the dropped images, ideally 3-4. Do
  all gathering for them first. Direction ids must run `1`…`n` (then `m1`…), so renumber the kept ones and, in
  `pool.json`, change each image's `style` by the same map (images of dropped languages become `null`); a later
  `taste gather` restores the old tags, so to add images after renumbering, scout and keep under the new id, gather,
  then re-apply the map to `pool.json`. Fill each direction out so all five parts are
  real: palette (`palettes` variants if useful), type pair (`fonts` pairings), texture (`sections.texture`),
  `components`, imagery. `taste validate <run>` until `directions ok`.
- `taste round render <run> directions --title "<Project>" --out <scratchpad>/taste-<slug>-directions`, publish, and
  give the link: "Keep or drop whole directions or single parts, mix parts across directions in the mixer, note
  anything, then tell me."
- **Stop**, then read the page back (ingest directions pass `<n>`).
- Mixes: `taste combine <run> --from-round <n>` adds each mix as a new direction (`m1`, `m2` …) to `directions.json`
  and prints them; it is safe to run twice. When it added any, `taste validate <run>`, then render the next
  directions pass (`--repeat-of <n>`) so the person sees the mixes as directions in their own right.
- Repeat on request, steered by the record, until the person names one direction (or one mix) as the pick. If they
  reply with an id instead of voting, use that.

## 4. Final (the real main screen)

- Brief: `taste brief <run> --pick <id> --note "<note>" --project <project dir>` (omit `--project` for a free-text
  brief; it lands in the run folder, say where). Exit 1: unknown pick id (check `directions.json`). Exit 2:
  `design/direction.md` exists; ask the person before re-running with `--force`.
- `taste profile project <run> --project <project dir>` writes `design/taste.md` (direction, survey traits, every
  note so far). Run it again whenever notes are added later.
- Demo: the person judges a direction by seeing it on the project, so every pick ends with a demo design on a
  claude.ai Design canvas.
  - `Artifact` `action: "quickstart"`, `intent: "design"`, then create from the Design type it names (`title`
    "<Project> — <direction>", `auto_open: "after_first_write"`) and follow the type's instructions for its files.
  - Show the project's **real main screen** (its actual copy, controls, sections and content from the repo, or the
    live site), restyled in the chosen direction: the brief's palette, type pair and motifs; nothing invented,
    missing facts as `[PLACEHOLDER]`. A website or app screen is one fluid PAGE artboard (`expand: "fill"`, `w`
    1440) that also works at phone width; add more artboards only if the project's core is several screens.
  - Real imagery beats placeholders: screenshot the live site or app with Playwright (hide overlays, crop) or use
    project assets, upload as an asset, and use its url. One accent-colour tweak (the brief's accent plus 2 palette
    alternatives) is enough.
  - Write `"demo": "<canvas url>", "demo_at": "<publish time, UTC ISO 8601>"` into `<run>/published.json` (merge;
    update `demo_at` on every republish), and append `Demo: <canvas url>` to `<project>/design/direction.md`.
  - Give the person the link with one sentence on what it shows: "Pin a comment anywhere you want something
    changed, then tell me."
- When they are done: `ArtifactComments` `action: "read"` on the canvas url; write each comment as
  `{"text": "<comment>", "anchor": "<what it is pinned to>"}` into `<run>/page-state/final-comments.json` (a list),
  then `taste round final <run> <run>/page-state/final-comments.json`. Comments already recorded are skipped. Then
  `taste profile project <run> --project <project dir>` again.
- Stop there. Changes to the finish go through `taste-refine`; building the direction into the real code is a
  separate job, only when the person asks for it.
