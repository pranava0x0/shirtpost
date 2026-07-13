import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

// The module captures HALL_OF_FAME_PATH at eval time, so set it BEFORE importing.
// A dynamic import (not a hoisted static one) runs after this assignment.
const dir = mkdtempSync(join(tmpdir(), "hof-"));
const file = join(dir, "hall-of-fame.json");
process.env.HALL_OF_FAME_PATH = file;

const { readHallOfFame, appendHallOfFame } = await import("@/lib/hallOfFame");

beforeEach(() => {
  rmSync(file, { force: true });
});

describe("readHallOfFame", () => {
  it("returns [] when the file does not exist", async () => {
    expect(await readHallOfFame()).toEqual([]);
  });

  it("returns [] on malformed JSON (never throws)", async () => {
    writeFileSync(file, "{ not json");
    expect(await readHallOfFame()).toEqual([]);
  });

  it("returns [] when the JSON is not an array", async () => {
    writeFileSync(file, '{"a": 1}');
    expect(await readHallOfFame()).toEqual([]);
  });

  it("filters non-string entries", async () => {
    writeFileSync(file, '["good", 42, null, "also good"]');
    expect(await readHallOfFame()).toEqual(["good", "also good"]);
  });
});

describe("appendHallOfFame", () => {
  it("appends a line and reads it back", async () => {
    await appendHallOfFame("we are so back");
    expect(await readHallOfFame()).toEqual(["we are so back"]);
  });

  it("dedupes case-insensitively", async () => {
    await appendHallOfFame("Touch Grass");
    await appendHallOfFame("touch grass");
    expect(await readHallOfFame()).toEqual(["Touch Grass"]);
  });

  it("rejects blank and overlong lines", async () => {
    await appendHallOfFame("   ");
    await appendHallOfFame("x".repeat(200));
    expect(await readHallOfFame()).toEqual([]);
  });

  it("does NOT cap by count — append-only keeps every shipped line", async () => {
    // Regression for the CLAUDE.md "cap by content, not count" fix: the old
    // slice(-200) silently dropped the oldest anchors.
    for (let i = 0; i < 205; i++) await appendHallOfFame(`line ${i}`);
    const all = await readHallOfFame();
    expect(all).toHaveLength(205);
    expect(all[0]).toBe("line 0"); // the oldest survives
    expect(all[204]).toBe("line 204");
  });
});
