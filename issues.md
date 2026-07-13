# issues.md — bug audit trail

Living log of bugs: date, area, description, **root cause** (code bug / test bug /
design bug), status. On resolution: the fix + commit + whether a regression test
was added. Newest first.

---

## 2026-07-13 — v2 critical code review (multi-agent) findings

Fixes for bugs found by an 8-angle critical review of the v2 diff (T1 discovery +
Part B copy-gen + Part C merch). All fixed on the v2 branch; tests: 136 backend +
31 vitest passing.

### Fixed

- **Per-drop garment picker produced invisible prints** · `factory/pipeline.py` +
  Part C plumbing · **design bug** · Fixed.
  The garment dropdown set the *ink* color (`print_color_for_garment`) but the
  Printful mockup/sync always ordered the fixed default variant (black). Picking
  "white" rendered dark ink → printed on the black shirt → unreadable — the exact
  white-on-white failure inverted. Removed the half-wired picker end-to-end (model
  column, migration entry, schema, DropOut, routes, pipeline, types, api,
  TrendCard, merch); ink now derives from the actually-ordered garment. Layout
  variety kept. Real garment variety needs a Printful color→variant map (backlog).

- **Debug SVG diverged from the printed PNG for 3 of 4 layouts** · `factory/printful.py`
  `build_text_svg` · **code bug** · Fixed.
  The pipeline rasterized the PNG with `layout=` but built the SVG "source" with no
  layout, so `top_left`/`oversized`/`boxed` SVGs showed the wrong placement (and
  `oversized` lowercased in the PNG only). Extracted the layout geometry to a shared
  `factory/layouts.py` used by both renderers; `build_text_svg` now honors layout +
  case. **Regression tests:** `test_factory_svg.py` (per-layout containment,
  oversized-lowercases, boxed-rect, top_left-anchor, unknown-fallback).

- **Empty quip batch was cached for 10 min** · `api/quips/route.ts` · **code bug** ·
  Fixed. When every candidate was filtered, the empty result was cached, so the
  UI's "try again" was a no-op for the whole TTL. Now only non-empty batches cache,
  and expired entries are pruned on write (bounding the Map).

- **Hall-of-fame trimmed append-only data by count** · `lib/hallOfFame.ts` ·
  **design bug (CLAUDE.md "Cap by content, not count")** · Fixed. `slice(-200)`
  silently dropped the oldest shipped-copy anchors. Now stores every line; the
  generator samples only the newest few. **Regression test:**
  `hallOfFame.test.ts::does NOT cap by count`.

- **Discovered adapter accepted bool/negative `shirt_score`** · `radar/sources.py` ·
  **code bug** · Fixed. `isinstance(True, int)` let JSON `true` become score 1, and
  negatives stored a negative volume with no threshold. Now rejects bool and
  negatives. **Regression tests:** `test_discovered.py` (bool/negative/zero).

- **Discovery window was 15 days, not 14** · `radar/sources.py` `parse_discovered` ·
  **code bug (off-by-one)** · Fixed. Both endpoints were admitted; the lower bound
  is now exclusive. **Regression test:** `test_window_is_exactly_window_days_not_one_more`.

- **`cleanAndFilter` double-counted repeated clichés** · `lib/quips.ts` · **code bug**
  · Fixed. Dropped lines were never added to `seen`, so a repeated cliché inflated
  the `dropped` audit count. Now records each decision. **Regression test:**
  `quips.test.ts::counts a repeated cliché only once`.

- **IP belt only caught the exact full term** · `lib/quips.ts` · **code bug** ·
  Fixed. "Taylor Swift" (ipRisk) let "swiftie"/"taylor's version" through, and the
  needle was untrimmed. Now trims and matches significant words too. **Regression
  test:** `quips.test.ts::drops partial-name IP leaks`.

- **`boxed` outline crossed the print safe-margin; `quipDropped` not reset on failed
  regenerate; cache key omitted angles/source** · render/route/TrendCard · **code
  bugs (minor)** · Fixed (clamp box to region; reset on generate; key on all prompt
  inputs).

### Regression test added for a previously-untested path

- **Additive-column migration upgrade path** · `database.py` `_add_missing_columns`
  · was only exercised via fresh `create_all`. Added `test_migration.py` (old-schema
  DB → migrate → columns added, rows preserved as NULL, idempotent, JSON round-trip,
  `_ADDITIVE_COLUMNS`↔model parity). Hardened the migration to trust ALTER +
  swallow "duplicate column" rather than reflect first — SQLite's per-connection
  schema cache made reflection disagree with the ALTER across pooled connections.

### Codex bot review (round 2) — additional fixes

- **Global top-N starved the discovered lane** · `api/routes.py` `list_trends` ·
  **code bug** · Fixed. `/trends?limit=N` ordered by global `hype_score` and
  trimmed, so the discovered lane's 0–100 scores sank below the attention sources'
  raw volumes and could vanish. Now returns the top-N *per source* (partitioned
  `row_number()`). **Regression test:** `test_low_hype_source_not_starved_by_global_limit`.
- **`shirt_score` validation missed NaN/Infinity/out-of-range** · `radar/sources.py`
  · **code bug** · Fixed. Judged scores bypass Hype, so a `500` or `NaN`
  (`json.loads` accepts non-finite) would corrupt the lane scale. Now rejects
  non-finite and anything outside 0–100. **Regression tests:**
  `test_out_of_range_shirt_score_is_rejected`, `test_non_finite_shirt_score_is_rejected`.
- **Hall of fame recorded on submit, not publish** · `TrendCard.tsx` · **code bug**
  · Fixed. A submitted-but-failed drop seeded the house voice; recording moved to
  the poll effect's `published` transition (deduped server-side).
- **Empty-sweep PR had no diff to open** · `docs/TRENDS-DISCOVERY-SPEC.md` (A4/A6)
  · **spec bug** · Fixed. The routine now always appends a run-report line to
  `data/trends/_sweeps.jsonl` (not ingested by the adapter), so a zero-candidate
  sweep still produces a diff and a PR.

### Noted, not fixed (low severity, single-operator local tool)

- Hall-of-fame append is read-modify-write with no lock (concurrent submits can
  lose-update); `/api/quips` two-stage flow, rate limiter, and cache have no unit
  tests (only the pure `lib/quips.ts` helpers do); layout containment tests sample
  corners, not edge midpoints; the family blocklist is duplicated across the
  Python/TS boundary with no drift test. Tracked in backlog.

---

## 2026-07-06 — Phase 2/3 build-out + code review

### Fixed

- **Budget guard under-counted spend** · `factory/pipeline.py` `_enforce_x_budget`
  · **code bug** · Fixed (`1579281`).
  The monthly api-post count filtered on `published_at`, but `x_tweet_id` (the real
  spend signal) commits a step earlier. A drop that posted its tweet then crashed
  before `published_at` was set had `published_at = NULL`, so it was excluded and the
  cap could be walked past. Now counts on `x_tweet_id` with a window that also catches
  posted-but-unpublished drops created this month (conservative). **Regression test:**
  `test_broadcast.py::test_x_budget_guard_counts_posted_but_unpublished_drops`.

- **Print-file storage poll swallowed every error** · `factory/storage.py`
  `_wait_until_live` · **code bug (observability)** · Fixed (`1579281`).
  The poll loop only checked `200 + content`; every other status and every network
  error hit a bare `pass` with no logging, and the final error discarded the cause. A
  permanently-broken deploy (Pages disabled, wrong `GITHUB_PAGES_BASE_URL`) failed
  after ~2 min with an opaque "never went live." Now logs each poll, fast-fails on
  401/403 with the body, and surfaces the last status in the raised error. **Regression
  test:** `test_storage.py::test_github_pages_poll_fast_fails_on_403_with_status`.

- **Wikipedia source hid fetch failures** · `radar/sources.py` `fetch_wikipedia` ·
  **code bug** · Fixed (`1579281`).
  A source-side fetch failure (`fetch.get` → `None`) and a legitimately-empty parse
  both returned `[]`, so the sweep logged `touched=0` identically whether the API was
  down all day or genuinely served nothing ("Empty ≠ broken"). Now logs a warning
  distinguishing a fetch failure from a 0-row parse (a possible format change).

- **`fetch.get` didn't back off on connection errors** · `radar/fetch.py` · **code
  bug** · Fixed (`1579281`). Only `429` backed off; a `RequestException` `continue`d and
  burned every retry against a down host. Now backs off exponentially like a 429.
  **Regression test:** `test_fetch.py::test_get_backs_off_on_connection_error_then_succeeds`.

- **Family filter dropped real trends silently + over-broad word** · `radar/sources.py`
  `is_family_safe` / `collect` · **code bug** · Fixed (`1579281`).
  Substring match is kept *on purpose* (a safety filter over-blocks; word boundaries
  would miss compounds like "Pornhub"), but "execution" was removed (false-positive on
  "code execution"), and drops are now counted per sweep so an over-broad blocklist is
  auditable. **Regression test:** `test_radar_sources.py::test_execution_removed_from_default_blocklist`.

- **`_parse_volume` silently downgraded unparseable traffic** · `radar/sources.py` ·
  **code bug** · Fixed (`1579281`). A present-but-unparseable `ht_approx_traffic` fell to
  the "presence" placeholder with no log; now warns so a format change surfaces.

- **Sparkline flat series drew at the bottom edge** · `components/Sparkline.tsx` ·
  **code bug (cosmetic) + comment rot** · Fixed (`1579281`). With `span = max-min || 1`
  and all-equal points, `y = pad + usableH` pinned the line to the bottom while the
  comment claimed "centered." Now special-cases a flat series to `height/2`.

- **Cross-platform hash-lock omitted `greenlet`** · `requirements*.lock` / CI · **code
  bug (tooling)** · Fixed (`ed32fb8`). The macOS-resolved lock omitted `greenlet` (a
  platform-conditional SQLAlchemy dep), so CI's Linux `--require-hashes` install failed
  "must be pinned upfront." Regenerated with `uv pip compile --universal`. Caught by CI.

- **Latent: Factory assumed Printful accepts SVG** · `factory/pipeline.py` /
  `printful.py` · **design bug** · Fixed (`373a46a`). The Phase-1 pipeline hosted the SVG
  and handed Printful an SVG URL; Printful's DTG pipeline rejects SVG (PNG/JPEG only), so
  a real account would always have failed at mockup. Now rasterizes a PNG (`render.py`).
  Similar research-caught assumptions: X has no free API tier since 2026-02 (→ Web
  Intent), Reddit's free API bars commercial use (→ dropped). See `docs/PLAN.md`.

### Open / accepted limitations (tracked, not defects)

- **`_wait_until_live` blocks a worker thread up to ~2 min** on a first `github_pages`
  publish (Pages deploy lag). Acceptable for a single-operator Phase-1/2 tool; it's the
  necessary behavior (you must wait for the file to be live before calling Printful).
  Revisit if throughput matters (webhook instead of poll). `factory/storage.py`.
- **Family filter is a crude keyword heuristic** — over-blocks (drops "grape harvest")
  and can't judge context ("Suicide Squad (film)"). The LLM classifier that would fix
  this is deferred (needs an API key). Tracked in `backlog.md` / `docs/PLAN.md` 3 #5.
- **Wikipedia reads yesterday's pageviews** (`-1 day`); if that day's data isn't
  published yet the source contributes nothing that sweep (logged). A `-2` fallback
  would be more robust. `radar/sources.py`.
