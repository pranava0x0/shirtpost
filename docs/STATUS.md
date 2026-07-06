# ShirtPost — Phase 1 status / resume point

_Last updated: 2026-07-05_

## Where things stand

Phase 1 scaffold merged to `main` (PRs #1, #2). This branch adds **Phase 1.5** —
four self-contained backlog items (observation history, idempotent retry,
cross-source lanes, garment-color safety), verified end-to-end and delivered as
a PR against `main`.

## Verified (all green, 2026-07-05)

- Backend: `pytest` = **67 passed** on CPython 3.12 (was 30 at scaffold).
- Frontend: `tsc --noEmit` clean, `next lint` clean, `next build` passes.
- E2E in the browser (dry-run + real-mode): per-source lanes render with inline
  hype sparklines and within-source meters; `submit` → **fails loud** with the
  exact missing-config reason → **Retry drop** re-runs the *same* drop (no
  duplicate) and, in dry-run, carries it to `published` with a served mockup.
  Mobile checked at 375px; no console errors.

## Improvements landed on the PR (second batch)

- **X media → v2** — v1.1 media upload was deprecated 2025-06-09; client now
  targets `POST /2/media/upload` with defensive id parsing.
- **Radar network hygiene** — `radar/fetch.py`: disk cache + per-host rate
  limit (>=1.5s) + 429 backoff.
- **Closed-loop Studio** — `GET /api/drops/{id}` + dashboard auto-polls
  in-flight drops; `POST /api/radar/sweep` + a "Refresh radar" button.
- **Safety** — 409 guard against double-firing a trend with an in-flight drop.
- **Hype Score fix** — found by *running* it: the spec's `velocity × volume`
  zeroed every score on the second identical sweep. Rebased on a volume base
  with a capped velocity boost; verified live to hold across re-sweeps.

## Phase 1.5 improvements (this branch)

- **Trend observation history** — append-only `trend_observations` (one snapshot
  per sweep). `GET /api/trends/{id}/observations` serves it; each `/trends` row
  carries a `spark` series (one windowed query for the page) → inline sparkline.
- **Idempotent Factory + retry** — each external step commits as it lands and is
  skipped on re-run; the tweet id commits *before* the published transition, so a
  crash-after-post can't double-tweet. `POST /api/drops/{id}/retry` + a UI button
  reserve the in-flight slot and resume.
- **Cross-source lanes** — the Studio groups trends per source; `normalized_hype`
  (0..1 within a source) is the honest within-lane scale. No global ranking across
  incomparable measurements.
- **Garment-color safety** — ink derived from `PRINTFUL_GARMENT_COLOR` for
  contrast; never white-on-white on a light garment.

## Dev environment already provisioned (don't redo)

- `backend/.venv` — created by **uv** with **Python 3.12.13**. The system
  Python is 3.9.6, which is **too old to run the backend** (union-type
  annotations need 3.10+). `uv` was installed to `~/.local/bin`.
- `frontend/node_modules` — installed (Node 22, npm 10).

### Resume commands

```bash
# backend
export PATH="$HOME/.local/bin:$PATH"        # uv lives here
cd backend && source .venv/bin/activate
uv run pytest                                # or: pytest
uvicorn app.main:app --reload --port 8000

# frontend
cd frontend
cp .env.example .env.local                   # NEXT_PUBLIC_API_BASE_URL
npm run dev                                   # http://localhost:3000
```

## Open decision

- **Merge the Phase 1.5 PR** once CI is green. No AI co-author / footer per CLAUDE.md.

## Next-up gaps (full list in backlog.md)

1. **Factory can't fully complete** until `PRINTFUL_PRINT_FILE_BASE_URL` (SVG
   hosting) + Printful/X creds exist. Until then, submissions fail loud by
   design. [high]
2. **No auth on the admin API** — required before any non-local deploy. A
   meaningful refactor (route the dashboard through Next.js server-side so the
   token stays server-only); deferred while not deploying. [high]
3. FastAPI/Starlette BadHost upgrade — blocked: `starlette >= 1.0.1` needs a
   coordinated fastapi upgrade (TrustedHostMiddleware is the interim mitigation). [high]
4. Storefront URL + conversion path before any real X posting — the code path
   (`STORE_BASE_URL`) exists; the broadcast stays a teaser until a drop is buyable. [high]
