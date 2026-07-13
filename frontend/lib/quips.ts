// Server-side quip generation logic. Lives in the Next.js dashboard (not the
// FastAPI backend) so the Anthropic key stays with the dashboard server and never
// touches the public admin API. Pure functions here; the two Claude calls (a
// Sonnet generate stage + a Haiku judge stage) are in app/api/quips/route.ts.
// See backlog.md "Keep ANTHROPIC_API_KEY off the backend" and
// docs/TRENDS-DISCOVERY-SPEC.md Part B.

import { z } from "zod";

// Mirrors the backend's family-safe gate (app/config.py `family_blocklist`). Kept
// in sync by hand across the language boundary; a drift only ever over-blocks
// generated copy, never lets more through. Substring match on purpose — a safety
// filter over-blocks ("Pornhub" must be caught, which a word-boundary match misses).
export const FAMILY_BLOCKLIST = [
  "porn",
  "pornographic",
  "nsfw",
  "xxx",
  "nude",
  "onlyfans",
  "rape",
  "massacre",
  "genocide",
  "terrorist attack",
  "mass shooting",
  "suicide",
  "beheading",
];

export function isFamilySafe(text: string, blocklist = FAMILY_BLOCKLIST): boolean {
  const low = text.toLowerCase();
  return !blocklist.some((bad) => low.includes(bad));
}

// LLM shirt humor converges on a handful of dead formats. Kill them so the batch
// is fresh, mirroring the family gate's pattern. Same over-block bias: dropping a
// borderline line is cheaper than shipping the 10,000th "I survived X" tee.
export const CLICHE_PATTERNS: RegExp[] = [
  /^i survived\b/i,
  /love language/i,
  /^keep calm\b/i,
  /^pov:/i,
  /is my (spirit animal|cardio|therapy)/i,
  /but first,? coffee/i,
  /\badulting\b/i,
];

// "...era" is not banned outright (it's still house voice) but capped at one per
// batch so the picks don't all read as the same joke.
const ERA_PATTERN = /\bera\b/i;

export function isCliche(line: string): boolean {
  return CLICHE_PATTERNS.some((re) => re.test(line));
}

// The four comedic angles Stage 1 spreads candidates across, so the human gets a
// real choice instead of eight rewrites of one joke.
export const COMEDIC_ANGLES = [
  "deadpan literalism — state the obvious flatly, no wink",
  "self-deprecating confession — make yourself the punchline",
  "absurdist escalation — take it one ridiculous step too far",
  "hyper-specific niche mashup — collide the trend with an unrelated subculture",
];

// Cold-start house voice used only when the hall of fame is empty. Once the
// operator ships real drops, data/copy/hall-of-fame.json supplies the anchors and
// these fall away (see route.ts + sampleAnchors).
export const STYLE_ANCHORS = [
  "we are so back",
  "delulu is the solulu",
  "it's giving unemployed",
  "in my villain era",
];

/** Pick up to `n` anchors from the hall of fame, falling back to the cold-start
 *  set when it's empty. Newest-first (the file appends), so recent taste wins. */
export function sampleAnchors(
  hallOfFame: string[],
  n = 5,
  fallback = STYLE_ANCHORS,
): string[] {
  const cleaned = hallOfFame
    .map((s) => (s ?? "").trim())
    .filter((s) => s.length > 0 && s.length <= 80);
  const pool = cleaned.length > 0 ? cleaned.slice().reverse() : fallback;
  return pool.slice(0, n);
}

export function buildGenerateSystemPrompt(anchors: string[]): string {
  return (
    "You write merch copy: short, funny one-liners for t-shirts and stickers. " +
    "You are handed a phrase or topic trending right now and must riff on it into " +
    "banger one-liners someone would actually wear.\n\n" +
    "Rules:\n" +
    "- Punchy. Most lines are 2-6 words; never more than ~8. A shirt is not a " +
    "paragraph.\n" +
    "- Actually funny: play on the trend, subvert it, or deadpan it. No corny " +
    "puns, no hashtags, no emoji, no quotation marks around the line.\n" +
    "- Wearable: self-deprecating, absurd, or relatable beats mean-spirited. " +
    "Family-safe — nothing sexual, hateful, or violent.\n" +
    "- NEVER print a real person's name, brand, franchise, or song lyric — those " +
    "are legally unprintable. Riff around the moment, not the trademarked words.\n" +
    "- Avoid dead merch clichés: no 'I survived X', 'X is my love language', " +
    "'POV:', 'keep calm', 'but first coffee', 'adulting', 'X is my cardio/therapy'.\n" +
    "- Spread the batch across these comedic angles so the human has real choice:\n" +
    COMEDIC_ANGLES.map((a) => `    • ${a}`).join("\n") +
    "\n- Match this house voice (meme-literate, lowercase-casual): " +
    anchors.join("; ") +
    ".\n\n" +
    'Return ONLY a JSON object of the form {"quips": ["line one", "line two"]} ' +
    "with no prose, preamble, or code fences."
  );
}

export const JUDGE_SYSTEM_PROMPT =
  "You are a ruthless merch editor. You are given candidate t-shirt one-liners " +
  "for a trend and must keep only the ones that would actually sell. Score each " +
  "on funny, wearable, and fresh (not a tired cliché), then return the very best, " +
  "most DISTINCT lines — never two rewrites of the same joke. Drop anything corny, " +
  "mean, off-voice, or that names a real person/brand/lyric.\n\n" +
  'Return ONLY a JSON object of the form {"quips": ["best line", "next best"]} ' +
  "ordered best-first, with no prose, preamble, or code fences.";

export function buildGeneratePrompt(opts: {
  term: string;
  source: string;
  measurement: string;
  context?: string | null;
  angles?: string[] | null;
  ipRisk?: boolean;
  count: number;
}): string {
  const lines = [
    `Trending topic: ${JSON.stringify(opts.term)}`,
    `(surfaced from ${opts.source}, measured as ${opts.measurement})`,
  ];
  if (opts.context) {
    lines.push(`Why it's trending: ${opts.context}`);
  }
  if (opts.angles && opts.angles.length > 0) {
    lines.push(`Angle hints to lean on: ${opts.angles.join("; ")}`);
  }
  if (opts.ipRisk) {
    lines.push(
      "IP WARNING: this trend is built on a real person/brand/franchise/lyric. " +
        `Do NOT put ${JSON.stringify(opts.term)} (or any real name) in the copy — ` +
        "riff on the vibe of the moment instead.",
    );
  }
  lines.push(
    "",
    `Write ${opts.count} distinct funny one-liner shirt slogans riffing on it, ` +
      "spread across the four comedic angles.",
  );
  return lines.join("\n");
}

export function buildJudgePrompt(term: string, candidates: string[], count: number): string {
  const numbered = candidates.map((c, i) => `${i + 1}. ${c}`).join("\n");
  return (
    `Trend: ${JSON.stringify(term)}\n\n` +
    `Candidates:\n${numbered}\n\n` +
    `Return the ${count} best, most distinct lines, best-first.`
  );
}

export class QuipError extends Error {}

const batchSchema = z.object({ quips: z.array(z.string()) });

// Pull the first {...} object out of the model's reply, tolerating stray prose or
// ```json fences even though the prompt asks for none (belt and suspenders).
const JSON_OBJECT = /\{[\s\S]*\}/;

export function parseBatch(text: string): string[] {
  const match = text.match(JSON_OBJECT);
  if (!match) {
    throw new QuipError(
      `model returned no JSON object (got ${JSON.stringify(text.slice(0, 120))})`,
    );
  }
  let data: unknown;
  try {
    data = JSON.parse(match[0]);
  } catch (e) {
    throw new QuipError(
      `model returned malformed quip JSON: ${e instanceof Error ? e.message : "parse error"}`,
    );
  }
  const parsed = batchSchema.safeParse(data);
  if (!parsed.success) {
    throw new QuipError("model returned JSON that isn't a {quips: string[]} batch");
  }
  return parsed.data.quips;
}

export type FilterResult = { kept: string[]; dropped: number };

/** Clean, gate, and dedupe candidate lines. Returns the survivors plus a count of
 *  quality drops (family/cliché/IP/era-cap) so the dashboard can show that the
 *  filter is working. `count` caps the survivors; pass Infinity to keep all.
 *
 *  When `ipRisk` is set, any line still containing the trend term is dropped —
 *  the belt to the prompt's suspenders (riff around the name, never print it). */
export function cleanAndFilter(
  quips: string[],
  opts: {
    blocklist: string[];
    maxChars: number;
    count: number;
    term?: string;
    ipRisk?: boolean;
  },
): FilterResult {
  const seen = new Set<string>();
  const kept: string[] = [];
  // IP belt: drop a line containing the whole term OR any significant word of it,
  // so "Taylor Swift" also catches "swiftie"/"taylor's version" (the prompt is the
  // primary guard; this is the backstop). Trimmed so surrounding whitespace can't
  // defeat the match. Short (<4-char) tokens are skipped to avoid false positives.
  const term = opts.ipRisk && opts.term ? opts.term.trim().toLowerCase() : "";
  const ipNeedles = term
    ? [term, ...term.split(/\s+/).filter((t) => t.length >= 4)]
    : [];
  let eraUsed = false;
  let dropped = 0;
  for (const raw of quips) {
    // strip whitespace + surrounding quotes, then re-trim
    const line = (raw ?? "").trim().replace(/^["']+|["']+$/g, "").trim();
    if (!line || line.length > opts.maxChars) continue; // junk, not a "quality" drop
    const key = line.toLowerCase();
    if (seen.has(key)) continue; // duplicate, not a quality drop
    // Record the decision now so a repeated cliché/unsafe line is only *counted*
    // once (dropped is the auditable quality signal, not a raw occurrence count).
    seen.add(key);
    if (!isFamilySafe(line, opts.blocklist)) {
      dropped++;
      continue;
    }
    if (isCliche(line)) {
      dropped++;
      continue;
    }
    if (ipNeedles.some((needle) => key.includes(needle))) {
      dropped++;
      continue;
    }
    if (ERA_PATTERN.test(line)) {
      if (eraUsed) {
        dropped++;
        continue;
      }
      eraUsed = true;
    }
    kept.push(line);
    if (kept.length >= opts.count) break;
  }
  return { kept, dropped };
}
