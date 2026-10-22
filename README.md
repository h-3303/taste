# taste

`taste` is a taste curator for Claude Code. Before an agent designs anything, it should know what the person
likes in general and what they want for this project; that context is usually missing, so agents design to an
average. `taste` gathers it through a funnel of picks and notes on claude.ai artifact pages (about 100 single
references, then collage boards of design languages, then full directions whose parts you can mix, then the
chosen direction on your project's real main screen, then refine passes for as long as you like) and keeps the
result as plain files any agent can read: `design/direction.md` and `design/taste.md` in the project, and a general
taste profile you confirm item by item. It ships with a design library (fonts, palettes, textures, inspiration,
sites, icons, snippets) that you keep adding to.

## Install

In Claude Code:

```
/plugin marketplace add h-3303/taste
/plugin install taste@taste
```

The CLI the skills drive (Python 3.12+, [uv](https://docs.astral.sh/uv/)):

```
uv tool install git+https://github.com/h-3303/taste
playwright install chromium
taste seed install
```

If `playwright` is not on your PATH after the install, run it from the tool's environment:
`~/.local/share/uv/tools/taste/bin/playwright install chromium`. `taste seed install` downloads the seed library
from the latest release; `taste --version` checks the install.

Pages are published as private claude.ai artifacts, so you need a Claude account that can publish artifacts.

## First run

In a project directory:

```
/taste <project>
```

The `taste` skill runs the funnel and stops at each page until you say you are done. Every stage can be repeated
as often as you like, and a repeat is steered by everything you liked, dropped and noted so far. The other two
skills: `taste-refine` (refine passes on the chosen direction, and the end-of-project profile review) and
`taste-library` (search, pluck and add to the library).

## Commands

```
taste new | gather | scout | keep | inbox-add | sheet | palette | validate | brief | survey-add | survey-keep
taste round render|ingest|steer|final   taste gaps   taste combine   taste refine check|apply
taste profile show|project|apply        taste library-page          taste add <file|folder|url>
taste lib search|show|collections|status|sources|pluck|cache|collection|add
taste seed install   taste sync   taste import   taste connect|disconnect|connectors
```

`taste --help` prints the arguments.

## Connectors

All off by default. Switch one on with `taste connect <name> --path <dir>`, off with `taste disconnect <name>`,
and list them with `taste connectors`:

- `folder-images`: a folder of images.
- `folder-notes`: a folder of markdown notes that hold image paths or URLs.
- `obsidian-resources`: an Obsidian vault's `Resources` notes (`type: resource` in the frontmatter).
- `instagram-media`: saved Instagram media laid out as `<creator>/<code>_N.jpg`.
- `obscura` (`--bin <path>`): the Obscura renderer instead of Playwright Chromium.

Coming from the older moodboards and design-library tools: `taste import --dlib <dir> --moodboards <dir>
--project <dir>`.

## Data

Everything lives in one data dir: `$TASTE_DATA`, default `~/.taste/`.

- `library/`: the library database, thumbnails and the pluck cache (capped at 2 GB).
- `runs/<date>-<slug>/`: one folder per funnel run, with one JSON record per stage pass in `rounds/`.
- `inbox/`: images dropped in by hand for a run's boards.
- `profile.md`: your general taste profile (plain markdown; edit it freely, `taste` only appends what you tick).
- `config.json`: connector settings.

## What ships

The plugin never redistributes other people's images. Openly licensed library items (Google Fonts, Fontsource,
Fontshare, Collletttivo, ambientCG, Poly Haven, palette datasets, MIT/ISC/CC0 code and icon sets, LYGIA's BSD
items) ship with thumbnails. Gallery items (Cosmos, Designspiration, Savee, Behance, site screenshots and the
like) ship as links only: title, tags, language and source page, with thumbnails fetched on your own machine on
first use, politely and rate-limited. Proprietary items, your own additions and anything from Are.na, Artvee,
eMuseum, Gurafiku or Design Reviewed never ship; those sites are refused in code. Tests (`tests/test_shipping.py`)
keep it that way.

## Development

```
uv sync
uv run pytest -q
```

Licence: to be decided.
