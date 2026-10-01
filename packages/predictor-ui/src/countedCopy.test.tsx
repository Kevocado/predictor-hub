/**
 * The track record counts every recorded pick, not only the ones made before
 * the start (spec `2026-10-01-track-record-counts-every-pick`, merged as #66).
 * The earliest recorded pick per (game, market) is the counted one, whenever it
 * was made, and honesty moved from **exclusion** to **disclosure**.
 *
 * That is why the two sentences in this file are the important ones.
 *
 * 1. **The source guard below.** Every other test here is about a string someone
 *    remembered to update. This one reads every shipped file, so the superseded
 *    rule cannot come back through a *new* string nobody thought to look for —
 *    which is exactly how it came back the first time, in a status badge worded
 *    by a different file from the one that was fixed.
 *
 * 2. **The rendered guards.** A source scan cannot tell a word that reaches a
 *    reader from a word that sits in a branch nobody visits, so the two
 *    components that can show a post-kickoff pick are rendered and read.
 *
 * What is NOT asserted here, deliberately: that a pick made after the start is
 * bad, or that it is suspect. It is neither. The record counts it, and the only
 * claim the UI makes about it is *when it was made* — because that is the one
 * fact a reader cannot recover from the number itself.
 */
import { render, screen } from "@testing-library/react";
import { readFileSync, readdirSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { ExplainerPanel } from "./components/ExplainerPanel";
import { InstantBlock } from "./components/InstantBlock";
import { statusWords, type Moment, type Status } from "./components/StatusBadge";
import type { Explanation } from "./components/ExplainerPanel";

/** Every shipped source file: `src/` minus the tests, which are not shipped. */
function shippedFiles(dir = resolve(__dirname)): string[] {
  return readdirSync(dir, { recursive: true, withFileTypes: true })
    .filter((e) => e.isFile() && /\.tsx?$/.test(e.name) && !/\.test\.tsx?$/.test(e.name))
    .map((e) => join(e.parentPath ?? e.path, e.name));
}

const NFL = {
  home_team: "GB", home_team_full: "Green Bay", away_team: "ATL",
  home_win_prob: 0.72, away_win_prob: 0.28, pick: { label: "GB", prob: 0.72 },
};

const answer = (over: Partial<Explanation> = {}): Explanation =>
  ({
    verdict: "Green Bay is the pick.",
    band: "strong",
    factors: [],
    source: "llm",
    model: "test",
    generated_at: "2026-10-01T00:00:00Z",
    sport: "nfl",
    ...over,
  }) as unknown as Explanation;

describe("the superseded rule is gone from the source", () => {
  it('no shipped file says a pick is "not counted"', () => {
    // A source scan, not a render: this is the one assertion here that fires
    // for a string nobody wired up to a component. Every string a reader can
    // see starts life as text in one of these files, so this is the cheapest
    // place to stop the rule coming back, and the only one that does not need
    // somebody to remember.
    const banned = ["not", "counted"].join(" ");
    const files = shippedFiles();
    // Measured, not assumed: an empty list would make every assertion below
    // vacuously true, which is the failure mode of a guard that reads a
    // directory it silently failed to walk.
    expect(files.length).toBeGreaterThan(10);

    const offenders = files
      .filter((f) => new RegExp(banned, "i").test(readFileSync(f, "utf8")))
      .map((f) => f.replace(resolve(__dirname), "src"));
    expect(offenders, `these files still say a pick is "${banned}"`).toEqual([]);
  });
});

describe("a post-kickoff pick is labelled, not excluded", () => {
  it("the badge says when it was made, for every moment the family uses", () => {
    // The STATUS KEY is still `rebuilt` and always will be: it is the value
    // sites pass and the value `pick_timing` carries across the wire, so it is
    // an internal enum rather than copy. Only the words a reader sees changed.
    // Renaming the key would break every site's compile for no reader-visible
    // gain, which is the trade this test exists to refuse.
    const moments: [Status, Moment, string][] = [
      ["rebuilt", "kickoff", "Made after kickoff"],
      ["rebuilt", "tip-off", "Made after tip-off"],
      ["rebuilt", "the session", "Made after the session"],
    ];
    for (const [status, moment, words] of moments) {
      expect(statusWords(status, moment)).toBe(words);
    }
  });

  it("the instant block states the moment and never the exclusion", () => {
    const { container } = render(
      <InstantBlock sport="nba" bundle={{ ...NFL, pick_timing: "rebuilt" }} />,
    );
    expect(screen.getByText("Made after tip-off")).toBeInTheDocument();
    expect(container.textContent).toMatch(/made after tip-off/i);
    expect(container.textContent).not.toMatch(/not\s+counted/i);
  });

  it("the explainer panel states the moment and never the exclusion", () => {
    const { container } = render(
      <ExplainerPanel data={answer({ pick_timing: "rebuilt" })} loading={false} error={false} onRetry={() => {}} />,
    );
    expect(screen.getByText("Made after kickoff")).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/not\s+counted/i);
  });

  it("keeps 'for reference' out too: it is the same exclusion, phrased politely", () => {
    // The old sentence carried two claims — the moment, and that the pick does
    // not count. The moment survives; the exclusion does not, and "for
    // reference" was the half that has to go with it.
    for (const [name, node] of [
      ["InstantBlock", <InstantBlock key="i" sport="nfl" bundle={{ ...NFL, pick_timing: "rebuilt" }} />],
      ["ExplainerPanel", <ExplainerPanel key="e" data={answer({ pick_timing: "rebuilt" })} loading={false} error={false} onRetry={() => {}} />],
    ] as const) {
      const { container, unmount } = render(node);
      expect(container.textContent, name).not.toMatch(/for\s+reference/i);
      unmount();
    }
  });

  it("still says nothing about timing when the pick was made in time", () => {
    // The disclosure is about a pick made after the start. A panel with no such
    // pick has nothing to disclose, and the pre-kickoff chip stays the one that
    // speaks.
    const { container } = render(
      <InstantBlock sport="nfl" bundle={NFL} />,
    );
    expect(screen.getByText("Made before kickoff")).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/made after/i);
  });

  it("an unconfirmed start time still discloses uncertainty, and is not an exclusion", () => {
    // `unverified` is a different fact and the decision did not touch it: the
    // schedule never supplied a start time, so nothing went wrong and nothing
    // is being withheld. What must not happen is this branch being "fixed" into
    // the old claim, which is why it is asserted here.
    const { container } = render(
      <InstantBlock
        sport="f1"
        bundle={{ driver: "Max Verstappen", pick: "Max Verstappen", pick_timing: "unknown", session_start: null }}
      />,
    );
    expect(screen.getByText("Timing not confirmed")).toBeInTheDocument();
    expect(container.textContent).toMatch(/did not provide the start time/i);
    expect(container.textContent).not.toMatch(/not\s+counted/i);
  });
});
