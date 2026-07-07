// Server-side quip generation logic. Lives in the Next.js dashboard (not the
// FastAPI backend) so the Anthropic key stays with the dashboard server and never
// touches the public admin API. Pure functions here; the Claude call is in
// app/api/quips/route.ts. See backlog.md "Keep ANTHROPIC_API_KEY off the backend".

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

// The funniest simulated seeds, reused as house-voice anchors so the model
// matches the tone (short, current, meme-literate). Mirror backend radar/sources.
const STYLE_ANCHORS = [
  "we are so back",
  "delulu is the solulu",
  "it's giving unemployed",
  "in my villain era",
];

export const SYSTEM_PROMPT =
  "You write merch copy: short, funny one-liners for t-shirts and stickers. " +
  "You are handed a phrase or topic that is trending right now and must riff on " +
  "it into banger one-liners someone would actually wear.\n\n" +
  "Rules:\n" +
  "- Punchy. Most lines are 2-6 words; never more than ~8. A shirt is not a " +
  "paragraph.\n" +
  "- Actually funny: play on the trend, subvert it, or deadpan it. No corny " +
  "puns, no hashtags, no emoji, no quotation marks around the line.\n" +
  "- Wearable: self-deprecating, absurd, or relatable beats mean-spirited. " +
  "Keep it family-safe — nothing sexual, hateful, or violent.\n" +
  "- Vary the angle across the batch so the human has a real choice; don't " +
  "give eight rewrites of the same joke.\n" +
  "- Match this house voice (meme-literate, lowercase-casual): " +
  STYLE_ANCHORS.join("; ") +
  ".\n\n" +
  'Return ONLY a JSON object of the form {"quips": ["line one", "line two"]} ' +
  "with no prose, preamble, or code fences.";

export function buildUserPrompt(
  term: string,
  source: string,
  measurement: string,
  count: number,
): string {
  return (
    `Trending topic: ${JSON.stringify(term)}\n` +
    `(surfaced from ${source}, measured as ${measurement})\n\n` +
    `Write ${count} distinct funny one-liner shirt slogans riffing on it.`
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

export function cleanAndFilter(
  quips: string[],
  opts: { blocklist: string[]; maxChars: number; count: number },
): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of quips) {
    // strip whitespace + surrounding quotes, then re-trim
    const line = (raw ?? "").trim().replace(/^["']+|["']+$/g, "").trim();
    if (!line || line.length > opts.maxChars) continue;
    if (!isFamilySafe(line, opts.blocklist)) continue;
    const key = line.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(line);
    if (out.length >= opts.count) break;
  }
  return out;
}
