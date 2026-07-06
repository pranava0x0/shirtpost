# Session history — Phase 1.5 → 2/3/4 build-out + review

_2026-07-05 → 2026-07-06. A record of how this branch was built: the agents and
tools used, the decisions and why, and the commit arc. For "what's the state / how
do I resume," see [STATUS.md](STATUS.md); for "what's the plan," [PLAN.md](PLAN.md);
for bugs, [../issues.md](../issues.md)._

## What shipped

One branch / one PR (`claude/elastic-thompson-c3d446`, PR #3) implementing **every
code-doable, $0, no-account item** from [PLAN.md](PLAN.md), then a code-review pass.
~40 files, backend **98 tests** (from 41), frontend typecheck/lint clean, CI green.

## Arc (commit sequence)

1. **Phase 1.5** — observation history, idempotent retry, per-source lanes, garment color.
2. **PLAN.md brought onto the branch** — the real plan lived on another branch (`claude/nifty-einstein-839581`); folded in.
3. **Phase 2A #1** — rasterize print files to PNG (Printful rejects SVG).
4. **Phase 2B** — free X Web-Intent broadcast (X has no free API tier) + monthly budget guard.
5. **Phase 3 #2/#5** — Wikipedia real source + family-safe filter, Reddit dropped (ToS).
6. **Phase 2A #2** — print-file storage backends (local + github_pages).
7. **Phase 4 #4** — hash-locked installs; **fixed** cross-platform lock (`--universal`) after CI caught it.
8. **Code review** — independent agents + self-review → fixes with regression tests → this doc set.

## Agents spawned

- **`pr-review-toolkit:code-reviewer`** (background) — correctness + CLAUDE.md adherence over the backend diff. Headline find: the **budget guard under-counted** (filtered on `published_at`, not the `x_tweet_id` spend signal). Confirmed the resume/no-double-post design and the observation write path as correct.
- **`pr-review-toolkit:silent-failure-hunter`** (background) — error handling. Headline find: **`_wait_until_live` swallowed every status/error** so a broken Pages deploy was an opaque 2-min timeout; also the Wikipedia fetch-vs-empty conflation and the missing connection-error backoff.
- Both ran read-only against `git diff main...HEAD`, so editing continued in parallel. Every finding was **evaluated before applying** — one suggestion (word-boundary family matching) was rejected because it would weaken a safety filter; documented instead.

## Tools / skills used

- **Browser preview** (`preview_start` / `preview_fill` / `preview_click` / `preview_eval` / `preview_screenshot` / `preview_network` / `preview_resize`) — verified the Studio end-to-end in dry-run **and** real mode: lanes, sparklines, meters, submit→fail-loud→retry (same drop, no duplicate), dry-run publish with a served PNG, the "Post to X" intent link, and 375px mobile. Text-based checks (snapshot/eval/inspect) preferred over screenshots for asserting values.
- **`WebFetch`** — the supply-chain advisory sweep before adding `pillow` (recorded in [../security.md](../security.md)).
- **Bash / gh / git** — commits (plain-voice, no AI footer per CLAUDE.md), PR create/edit, `gh pr checks --watch` for CI. **uv** for the Python 3.12 venv + hash-lock compile; **pytest** as the eval loop.
- **Live source validation** — one real Wikimedia API call to confirm the parser against the real payload before trusting it.
- **Memory** — saved that "implement the plan" = the full doable set (don't ask to narrow), and that the plan lives at `docs/PLAN.md` (possibly on a sibling branch).

## Key decisions & why

| Decision | Why |
|---|---|
| PNG rasterization via **Pillow bundled font**, not cairosvg/resvg or a vendored TTF | No system `cairo`/`pango` and no committed binary — one pip dep; boring-tech + CLAUDE.md "no large binaries." |
| Binary-search the wrap "largest prefix that fits" | A per-char scan was O(n²) — 38s → 1.5s on the render tests. |
| **Intent** broadcast default, api behind a flag | X has no free tier ($0.20/post w/ URL); Web Intent is $0, no keys, fits human-in-the-loop. |
| **Substring** family filter, not word-boundary | A safety gate must over-block; `\bporn\b` misses "Pornhub". Removed the one over-broad word ("execution") and made drops auditable instead. |
| Storage `local` **fails loud on localhost** | A localhost URL is unreachable by Printful — better to fail with the reason than hand Printful a dead URL. |
| Deferred (not built): Printful account, Quick Store, Trends alpha, deploy/auth, R2, Phase 5 | Genuinely human-gated or ahead of their trigger ("no future-proofing without a present user"). |

## Gotchas hit (see issues.md for the full list)

- Cross-platform hash-lock omitted `greenlet` → CI Linux `--require-hashes` failed; fixed with `uv pip compile --universal`.
- A `GitHub Actions` workflow-edit security hook fired on `ci.yml` edits — benign here (static `run:`, no untrusted `${{ github.event.* }}`); retried through it.
