// Server-only: the "hall of fame" is the operator's actually-shipped design copy,
// used as few-shot house-voice anchors for quip generation. Every submitted drop
// appends here (best-effort), so the voice becomes what the owner really picks
// rather than the frozen 2023-era seeds. Owner can hand-add/prune the JSON.
// See docs/TRENDS-DISCOVERY-SPEC.md Part B #4.

import { promises as fs } from "node:fs";
import path from "node:path";

// Relative to the Next.js server CWD (frontend/), so this lands at
// repo-root/data/copy/hall-of-fame.json — same data/ tree as the discovered
// trends. Override with HALL_OF_FAME_PATH.
const HALL_OF_FAME_PATH =
  process.env.HALL_OF_FAME_PATH ??
  path.join(process.cwd(), "..", "data", "copy", "hall-of-fame.json");

// Keep the file bounded — the newest picks are the freshest voice. Display/use
// samples from the tail; the file never grows without limit.
const MAX_ENTRIES = 200;
const MAX_LINE_CHARS = 80;

/** Read the hall of fame as a string[]. Missing file or bad JSON => [] (the
 *  generator falls back to the cold-start STYLE_ANCHORS). Never throws. */
export async function readHallOfFame(): Promise<string[]> {
  let body: string;
  try {
    body = await fs.readFile(HALL_OF_FAME_PATH, "utf-8");
  } catch {
    return []; // not created yet — cold start
  }
  try {
    const data: unknown = JSON.parse(body);
    if (!Array.isArray(data)) return [];
    return data.filter((x): x is string => typeof x === "string");
  } catch {
    console.warn(`hall-of-fame: ${HALL_OF_FAME_PATH} is not valid JSON — ignoring`);
    return [];
  }
}

/** Append a shipped line, deduped case-insensitively, bounded to MAX_ENTRIES.
 *  Best-effort: a write failure is logged, not thrown (it must never block the
 *  submit that triggered it). */
export async function appendHallOfFame(copy: string): Promise<void> {
  const line = copy.trim();
  if (!line || line.length > MAX_LINE_CHARS) return;
  const current = await readHallOfFame();
  if (current.some((c) => c.toLowerCase() === line.toLowerCase())) return; // already in
  const next = [...current, line].slice(-MAX_ENTRIES);
  try {
    await fs.mkdir(path.dirname(HALL_OF_FAME_PATH), { recursive: true });
    await fs.writeFile(HALL_OF_FAME_PATH, `${JSON.stringify(next, null, 2)}\n`, "utf-8");
  } catch (e) {
    console.warn(
      `hall-of-fame: could not append to ${HALL_OF_FAME_PATH}: ${
        e instanceof Error ? e.message : "write error"
      }`,
    );
  }
}
