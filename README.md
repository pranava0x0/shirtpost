# ShirtPost

Fast-fashion print-on-demand for family-friendly internet trends. **Phase 1** = the
backend trend **Radar**, a human-in-the-loop admin **Studio**, and the automated
Printful + X.com **Factory**. No storefront or checkout yet.

```
backend/    FastAPI + SQLAlchemy — radar, scoring, API, factory pipeline (owns the DB)
frontend/   Next.js 15 (App Router) — internal admin dashboard, thin HTTP client
llms.txt    Machine-readable project map
security.md Supply-chain advisory sweep + mitigations
backlog.md  Deferred work
```

The Next.js app talks to FastAPI over HTTP only — FastAPI is the single owner of the
SQLite database (see [backlog.md](backlog.md) for why Prisma was deferred).

## Backend

```bash
cd backend
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # prod
pip install -r requirements-dev.txt      # + pytest/httpx for tests
cp .env.example .env                      # fill in keys (or leave blank for radar-only)
uvicorn app.main:app --reload --port 8000
```

- `GET /health` — liveness
- `GET /api/trends?limit=100` — trends sorted by Hype Score
- `POST /api/trends/{id}/submit` — `{ "design_copy": "..." }`, fires the Factory (409 if a drop for that trend is already in flight)
- `GET /api/drops` — drops, newest first
- `GET /api/drops/{id}` — one drop (the dashboard polls this while a drop is in flight)
- `POST /api/radar/sweep` — force an immediate radar sweep (the "Refresh radar" button)

Run tests:

```bash
cd backend && pytest
```

The Radar runs on a background interval (`RADAR_POLL_INTERVAL_SECONDS`). With the
default `RADAR_SOURCES=["simulated"]` it populates trends with no network or keys.

## Frontend

```bash
cd frontend
npm install
cp .env.example .env.local                # NEXT_PUBLIC_API_BASE_URL
npm run dev                               # http://localhost:3000
npm run typecheck                         # tsc --noEmit
```

## What works end-to-end today

- Radar → DB → Admin queue → submit → Factory pipeline runs and records status.
- The Factory **fails loud** (drop `status=failed`, `error` surfaced in the UI) until
  Printful + X.com credentials *and* `PRINTFUL_PRINT_FILE_BASE_URL` (SVG hosting) are
  configured. See [backlog.md](backlog.md).

## Security

All secrets load from env (validated by Pydantic / Zod). Versions pinned exact. A
supply-chain sweep gated this scaffold — see [security.md](security.md). Notably:
`next` 15.5.10 / `react` 19.2.4 (React2Shell-patched), `axios` removed entirely, and
`TrustedHostMiddleware` mitigating the Starlette BadHost advisory.
