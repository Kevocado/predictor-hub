/**
 * One vocabulary for five sports.
 *
 * The record pages were built in four places and named the same facts four
 * ways: "Called it"/"Missed" on one, `hit`/`miss` on another, `ats`/`totals`
 * on a third. The kit's job is to make the words a single decision. Part of
 * that is these constants; the other part is the source scan at the bottom,
 * which is the only assertion that fires for a string nobody remembered to
 * route through the constants.
 */
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { PUSH, RIGHT, WRONG, marketLabel, marketRank, momentFor } from "./vocabulary";

describe("one vocabulary", () => {
  it("a pick is Right or Wrong, never called/missed", () => {
    expect(RIGHT).toBe("Right");
    expect(WRONG).toBe("Wrong");
    expect(PUSH).toBe("Push");
  });

  it("spells the markets the family reads", () => {
    expect(marketLabel("game_outcome")).toBe("Winner pick");
    expect(marketLabel("h2h")).toBe("Moneyline");
    expect(marketLabel("spread")).toBe("Spread");
    expect(marketLabel("total")).toBe("Total");
    expect(marketLabel("player_props")).toBe("Props");
  });

  it("never hands a raw market key back as a label", () => {
    for (const key of ["game_outcome", "h2h", "spread", "total", "totals", "player_props", "props"]) {
      expect(marketLabel(key), key).not.toBe(key);
    }
  });

  it("orders markets lead-first, then Moneyline, Spread, Total, Props", () => {
    const keys = ["player_props", "total", "spread", "h2h", "game_outcome"];
    const ordered = [...keys].sort((a, b) => marketRank(a) - marketRank(b));
    expect(ordered).toEqual(["game_outcome", "h2h", "spread", "total", "player_props"]);
  });

  it("names the moment the sport's own way", () => {
    expect(momentFor("nba")).toBe("tip-off");
    expect(momentFor("f1")).toBe("the session");
    expect(momentFor("nfl")).toBe("kickoff");
    expect(momentFor("cfb")).toBe("kickoff");
    expect(momentFor("pl")).toBe("kickoff");
  });
});

describe("no kit component hard-codes the words the vocabulary owns", () => {
  it("keeps Called it / Missed / hit / miss / ats / totals out of every string", () => {
    // A source scan, not a render. Every string a reader can see starts life as
    // a literal in one of these files, so this is the cheapest place to stop the
    // four dialects growing back — and the only one that does not need somebody
    // to remember. Comments are stripped first: prose about the rule is not the
    // rule. Object keys are read unquoted by convention here, so `totals: "Total"`
    // is a mapping rather than a rendered string.
    const banned = /\b(called it|missed|hits?|miss(es)?|ats|totals)\b/i;
    // "hit rate" is the statistical phrase the week chart's own accessible name
    // uses (`Hit rate by week`, carried over from NBA); it is not the verdict
    // word. Everything else containing `hit` or `miss` is the verdict and is
    // refused. The rendered-text test in trackRecord.test.tsx covers the words a
    // reader actually sees, which is what the ban is really about.
    const statistical = /hit\s*rate/gi;
    const files = readdirSync(__dirname, { withFileTypes: true })
      .filter((e) => e.isFile() && /\.tsx?$/.test(e.name) && !/\.test\.tsx?$/.test(e.name))
      .map((e) => join(__dirname, e.name));
    // Measured, not assumed: an empty list would make the scan vacuously green.
    expect(files.length).toBeGreaterThan(3);

    const offenders: string[] = [];
    for (const file of files) {
      const src = readFileSync(file, "utf8")
        .replace(/\/\*[\s\S]*?\*\//g, "")
        .replace(/^\s*\/\/.*$/gm, "");
      for (const match of src.matchAll(/(?<![\w$])"((?:\\.|[^"\\])*)"|'((?:\\.|[^'\\])*)'|`((?:\\.|[^`\\])*)`/g)) {
        const text = (match[1] ?? match[2] ?? match[3] ?? "").replace(statistical, "");
        if (banned.test(text)) offenders.push(`${file.split("/").pop()}: "${text}"`);
      }
    }
    expect(offenders, "these strings carry a superseded word instead of the vocabulary").toEqual([]);
  });
});
