# Backlog

## Data access (deferred from Phase 1 scaffold decision)

The Phase 1 spec listed both SQLAlchemy (Python) and Prisma (Next.js) over one DB.
We shipped option 1 — Next.js as a thin HTTP client over FastAPI, which solely owns
the SQLite DB — to honor single-source-of-truth and avoid two ORMs writing one file.
The alternatives, if ever needed:

- **Prisma read-only mirror for the dashboard** (priority: low). Let Next.js read trends
  via Prisma for richer server-side querying, while all writes stay on FastAPI. Requires a
  Prisma schema kept in sync with `models.py` and a sync/contract test. Only worth it if the
  dashboard outgrows the REST endpoints.
- **Prisma direct read+write** (priority: low / discouraged). Matches the literal spec but
  means concurrent writers to one SQLite file — corruption + schema-drift risk. Revisit only
  if the DB moves to Postgres with proper concurrency.

## Factory pipeline gaps

- **Real-mode Printful hosting setup** (priority: high — a human step, not code, PLAN.md 2A #2/#3).
  The storage code is done (`PRINT_FILE_STORAGE=local|github_pages`); what's left is external:
  create the GitHub Pages artifacts repo + a token (or deploy so `local` is publicly reachable),
  and a free Printful account to exercise live. Until hosting is reachable, submissions fail loud.
  **Cloudflare R2** (boto3 + a card) is the deferred storage upgrade.
- **FastAPI + Starlette BadHost upgrade** (priority: high). Pin fastapi/starlette to the
  CVE-2026-48710-patched line once resolvable; confirm `starlette >= 1.0.1`. Interim mitigation
  (TrustedHostMiddleware) is in place. See `security.md`. **Blocked:** `starlette >= 1.0.1` is a
  major jump incompatible with the pinned `fastapi==0.115.6` (needs `starlette < 0.42`); do it as
  a coordinated fastapi+starlette upgrade with a fresh advisory sweep, not a lone bump.

## Done (was here, now implemented)

- ~~Print-file storage~~ (PLAN.md 2A #2) — `factory/storage.py`: `local` (serve from this backend,
  fails loud on localhost) + `github_pages` (push to a public artifacts repo + poll until live,
  idempotent via blob sha). Replaced the `PRINTFUL_PRINT_FILE_BASE_URL` assumption. R2 deferred.
- ~~Real ToS-clean source + family filter~~ (PLAN.md 3 #2/#5) — `wikipedia` most-viewed articles
  (open pageviews API, no key); Reddit dropped (commercial ToS); a keyword blocklist drops
  family-unsafe trends before the queue (an LLM classifier would be stronger — deferred).
- ~~X monthly budget guard~~ (PLAN.md 2B) — `X_MONTHLY_BUDGET_USD` refuses an api-mode auto-post
  that would exceed the month's cap (conservative count). Free intent mode is unaffected.
- ~~Lock files / hash-locked installs~~ (PLAN.md 4 #4) — `requirements.lock` / `requirements-dev.lock`
  (`uv pip compile --generate-hashes`); CI installs with `--require-hashes`.

- ~~Trend observation history~~ — append-only `trend_observations` table; the worker writes one
  snapshot per sweep (`worker.py`), `GET /api/trends/{id}/observations` serves the history, and each
  `/trends` row carries a `spark` series the Studio draws as an inline sparkline.
- ~~Pipeline retries + idempotency~~ — each external step commits as it lands and is skipped when its
  result is already present, so a retry RESUMES; the tweet id is committed before the published
  transition so a crash-after-post can't double-tweet. `POST /api/drops/{id}/retry` + a UI button
  reserve the in-flight slot (unique index) and re-run. Unit tests cover no-double-post + resume.
- ~~True cross-source normalization~~ — trends group into per-source lanes in the Studio, each ranked
  within its own source; `normalized_hype` (0..1, min-max over a source's population) is the honest
  within-lane scale. Volumes are never ranked on one global scale across incomparable measurements.
- ~~Garment-color safety~~ — `print_color_for_garment` derives ink from `PRINTFUL_GARMENT_COLOR`
  (light garment → dark ink, dark → white), so art never prints white-on-white. Unknown color logs
  a warning and defaults to white (safe for the black default variant).
- ~~Printful rejects SVG~~ (PLAN.md 2A #1) — `factory/render.py` rasterizes a transparent print-ready
  PNG with Pillow (bundled scalable font, no system cairo, no vendored binary); the SVG stays as the
  source. Pipeline hosts/serves `<id>.png`. Real-mode hosting (above) is the remaining gate.
- ~~X has no free API tier~~ (PLAN.md 2B) — `X_BROADCAST_MODE=intent` (default) generates a prefilled
  `x.com/intent/post` URL the operator clicks ($0, no keys); `=api` keeps the metered auto-post path
  (logs per-post cost). "Post to X" button in the Studio.

- ~~Real source-adapter hardening~~ — `radar/fetch.py` adds disk caching, per-host rate limiting
  (>=1.5s), and 429 backoff.
- ~~X v1.1 media upload~~ — X deprecated v1.1 media on 2025-06-09; the client now targets v2
  `POST /2/media/upload` with defensive id parsing.
- ~~Hype Score collapse~~ — found by running it: `velocity * volume` zeroed every score on the
  second identical sweep. Rebased on a volume base with a capped velocity boost (`scoring.py`).
- ~~Factory always failed without secrets~~ — added `FACTORY_DRY_RUN` so the loop completes with
  clearly-marked simulated outputs (drops reach `published`); backend serves the generated SVG at
  `/artifacts/<id>.svg`. Real-mode hosting + creds (above) still needed for actual publishing.
- ~~Duplicate-drop race~~ (PR review) — replaced the check-then-insert 409 with a DB-level partial
  unique index on `trend_id` while in-flight; the route catches `IntegrityError`. Concurrency test added.
- ~~Off-canvas shirt art~~ (PR review) — `build_text_svg` now fits the largest font that keeps wrapped
  copy inside the print area (was unbounded lines → invisible art). Regression test asserts containment.
- ~~Cross-source volume confusion~~ (PR review) — added a `measurement` field per trend
  (`search_traffic` / `presence` / `seed`), surfaced in the UI so volumes aren't implied comparable.
- ~~Missing source trail~~ (PR review) — trend card links `source_url`, shows `last_seen`, and flags
  seed/no-source data as "verify before publishing".
- ~~Tweet claimed a non-buyable drop was "live"~~ (PR review) — broadcast copy no longer claims "live";
  it only links a shop URL when `STORE_BASE_URL` is set, reserving characters for it.

## Open follow-ups from the PR review

- **Storefront URL + conversion path** (priority: high, PLAN.md 2B). The broadcast wiring is done
  (`STORE_BASE_URL` → shop link in the intent/tweet copy), but it stays a *teaser* until a real
  storefront exists. Plan default: a **Printful Quick Store** ($0, Stripe checkout) — validate that
  an API-created sync product gets a shareable product URL (manual 30-min test), then store that URL
  on the drop. Fallback: Shopify Starter (~$5/mo) or manual publish.
- **Per-source rank normalization at scale** (priority: low). The lanes + `normalized_hype` land the
  honest within-source ranking. If sources later need cross-source triage (one merged action queue),
  add an explicit exposure-weighted score — never a bare `hype_score` compare across measurements.

## Open follow-ups from code review (2026-07-06)

- **LLM family-safe classifier** (priority: medium, PLAN.md 3 #5). The keyword blocklist over-blocks
  ("grape harvest") and can't judge context ("Suicide Squad (film)"). A Haiku pass cached by content
  hash, gated behind the keyword filter, is the real fix — deferred (needs an API key + cost budget).
- **Wikipedia date fallback** (priority: low). The source reads `-1 day`; if that day's pageviews
  aren't published yet the source is empty that sweep (now logged). Try `-2` on a 404.
- **github_pages: webhook over 2-min poll** (priority: low). `_wait_until_live` blocks a worker thread
  up to ~2 min on a first publish (Pages deploy lag). Fine for a single operator; a Pages-deploy
  webhook would free the thread if throughput ever matters. See `issues.md`.
- **Per-source sweep coverage counts** (priority: low). `run_sweep_once` logs a single `touched=N`;
  a per-source `fetched/parsed/dropped` line would make a silently-failing source obvious at a glance.

## Phase 2+

- **Public storefront + checkout** (priority: low for now). Explicitly out of Phase 1 scope.
- **Auth on the admin dashboard** (priority: high before any non-local deployment). The API is
  currently open behind CORS + trusted-host only. Do it properly: route the dashboard's calls
  through Next.js server-side (Route Handlers / Server Actions) so an `ADMIN_API_TOKEN` lives only
  on the server, then require it on the FastAPI side — a browser-direct token would be public.
  Deferred this pass because it's a meaningful refactor and we're not deploying yet.
