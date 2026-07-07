# ShirtPost — Phase 1 status / resume point

_Last updated: 2026-07-05_

## Where things stand

Phase 1 scaffold merged to `main` (PRs #1, #2). This branch carries **Phase 1.5 +
the code-doable, $0 parts of Phase 2A/2B** from [PLAN.md](PLAN.md): observation
history, idempotent retry, cross-source lanes, garment-color safety, **PNG
rasterization** (Printful rejects SVG), and **free X Web-Intent broadcast** (X has
no free API tier). Delivered as a PR against `main`. Remaining plan work is
human-gated or waits on its trigger — see [PLAN.md](PLAN.md) § Progress.

## Verified (all green, 2026-07-06)

- Backend: `pytest` = **98 passed** on CPython 3.12 (was 30 at scaffold); the
  Wikipedia parser is also live-validated against the real API.
- Frontend: `tsc --noEmit` clean, `next lint` clean, `next build` passes.
- E2E in the browser (dry-run + real-mode): per-source lanes render with inline
  hype sparklines and within-source meters; `submit` → **fails loud** with the
  exact missing-config reason → **Retry drop** re-runs the *same* drop (no
  duplicate) and, in dry-run, carries it to `published`. The Factory now renders
  a real **transparent PNG** (served `image/png`, RGBA 1800×2400) and a published
  drop shows a **"Post to X"** intent button with a valid, URL-encoded link.
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

## Merch humor: LLM quip generator (this branch)

- **Funny one-liner copy from trends** — the design copy was operator-pasted
  "from your LLM"; nothing funny was proposed. The Studio "Generate ideas" button
  asks Claude for a batch of banger shirt slogans riffed on the trend, runs each
  through the Radar's family-safe gate, dedup + length-caps, and renders them as
  pickable chips → fills the copy box (model proposes, human picks). Seeds in
  `radar/sources.py` freshened toward current, wearable bangers (kept "we are so
  back" / "delulu is the solulu").
- **The key lives on the dashboard, not the backend.** Generation runs in a
  Next.js server route (`frontend/app/api/quips/route.ts`, `@anthropic-ai/sdk`);
  the browser POSTs the trend fields it already has to that same-origin route.
  `ANTHROPIC_API_KEY` is read there only (server env — **never** `NEXT_PUBLIC_*`),
  so it never touches the public FastAPI admin API. Fails loud (503) with no key;
  Haiku by default (`QUIP_MODEL` → Sonnet for wittier). The Python `anthropic`
  dep and the old `/quips` FastAPI endpoint were removed. Pure filter/parse logic
  lives in `frontend/lib/quips.ts`. Advisory-swept: `@anthropic-ai/sdk==0.110.0`
  (+ a `zod` bump to `3.25.76` for its peer range), see `security.md`.

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

## Phase 2A/2B/3/4 ($0, code-doable PLAN.md items — this branch)

- **PNG rasterization** (2A #1) — research found Printful rejects SVG.
  `factory/render.py` (Pillow, bundled scalable font — no system cairo, no
  vendored binary) renders a transparent print-ready PNG; the SVG stays as the
  source. `pillow==12.3.0` (advisory-swept).
- **Print-file storage** (2A #2) — `factory/storage.py`: `PRINT_FILE_STORAGE`
  = `local` (serve from this backend; fails loud on localhost) or `github_pages`
  (push to a public artifacts repo + poll until live, idempotent). R2 deferred.
- **Free X broadcast + budget guard** (2B) — X has no free API tier since 2026-02.
  `X_BROADCAST_MODE=intent` (default) generates a prefilled `x.com/intent/post`
  URL the operator clicks — $0, no keys. `=api` auto-posts, logs an estimated
  per-post cost, and honors `X_MONTHLY_BUDGET_USD` (fail-loud). "Post to X" button.
- **Real source + family filter** (3 #2/#5) — `wikipedia` most-viewed (open API,
  ToS-clean); Reddit dropped (commercial ToS); a keyword blocklist drops unsafe
  trends before the queue.
- **Hash-locked installs** (4 #4) — `requirements*.lock` + CI `--require-hashes`.

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

- **Merge the PR** once CI is green. No AI co-author / footer per CLAUDE.md.

## Next-up gaps (full list in backlog.md)

1. **Real-mode Printful needs a human step, not code**: a free Printful account +
   PNG hosting (`PRINT_FILE_STORAGE=github_pages` → create the artifacts repo + a
   token, or deploy so `local` is publicly reachable). The pipeline + storage code
   are done; submissions fail loud until hosting is reachable. [high]
2. **No auth on the admin API** — required before any non-local deploy. A
   meaningful refactor (route the dashboard through Next.js server-side so the
   token stays server-only); deferred while not deploying. [high]
3. FastAPI/Starlette BadHost upgrade — blocked: `starlette >= 1.0.1` needs a
   coordinated fastapi upgrade (TrustedHostMiddleware is the interim mitigation). [high]
4. Storefront URL + conversion path before any real X posting — the code path
   (`STORE_BASE_URL`) exists; the broadcast stays a teaser until a drop is buyable. [high]
