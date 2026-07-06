# issues.md — bug audit trail

Living log of bugs: date, area, description, **root cause** (code bug / test bug /
design bug), status. On resolution: the fix + commit + whether a regression test
was added. Newest first.

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
