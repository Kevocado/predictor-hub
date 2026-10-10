import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MatchupBrief, createContextLoader, type MatchupRow } from "./MatchupBrief";
import { ExplainerPanel, type Explanation } from "./ExplainerPanel";
import { FixtureExplainer } from "./FixtureExplainer";

const duel: MatchupRow = {
  id: "pass_off_vs_pass_def:home", attacker: "Bills", defender: "Jets",
  stat: "passing offence", foil: "pass defence",
  attacker_rank: 3, defender_rank: 28, n_teams: 32, toward_pick: null,
};
const form = { id: "quali", subject: "Verstappen", label: "qualifying pace", value: "+0.12s", rank: 2, n: 20 };

describe("MatchupBrief (the Matchup section)", () => {
  it("draws a RankDuel per duel and plain rows for form, neutrally", () => {
    render(<MatchupBrief matchups={[duel]} formRows={[form, { ...form, id: "t", label: "track history", rank: null, n: null }]} />);
    expect(screen.getByRole("heading", { name: "Matchup" })).toBeTruthy();
    expect(screen.getAllByTestId("rank-duel")).toHaveLength(1);
    expect(screen.getByTestId("form-quali").textContent).toContain("#2 of 20");
    expect(screen.getByTestId("form-t").textContent).not.toContain("#");
    expect(document.body.textContent).not.toMatch(/advantage|favou?rs|edge|risk/i);
  });

  it("renders nothing, no heading and no placeholder, when there is nothing to draw", () => {
    const { container } = render(<MatchupBrief />);
    expect(container.innerHTML).toBe("");
    const bad = render(<MatchupBrief matchups={[{ ...duel, defender_rank: 40 }]} formRows={[{ ...form, value: "" }]} />);
    expect(bad.container.innerHTML).toBe("");
    const junk = render(<MatchupBrief matchups={"x" as any} formRows={{} as any} />);
    expect(junk.container.innerHTML).toBe("");
  });
});

const base: any = {
  source: "llm", model: "m", generated_at: new Date().toISOString(), sport: "nfl",
  pick_timing: "pre_kickoff", verdict: "Bills are the pick.", band: "moderate", factors: [],
};
const RESTING = { loading: false, error: false, onRetry: () => {} };

describe("the AI panel is verdict + read", () => {
  it("shows the read and no Edge/Risk/Price groups", () => {
    render(<ExplainerPanel {...RESTING} data={{ ...base, read: "Two sentences. About the matchup." } as Explanation} />);
    expect(screen.getByTestId("ai-read").textContent).toBe("Two sentences. About the matchup.");
    expect(screen.queryByText(/^(Edge|Risk|Price)$/)).toBeNull();
    expect(screen.queryByText("Why it matters")).toBeNull();
  });

  it("a pre-v9 answer (no read) keeps its factor list", () => {
    const legacy = { ...base, factors: [{ key: "record", direction: "neutral", headline: "Its record", text: "41 of 68." }] };
    render(<ExplainerPanel {...RESTING} data={legacy as Explanation} />);
    expect(screen.getByText("Why it matters")).toBeTruthy();
    expect(screen.queryByTestId("ai-read")).toBeNull();
  });
});

describe("FixtureExplainer", () => {
  const bundle = { home_team: "BUF", away_team: "NYJ", pick: { label: "BUF", prob: 0.6 }, context: { matchups: [duel], form_rows: [form] } };
  const props = { sport: "nfl", state: { kind: "idle" } as any, request: async () => ({}) };

  it("shows the Matchup section before the AI is asked for", () => {
    render(<FixtureExplainer {...props} bundle={bundle} />);
    expect(screen.getByTestId("matchup-section")).toBeTruthy();
  });

  it("shows no Matchup section for a bundle without context", () => {
    render(<FixtureExplainer {...props} bundle={{ ...bundle, context: undefined }} />);
    expect(screen.queryByTestId("matchup-section")).toBeNull();
  });
});

describe("FixtureExplainer.loadContext", () => {
  const noCtx = { id: "g1", home_team: "BUF", away_team: "NYJ", pick: { label: "BUF", prob: 0.6 } };
  const props = { sport: "nfl", state: { kind: "idle" } as any, request: async () => ({}) };

  it("loads on mount, without pressing the button, and draws the section", async () => {
    const load = vi.fn(async () => ({ matchups: [duel] }));
    render(<FixtureExplainer {...props} bundle={noCtx} loadContext={load} />);
    expect(await screen.findByTestId("matchup-section")).toBeTruthy();
    expect(load).toHaveBeenCalledWith("g1");
  });

  it("a failed load renders nothing and no error banner", async () => {
    const load = vi.fn(async () => { throw new Error("502"); });
    render(<FixtureExplainer {...props} bundle={noCtx} loadContext={load} />);
    await waitFor(() => expect(load).toHaveBeenCalled());
    expect(screen.queryByTestId("matchup-section")).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("an empty context renders nothing", async () => {
    const load = vi.fn(async () => ({}));
    render(<FixtureExplainer {...props} bundle={noCtx} loadContext={load} />);
    await waitFor(() => expect(load).toHaveBeenCalled());
    expect(screen.queryByTestId("matchup-section")).toBeNull();
  });

  it("prefers bundle.context and does not load when the site supplies it", () => {
    const load = vi.fn(async () => ({ matchups: [] }));
    render(<FixtureExplainer {...props} bundle={{ ...noCtx, context: { matchups: [duel] } }} loadContext={load} />);
    expect(screen.getByTestId("matchup-section")).toBeTruthy();
    expect(load).not.toHaveBeenCalled();
  });

  it("uses fixtureId when the bundle has no id", async () => {
    const load = vi.fn(async () => ({}));
    render(<FixtureExplainer {...props} bundle={{ home_team: "A" }} fixtureId="x/y" loadContext={load} />);
    await waitFor(() => expect(load).toHaveBeenCalledWith("x/y"));
  });
});

describe("createContextLoader", () => {
  it("GETs <base>/<id>/context and throws on a non-2xx", async () => {
    const f = vi.fn(async () => new Response(JSON.stringify({ matchups: [] }), { status: 200 }));
    vi.stubGlobal("fetch", f);
    expect(await createContextLoader("/api/explain/nfl/")("a/b c")).toEqual({ matchups: [] });
    expect((f.mock.calls[0] as any)[0]).toBe("/api/explain/nfl/a/b%20c/context");
    vi.stubGlobal("fetch", async () => new Response("x", { status: 502 }));
    await expect(createContextLoader("/e")("g")).rejects.toThrow(/502/);
    vi.unstubAllGlobals();
  });
});
