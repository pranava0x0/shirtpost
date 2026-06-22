# ShirtPost — Phase 1 status / resume point

_Last updated: 2026-06-19_

## Where things stand

Phase 1 scaffold is **complete and verified end-to-end**, committed on branch
`phase-1-radar-factory` and delivered as an **open PR against `main`** along
with a GitHub Actions CI workflow (`.github/workflows/ci.yml`). `main` still
holds only the initial 4 docs until the PR merges.

## Verified (all green, 2026-06-19)

- Frontend: `npm install` (361 pkgs), `tsc --noEmit`, `next build` — all pass.
- Backend: deps install on CPython 3.12, `pytest` = **30 passed**.
- E2E smoke: radar sweep (simulated source) → 5 trends → `GET /api/trends`
  sorted by Hype Score → `POST submit` creates a drop; Factory **fails loud**
  with the exact missing-config reason and records it on the drop.

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

- **Merge the PR** once CI is green. The branch carries the scaffold + CI; the
  repo has no AI co-author / footer per CLAUDE.md.

## Next-up gaps (full list in backlog.md)

1. **Factory can't fully complete** until `PRINTFUL_PRINT_FILE_BASE_URL` (SVG
   hosting) + Printful/X creds exist. Until then, submissions fail loud by
   design. [high]
2. **No auth on the admin API** — required before any non-local deploy. [high]
3. FastAPI/Starlette BadHost upgrade once the patched line resolves
   (TrustedHostMiddleware is the interim mitigation). [high]
4. Trend observation-history table — the model stores only latest + prev volume
   per trend; an append-only observations table would give true velocity curves
   instead of a single delta. [medium]
