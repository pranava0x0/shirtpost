# Security Sweep Log

Source: https://pranava0x0.github.io/vibe-coding-security/llms-ctx.txt
Refresh if > 7 days old, or before any new dependency add / scaffold / CDN asset / GitHub Action / fetched install script.

## Sweep 2026-07-12 — vitest test harness (v2 copy-gen work)

Triggered by: adding `vitest` as a frontend devDependency for `quips.test.ts`
(the deferred vitest harness, TRENDS-DISCOVERY-SPEC Part B). Advisory index
re-fetched 2026-07-12.

- **`vitest`** — NOT named in the index. Cleared. Pinned exact, lockfile-installed.
- The only Vite-family entry is "Vite dev-server WebSocket arbitrary file read"
  (advisory 2026-04-06) — it concerns an *exposed* `vite` dev server, not the
  test runner, which we never expose. No action beyond pinning a current version.
- No other index matches; prior notes below still stand.

## Sweep 2026-07-06 — quip generation moved to the Next.js server

Triggered by: moving quip generation off FastAPI to a Next.js server route so the
Anthropic key lives only with the dashboard server (owner constraint), which adds
`@anthropic-ai/sdk` to the frontend. Advisory index re-checked 2026-07-06.

- **`@anthropic-ai/sdk==0.110.0`** — NOT named in the index. Cleared for use.
  Pinned exact (`--save-exact`, no `^`), lockfile-installed. Removed the Python
  `anthropic` dep from the backend in the same change (key no longer on FastAPI).
- Key read as `ANTHROPIC_API_KEY` (server env, **never** `NEXT_PUBLIC_*` — that
  would ship it to the browser) inside the route only; not in the client zod env.
- No other index matches; the Starlette BadHost note below still stands.

## Sweep 2026-07-06 — LLM quip generator dependency (SUPERSEDED — never shipped)

> **Not in the shipped tree.** This first pass added the Python `anthropic` dep to
> the backend; it was reverted within the same branch (commit 2) in favor of the
> Next.js `@anthropic-ai/sdk` route above, to keep the key off FastAPI. Kept for an
> honest audit trail: the sweep below was real (the Python package IS clean), but
> `backend/requirements.txt` ships with **no** `anthropic` dep. Don't re-add it.

Triggered by: adding the official `anthropic` SDK to `backend/requirements.txt` to
generate funny one-liner shirt copy from trends. Advisory index fetched 2026-07-06.

- **`anthropic==0.116.0`** — NOT named in the index. Cleared for use (but reverted,
  see above). Pulls `httpx` (already cleared below) + small typed-client deps.
- `httpx`, `pydantic` re-checked against the index — still not named. No new matches.
- Key stays env-only (`ANTHROPIC_API_KEY`), never logged; the generator makes no
  network call at import time and fails loud (503) when the key is absent.

## Sweep 2026-07-05 — Phase 2A raster dependency

Triggered by: adding `pillow` to `backend/requirements.txt` for SVG→PNG rasterization
(Printful rejects SVG). Advisory index fetched 2026-07-06.

- **`pillow==12.3.0`** — NOT named in the index. Cleared for use. Pinned exact. Uses
  Pillow's bundled scalable default font, so no system `cairo`/`pango` and no vendored
  font binary enter the tree (keeps the "no committed binaries" rule intact).
- Also re-checked (still clean, unchanged from below): the Starlette **BadHost**
  (CVE-2026-48710) remains the only stack-relevant advisory; `TrustedHostMiddleware`
  mitigation stays. No new matches against the existing manifest.
- Not adding `boto3`/`cairosvg`/`resvg` this pass (R2 backend deferred; Pillow chosen
  over cairosvg to avoid system libs). Re-sweep before adding any of them.

## Sweep 2026-06-19 — Phase 1 scaffold

Triggered by: new-project scaffold + initial dependency manifests (`requirements.txt`, `package.json`).

### Matches against our intended stack

| Package | Advisory | Affected | Mitigation taken |
|---|---|---|---|
| `next` | React2Shell (CVE-2025-55182) + Next.js 13-CVE RSC cluster (unauth RCE, SSRF) | `<15.5.10` in the 15.x line; `<16.1.5` in 16.x | Pinned `next` to a patched 15.x release; App Router only. |
| `react` / `react-dom` | React2Shell CVE-2025-55182 — insecure RSC deserialization → RCE | `<19.2.4` | Pinned `react`/`react-dom` to patched 19.2.4. |
| `axios` | CVE-2026-34841 — malicious versions ship a RAT dropper | `1.14.1`, `0.30.4` | Removed from the stack. Frontend uses native `fetch`. |
| `fastapi` / `starlette` | CVE-2026-48710 "BadHost" — Host-header auth bypass via `request.url` | `starlette <1.0.1` (FastAPI downstream) | Pin `starlette>=1.0.1`; add `TrustedHostMiddleware` with an explicit allowlist as defense-in-depth. Verify `pip install` resolves starlette to the patched line. |

### Checked, NOT named in the index (cleared for use)

pydantic, pydantic-settings, SQLAlchemy, beautifulsoup4, feedparser, httpx, uvicorn, python-dotenv,
prisma, zod, typescript, tailwindcss.

### Standing notes

- No `axios` anywhere in this repo. Re-flag if a transitive dep pulls it (`@usebruno/cli`, `@usebruno/*` chains were compromised via axios).
- All versions pinned exact (`==` / no `^` `~`) per CLAUDE.md supply-chain hardening.
- Re-run this sweep before the next dependency add or upgrade.

### GitHub Actions (reused sweep 2026-06-19)

Adding `.github/workflows/ci.yml` is a supply-chain trigger; reused the same-day sweep above.

- **Avoided** flagged actions: `aquasecurity/trivy-action` (75/76 tags backdoored, TeamPCP),
  `anthropics/claude-code-action` `<v1.0.94` (bot-bypass), `comment-and-control` (PR/issue injection).
- **Used** only first-party actions, each pinned to a full commit SHA + version comment, with a
  per-job `permissions: contents: read` (least privilege):
  - `actions/checkout@9c091bb…` # v7.0.0
  - `actions/setup-node@48b55a0…` # v6.4.0
  - `astral-sh/setup-uv@fac544c…` # v8.2.0
- Re-pin with `gh api repos/<owner>/<repo>/commits/<tag> --jq .sha`.
