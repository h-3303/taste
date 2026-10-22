# taste — plugin core (phase 1)

Date: 2026-10-22 · Owner: h (h-3303) · Status: draft for approval

## Intent

`taste` is a taste curator. Before an agent designs anything, it should know where the person's design
preferences come from: what they like in general, and what they want for this project. That context is
usually missing, so agents design to an average. `taste` gathers it through a funnel of picks and notes,
keeps it as files an agent reads, and keeps refining it after a design exists.

It grows out of two working tools of h's: **moodboards** (`~/dev/moodboards`: taste survey → design
languages → collage boards on a pickable claude.ai canvas → `design/direction.md` → Design-canvas demo)
and **design-library / dlib** (`~/dev/design-library`: a local SQLite catalogue of ~13,600 fonts,
palettes, textures, images, sites, icons and snippets with thumbnails and on-demand pluck). Both work
today for h alone. `taste` merges them into one shareable Claude Code plugin.

Phase 1 is this document: the plugin core, built for Claude Code. Later phases, each with its own spec:
2. agent-agnostic (profile and rounds usable by other agents, e.g. plain files plus an MCP server; more
   connectors), 3. public listing (packaging, licence, docs, marketplace), 4. a website version of the
   same funnel. h wants none of these dropped; phase 1 must not paint them into a corner (see Constraints).

## Who it is for

Phase 1's first outside users are **designers and developers already on Claude Code** who can publish
claude.ai artifacts. They have their own projects and nothing else: no Obsidian vault, no saves, no library.
h is also a user, with connectors switched on for their own sources.

## Goals

1. **A broad-to-narrow funnel** for one project, where the sample grows more complete as the choice shrinks:
   1. **Broad**: ~100 single images across everything (app UI, sites, posters, type, identity, motion stills,
      illustration, texture). Like / dislike / note.
   2. **Boards**: design languages grown from the likes (count is free; default ~6–10), each a collage board.
      Keep / drop / note per board and per image.
   3. **Directions**: a few full directions, each split into parts (palette, type pair, texture, components,
      imagery). Parts can be picked across directions to **combine**; a combination becomes a new direction
      in the next round. Note on every part.
   4. **Final**: the chosen direction or mix applied to the project's **real main screen** on a claude.ai
      Design canvas (as moodboards step 10 does now). Notes pinned anywhere.
   5. **Refine, open-ended**: like h's dollparts finish pass. Each pass offers a list of changes per layer
      (e.g. ground / cards / depth / UI / type / accent), the user picks one per layer, mixes, adds notes or a
      free prompt, and sees the result again. It never ends by itself.
2. **Every stage repeatable** as many times as the user likes; a repeat is steered by all likes, dislikes,
   notes and combinations so far.
3. **A note option on every item, board, part and pass**, always.
4. **A two-layer taste profile** the agent reads before design:
   - **General** (`~/.taste/profile.md` or the data dir equivalent): traits liked and disliked, favourite
     references (with library ids and images), standing rules the person has stated ("no brown", "beauty, not
     theme"), updated by every project.
     It is never written silently: at the end of a project the agent proposes what to lift into it (traits,
     rules, references) on a short review page; the user ticks what is general. Project-only rules (one
     client's "no brown") stay in the project unless ticked. This review is its own stage record.
   - **Per project** (`<project>/design/taste.md` beside `design/direction.md`): the chosen direction, the
     combinations, every refine pass and its notes.
   Plain markdown with image references, readable by any agent (phase 2 builds on this).
5. **A shipped library**, seeded from everything in dlib and moodboards that can be shipped cleanly (see
   Library), and **adding inspiration as a core feature** the user is actively prompted to do, two ways:
   - the agent searches for designs the person's taste points to, and they keep or drop the results;
   - the person adds their own (image file, folder, URL, page link), on the pages or from the CLI.
6. **Its own interface**: artifact pages for everything the person looks at (rounds, library browser, add
   inspiration, profile view), with the CLI underneath for fetching, rendering and data.
7. **Optional connectors**, off by default: h's own sources become connectors anyone can switch on for their
   own setup: an **Obsidian folder** (today: vault Resources), **Instagram saves** (today: the vault's
   `Sources/media`), and the **Obscura** renderer (today: dlib's fetcher for rendered galleries).

## Non-goals (phase 1)

- Editing the project's real code. The refine loop updates `design/direction.md`, `design/taste.md` and the
  Design-canvas demo only; building the direction into code stays a separate, explicit request.
- The website, the marketplace listing and non-Claude agents (phases 2–4), beyond not blocking them.
- Replacing h's existing tools during the build: `~/dev/moodboards` and `~/dev/design-library` and their
  skills stay as they are until `taste` is proven and h decides to retire them.

## Anti-goals (would make it a failure even if it works)

- **Theme-park design.** Languages and images are never chosen because they echo the project's subject. A
  travel app does not get a passport look. Test: would it be an equally strong pick for an unrelated product?
  The project only adds practical constraints. Same for images: a board shows what a style looks like, never
  the project's subject. (Carried over from the moodboards skill; it is the core of the tool's judgement.)
- **Redistributing other people's images.** The plugin never ships scraped gallery thumbnails or
  screenshots (see Library).
- **Touching banned sites.** Are.na, Artvee, eMuseum, Gurafiku and Design Reviewed are refused in code (Are.na
  asks AI agents not to access it); users may still add their own saves from them by hand.
- **h-specific leftovers** in the shipped plugin: no "h" in skill text, no hard-coded vault path, no
  `~/<project>-data` assumptions.
- A funnel that forces the user forward: no stage may be skippable only by finishing it, and nothing a user
  noted may be silently dropped.

## Constraints

- **Stack**: Python with `uv`, as both source repos. One package, one CLI (`taste`), merging the `moodboards`
  and `dlib` CLIs. Jinja templates for pages as today. Tests with pytest. **TDD** throughout (h's default).
- **Claude Code plugin layout**: a plugin manifest, skills under the plugin (one per job; builder's call on
  the split, e.g. `taste` (rounds), `taste-library`, `taste-refine`), and the CLI installable with
  `uv tool install`. The skill text must work for any user.
- **Pages are claude.ai artifacts** published with the Artifact tool, with the `db` and `user` capabilities
  for votes, notes and picks (as the survey and canvas do now). Page state is read back with ArtifactData.
  Keep page templates free of claude.ai-only assumptions where cheap, so phase 4 can host the same pages.
- **Data dir** per user, configurable (env var + default such as `~/.taste/`): library DB, thumbnails,
  asset cache (cap as dlib's 2 GB), runs, profile. Runs keep the moodboards layout (`runs/<date>-<slug>/`).
- **Rate limits and robots.txt** as dlib does now (1 request/s per host for thumbnails; bot challenge or
  429 stops the source).
- **Phase 2 readiness**: the profile and every round's state are plain files (markdown + JSON) in the run
  and project; no state lives only in an artifact database or only in the skill's prose.

## Decisions h made (2026-10-22)

| Topic | Decision |
|---|---|
| What it is | Merge moodboards and design-library into one shareable taste curator; skill/plugin first, site later |
| Funnel | Broad images → boards → combinable directions → real screen → open refine loop; every stage repeatable; notes everywhere; combinations in the late rounds |
| Refine loop | Like the dollparts finish pass: per-layer change lists, notes and prompts; updates brief + demo only |
| First users | Claude Code designers/devs |
| Library | Add everything already held that can be added easily; adding more is core and actively prompted (agent search or own additions) |
| Shipping | Openly licensed items ship as files; gallery items ship as links; each user's machine fetches its own thumbnails |
| Interface | Artifact pages + CLI |
| Profile | Two layers: general + per project |
| Repo | New repo `~/dev/taste` (private GitHub `h-3303/taste` after approval); old repos untouched |
| h's sources | Optional connectors, off by default |
| Scope | Nothing left out overall; build for Claude first, then agent-agnostic |
| Name | `taste` |
| Renderer | Playwright/Chromium is the default for scouting and screenshots (moodboards already uses it); Obscura is an optional connector that takes over when installed. dlib's Obscura-only rule does not carry over |
| Sharing | Public GitHub repo `h-3303/taste` with a plugin marketplace manifest (`/plugin marketplace add h-3303/taste`) from phase 1; licence filtering must be right before the first public push; seed snapshots in GitHub releases |
| Library sync | h runs the full sync as maintainer and publishes seed snapshots; users get the seed, lazy thumbnails, their own additions and an optional `taste sync` for API/repo sources only (no renderer needed) |
| General profile | Proposed by the agent at project end on a review page; the user confirms what is general |

## Library

The merged library is dlib's schema (items, collections, FTS search, thumbnails, pluck cache), extended with
user additions and notes. What exists today (dlib, 2026-10-22):

- **Ships as files (thumbnails + metadata; full assets plucked from the open source on demand)**: Google
  Fonts (1,950, OFL), Fontsource (72, OFL/Apache/CC0), Fontshare (100, ITF FFL), Collletttivo (16, OFL),
  ambientCG (1,057, CC0), Poly Haven (866, CC0), GitHub palette datasets (1,374, MIT), react-bits (214, MIT),
  magicui (79, MIT), gl-transitions (125, MIT), vanta (14, MIT), LYGIA (155, BSD-3/Prosperity — check per
  item), tabler/lucide/simple-icons (96, MIT/ISC/CC0), animate-css (98, Hippocratic 2.1).
- **Ships as links only (title, tags, language, source page URL, image URL; no thumbnail)**: Cosmos (2,138),
  Designspiration (606), Savee (26), Pinterest (70), Behance (67), CARI (70), Internet Archive (48), Lospec
  palettes (949, "see palette page"; the hex values are facts and may ship, the page link stays), the
  awesome lists and design-resources (2,733 sites), site screenshots from Awwwards, Dark.design, Siteinspire,
  Land-book, Godly (431, © site owner), Texture Labs (208, own free licence), and h's 440 curated keepers.
- **Never ships**: MetalForge (34, proprietary), anything from the banned sites.
- Thumbnails for link-only items are fetched on the user's machine on first use (lazily, rate-limited), into
  their data dir. A link that has died is marked dead and hidden, not deleted.
- **Additions**: `taste add <file|folder|url>` and an add field on every page (pasted links; dropped files
  where the artifact runtime allows file storage). Each addition gets kind, tags and language, and joins the
  user's library and the current round.
- **Agent search**: at each repeat of stages 1–3, the skill runs searches steered by the profile (Cosmos and
  Designspiration scouting as `moodboards scout` does now, dlib search, Mobbin when the user's plan allows) and
  offers the results as part of the round. Pages show a "find more like this" control on items and boards;
  pressing it records a request the agent picks up on its next turn.
- **Prompting**: when a round is thin in some kind (e.g. no textures liked yet) or the library is small for a
  language, the page and the skill say so and offer both ways to add.

## Stage records

Each run keeps one JSON file per stage pass (`rounds/<stage>-<n>.json`): the items shown (library ids or run
image ids), each item's vote and note, combinations made, free prompts, and the time. The skill reads these to
steer the next pass and to write the profile. The artifact database is the live input; the JSON is the
record. A repeat links to the pass it repeats.

## What carries over from moodboards and dlib

All of today's working behaviour unless this document changes it: survey (`survey-add`, `survey-keep`,
`survey-canvas`), scout (Cosmos + Designspiration headless, contact sheets, `keep`), gather (site screenshots
via Playwright, Internet Archive opt-in, inbox), sheet, palette, validate, canvas, brief, demo; dlib's search,
sheets, show, pluck (texture maps and resolutions, font CSS, palette files, snippet licences), curated
collections, sync with sample/full/snapshot modes, timer. Also the unmerged `n-directions` branch of
moodboards (any number of directions, boards up to 60 images, sectioned boards for UI / graphic / texture,
palette variants with WCAG contrast ratios, font pairings, components): merge it into moodboards first or
port it, whichever is cleaner at build time.

## Left to the builder

- Package and module layout, how the two CLIs' commands are named under `taste`, and the skill split.
- The exact page designs for each stage (they must load the `artifact-design` skill, work at phone width, and
  keep today's canvas behaviours: pick, note, published-at check).
- How a combination is represented and rendered as a new direction.
- The refine loop's layer list per project type (web/app UI vs print) and how a pass is shown (side-by-side
  stills on a page, or Design-canvas variants).
- How the shipped seed catalogue is built and packaged (in-repo file vs first-run download) and its size.
- **Builder's calls already made (Claude, 2026-10-22; h to check):**
  - h's existing data carries over through an import command (`taste import`): dlib's DB (schema-compatible),
    moodboards runs and `taste.json` results, and existing `design/direction.md` files. Items that may not
    ship stay local to h's install and are never exported into a seed snapshot.
  - Connectors in phase 1 are generic: "folder of images" and "folder of markdown notes with URLs/images",
    with h's vault Resources and `Sources/media/<creator>/<code>_N.jpg` layouts as presets. A parser for
    Instagram's official data export comes later.
  - Maintainer-only commands (full sync, renderer-based sync, snapshot build) live in the same CLI behind
    a `taste maintainer …` group so users never need them.

## Open questions for h

None left after the builder check (answers above, 2026-10-22).
