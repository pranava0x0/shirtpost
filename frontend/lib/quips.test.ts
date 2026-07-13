import { describe, expect, it } from "vitest";

import {
  buildGeneratePrompt,
  buildGenerateSystemPrompt,
  cleanAndFilter,
  FAMILY_BLOCKLIST,
  isCliche,
  parseBatch,
  QuipError,
  sampleAnchors,
  STYLE_ANCHORS,
} from "@/lib/quips";

const OPTS = { blocklist: FAMILY_BLOCKLIST, maxChars: 80, count: 6 };

describe("parseBatch", () => {
  it("pulls a {quips: []} object out of clean JSON", () => {
    expect(parseBatch('{"quips": ["a", "b"]}')).toEqual(["a", "b"]);
  });

  it("tolerates prose and code fences around the JSON", () => {
    const text = 'Here you go:\n```json\n{"quips": ["one"]}\n```';
    expect(parseBatch(text)).toEqual(["one"]);
  });

  it("throws QuipError on no JSON object", () => {
    expect(() => parseBatch("no json here")).toThrow(QuipError);
  });

  it("throws QuipError on the wrong shape", () => {
    expect(() => parseBatch('{"lines": ["a"]}')).toThrow(QuipError);
  });
});

describe("cleanAndFilter", () => {
  it("strips surrounding quotes and whitespace", () => {
    const { kept } = cleanAndFilter(['  "we are so back"  '], OPTS);
    expect(kept).toEqual(["we are so back"]);
  });

  it("dedupes case-insensitively without counting it as a quality drop", () => {
    const { kept, dropped } = cleanAndFilter(["Touch Grass", "touch grass"], OPTS);
    expect(kept).toEqual(["Touch Grass"]);
    expect(dropped).toBe(0);
  });

  it("drops family-unsafe lines and counts them", () => {
    const { kept, dropped } = cleanAndFilter(["nice one", "buy my onlyfans"], OPTS);
    expect(kept).toEqual(["nice one"]);
    expect(dropped).toBe(1);
  });

  it("drops merch clichés and counts them", () => {
    const raw = ["I survived Monday", "coding is my love language", "genuinely funny line"];
    const { kept, dropped } = cleanAndFilter(raw, OPTS);
    expect(kept).toEqual(["genuinely funny line"]);
    expect(dropped).toBe(2);
  });

  it("keeps at most one ...era line per batch", () => {
    const raw = ["in my villain era", "delulu era", "unbothered"];
    const { kept, dropped } = cleanAndFilter(raw, OPTS);
    expect(kept).toEqual(["in my villain era", "unbothered"]);
    expect(dropped).toBe(1); // the second era line
  });

  it("drops candidates containing the term when ipRisk is set", () => {
    const raw = ["Taylor Swift is my therapist", "shake it off, literally"];
    const { kept, dropped } = cleanAndFilter(raw, {
      ...OPTS,
      term: "Taylor Swift",
      ipRisk: true,
    });
    // "is my therapist" isn't in the cliché list; the IP-term drop is what fires.
    expect(kept).toEqual(["shake it off, literally"]);
    expect(dropped).toBe(1);
  });

  it("does NOT drop the term when ipRisk is unset", () => {
    const { kept } = cleanAndFilter(["crashing out again"], {
      ...OPTS,
      term: "crashing out",
    });
    expect(kept).toEqual(["crashing out again"]);
  });

  it("respects the count cap and Infinity keeps all survivors", () => {
    const raw = ["a", "b", "c", "d"];
    expect(cleanAndFilter(raw, { ...OPTS, count: 2 }).kept).toHaveLength(2);
    expect(
      cleanAndFilter(raw, { ...OPTS, count: Number.POSITIVE_INFINITY }).kept,
    ).toHaveLength(4);
  });

  it("drops overlong lines as junk, not as a quality drop", () => {
    const { kept, dropped } = cleanAndFilter(["x".repeat(200), "fits fine"], OPTS);
    expect(kept).toEqual(["fits fine"]);
    expect(dropped).toBe(0);
  });
});

describe("isCliche", () => {
  it("flags known dead formats", () => {
    expect(isCliche("I survived 2026")).toBe(true);
    expect(isCliche("POV: you read this")).toBe(true);
    expect(isCliche("running is my cardio")).toBe(true);
  });

  it("passes a genuinely fresh line", () => {
    expect(isCliche("emotionally load-bearing")).toBe(false);
  });
});

describe("sampleAnchors", () => {
  it("falls back to STYLE_ANCHORS when the hall of fame is empty", () => {
    expect(sampleAnchors([])).toEqual(STYLE_ANCHORS);
  });

  it("prefers hall-of-fame entries, newest-first", () => {
    const hof = ["old line", "mid line", "newest line"];
    expect(sampleAnchors(hof, 2)).toEqual(["newest line", "mid line"]);
  });

  it("filters out empty/overlong entries", () => {
    const hof = ["", "  ", "x".repeat(200), "good"];
    expect(sampleAnchors(hof)).toEqual(["good"]);
  });
});

describe("prompt builders", () => {
  it("system prompt embeds the anchors and bans clichés", () => {
    const sys = buildGenerateSystemPrompt(["banger one"]);
    expect(sys).toContain("banger one");
    expect(sys.toLowerCase()).toContain("i survived");
  });

  it("generate prompt weaves in context and angles when present", () => {
    const p = buildGeneratePrompt({
      term: "crashing out",
      source: "discovered",
      measurement: "shirt_score",
      context: "resurgent on X this week",
      angles: ["deadpan self-diagnosis"],
      count: 12,
    });
    expect(p).toContain("resurgent on X this week");
    expect(p).toContain("deadpan self-diagnosis");
    expect(p).toContain("12");
  });

  it("generate prompt warns off the name when ipRisk is set", () => {
    const p = buildGeneratePrompt({
      term: "Some Celebrity",
      source: "discovered",
      measurement: "shirt_score",
      ipRisk: true,
      count: 12,
    });
    expect(p).toContain("IP WARNING");
    expect(p).toContain("Some Celebrity");
  });
});
