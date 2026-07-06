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

- **Host the SVG print files** (priority: high). Printful's mockup generator fetches the print
  file by public URL. The pipeline writes `artifacts/<drop_id>.svg` and fails loud until
  `PRINTFUL_PRINT_FILE_BASE_URL` points at a reachable host (S3/R2/Cloudflare). Until then the
  Factory cannot complete end-to-end.
- **FastAPI + Starlette BadHost upgrade** (priority: high). Pin fastapi/starlette to the
  CVE-2026-48710-patched line once resolvable; confirm `starlette >= 1.0.1`. Interim mitigation
  (TrustedHostMiddleware) is in place. See `security.md`. **Blocked:** `starlette >= 1.0.1` is a
  major jump incompatible with the pinned `fastapi==0.115.6` (needs `starlette < 0.42`); do it as
  a coordinated fastapi+starlette upgrade with a fresh advisory sweep, not a lone bump.
- **Lock files / hash-locked installs** (priority: medium). The frontend commits
  `package-lock.json` (CI uses `npm ci`); add `uv lock` / `pip-compile --generate-hashes` for the
  backend and install with `--require-hashes`.

## Done (was here, now implemented)

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

- **Storefront URL + conversion path** (priority: high before any real X posting). Phase 1 has no
  checkout, so the broadcast is a teaser. The code path exists (`STORE_BASE_URL` → shop link in the
  broadcast); it stays a teaser until a real product/store URL + CTA is wired and a drop is buyable.
- **Per-source rank normalization at scale** (priority: low). The lanes + `normalized_hype` land the
  honest within-source ranking. If sources later need cross-source triage (one merged action queue),
  add an explicit exposure-weighted score — never a bare `hype_score` compare across measurements.

## Phase 2+

- **Public storefront + checkout** (priority: low for now). Explicitly out of Phase 1 scope.
- **Auth on the admin dashboard** (priority: high before any non-local deployment). The API is
  currently open behind CORS + trusted-host only. Do it properly: route the dashboard's calls
  through Next.js server-side (Route Handlers / Server Actions) so an `ADMIN_API_TOKEN` lives only
  on the server, then require it on the FastAPI side — a browser-direct token would be public.
  Deferred this pass because it's a meaningful refactor and we're not deploying yet.
