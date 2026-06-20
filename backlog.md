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
  (TrustedHostMiddleware) is in place. See `security.md`.
- **Trend observation history** (priority: medium). Current model stores only latest + prev
  volume per trend. An append-only `trend_observations` table would give true velocity curves
  and charts instead of a single delta.
- **Lock files / hash-locked installs** (priority: medium). Add `pip-compile --generate-hashes`
  (or uv lock) for the backend and commit `package-lock.json` for the frontend; install with
  `pip install --require-hashes` / `npm ci`.
- **Real source adapters hardening** (priority: medium). Add rate limiting (>=1.5s/host),
  backoff on 429, and disk caching for Google Trends / Reddit per CLAUDE.md network ethics.
- **Pipeline retries + idempotency** (priority: medium). A failed drop should be safely
  re-runnable without double-posting to X.com (dedup by drop id / store the tweet attempt).

## Phase 2+

- **Public storefront + checkout** (priority: low for now). Explicitly out of Phase 1 scope.
- **Auth on the admin dashboard** (priority: high before any non-local deployment). The API is
  currently open behind CORS + trusted-host only.
