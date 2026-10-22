---
name: taste-refine
description: Keep refining a chosen design direction after the taste funnel, and keep the person's taste profile current. Runs open-ended refine passes (per-layer options shown as stills, one pick per layer plus notes and free prompts) that update design/direction.md, design/taste.md and the Design-canvas demo but never the project's code, and the end-of-project review that proposes what to lift into the general taste profile for the person to confirm. Also the rule to read the profile before any design work. Use when the person says "refine", "another pass", "finish pass", "tweak the direction", "what's in my profile", "update my taste profile", "review my taste", or a /taste run has reached its demo; and before designing anything for someone who has a taste profile.
---

# taste-refine: refine passes and the profile

## Before any design work

Run `taste profile show`. It prints the general profile (liked and disliked traits, rules, references, projects)
or says there is none yet. Treat its **Rules** as binding and its traits as the default lean. In a project, also
read `design/direction.md` and `design/taste.md` when they exist. Do this before proposing any look, writing UI,
or picking type and colour, whether or not `/taste` was used in this session.

Never write `profile.md` by hand or silently: the profile changes only through the review stage below.

## Refine passes (open-ended)

A pass offers a short list of changes per layer; the person picks at most one per layer, adds notes or a free
prompt, and sees the result. Passes never end by themselves: offer another after each one until the person stops.
**Refining never edits the project's code**: it changes `design/direction.md` ("Current finish"),
`design/taste.md` and the Design-canvas demo only. Building it into code is a separate, explicit request.

Needs a run with a brief (`taste brief`, from the `taste` skill) and ideally its demo. The next pass number `<n>` is
one more than the highest `<run>/rounds/refine-<k>.json` (1 when there is none).

1. **Options.** Layers by kind: `ui` = ground, cards, depth, ui, type, accent; `graphic` = ground, type, accent,
   imagery, texture. Leave out layers with nothing worth changing. For each listed layer offer 2-6 options, each a
   real change steered by the person's notes so far (`taste round steer <run>`, the demo's comments, the profile)
   and by the beauty-not-theme rule (a change is never justified by the project's subject).
2. **Stills.** Each option is shown as a still of the main screen with only that change applied. Make them from the
   demo: copy its page, apply one option, and screenshot with Playwright at 1440 px wide (crop to the part that
   changes if the change is small). Save under the run, e.g. `<run>/refine/<n>/<layer>-<id>.png`.
3. Write `<run>/refine/<n>-options.json`:
   `{"kind": "ui"|"graphic", "layers": {"<layer>": [{"id": "a", "label": "Warm off-white ground",
   "still": "refine/<n>/ground-a.png", "detail": "#f4efe6 under every surface"}, ...]}}` (`still` is a path
   relative to the run; ids are letters, digits, `-` or `_`).
4. `taste refine check <run> <n>` until it prints `ok`.
5. `taste round render <run> refine --title "<Project> — pass <n>" --out <scratchpad>/taste-<slug>-refine`, then
   publish it exactly as the `taste` skill publishes a stage page (`root`, `files` mapping each key of
   `files.json` to itself, `capabilities: {"db": {}, "user": {}}`) and record it in `<run>/published.json`. Give the
   link: "Pick at most one change per layer, add notes or a prompt, then tell me."
6. **Stop** until they are done. Read it back as every stage is read back: `ArtifactData` `get`, collection
   `rounds`, doc_id `refine-<n>`, `out_dir` `<run>/page-state`, then
   `taste round ingest <run> refine <n> <run>/page-state/rounds/refine-<n>.json`. A stale-page error means their
   picks were made on an older version: ask them to pick again.
7. `taste refine apply <run> <n> --project <project dir>` appends `## Refine pass <n>` to `design/taste.md` and
   rewrites the "Current finish" section of `design/direction.md` (run folder when there is no project).
8. Update the Design-canvas demo with the picked changes and every prompt, republish it, and update `demo_at` in
   `<run>/published.json`. Give the link with one line on what changed, and offer the next pass.

## End-of-project review (general profile)

When the person says the project's design is settled (or asks to update their profile):

1. `taste profile project <run> --project <project dir>` (refreshes `design/taste.md` and records the project dir;
   it must run before `taste profile apply`).
2. Propose what to lift into the general profile: traits seen across the survey and passes, rules the person
   stated, references they kept. Ask yourself for each: is it the person's taste, or only this project's need?
   Project-only rules (one client's "no brown") get `"default": false`; general ones `true`.
   Write `<run>/proposals.json`: `[{"id": "p1", "section": "Liked traits"|"Disliked traits"|"Rules"|"References",
   "text": "...", "default": true}, ...]`.
3. `taste round render <run> review --title "<Project> — profile review" --out <scratchpad>/taste-<slug>-review`,
   publish as above, and give the link: "Tick what is true of your taste in general, then tell me."
4. **Stop**, then ingest it (`ArtifactData` `get` collection `rounds`, doc_id `review-<n>` into `<run>/page-state`,
   then `taste round ingest <run> review <n> <file>`).
5. `taste profile apply <run> <n>` adds the ticked proposals and the project's line to the profile (append-only;
   ticking the same thing twice adds nothing). Show the person `taste profile show`.

The review applies what that page showed (a snapshot taken at render time). To reword a proposal, edit
`proposals.json` and render a new review pass; editing after rendering changes nothing for the old pass.

Proposals from an imported history (`taste import --moodboards …` writes `<data dir>/import-proposals.json`): copy
them into a run's `proposals.json` (start one with `taste new profile-import` if needed) and run steps 3-5.
