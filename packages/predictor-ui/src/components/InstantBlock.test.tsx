import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { InstantBlock } from "./InstantBlock";

const NFL = {
  home_team: "GB", home_team_full: "Green Bay", away_team: "ATL",
  home_win_prob: 0.72, away_win_prob: 0.28, pick: { label: "GB", prob: 0.72 },
};
const TILES = [{ market: "moneyline", label: "moneyline", value: "72%", sub: "win · GB" }];
const SEGMENTS = [{ label: "GB", prob: 0.72, market: "moneyline" }, { label: "ATL", prob: 0.28, market: "moneyline" }];

describe("InstantBlock", () => {
  it("renders the verdict from the bundle without any request", () => {
    // The proof is the spy: it throws if anything is called, and the block has
    // no request prop to pass one through even if it wanted to.
    const fetchSpy = vi.fn(() => {
      throw new Error("the instant block must never fetch");
    });
    const original = globalThis.fetch;
    globalThis.fetch = fetchSpy as unknown as typeof globalThis.fetch;
    try {
      render(<InstantBlock sport="nfl" bundle={NFL} />);
      expect(screen.getByText("Green Bay is the pick.")).toBeInTheDocument();
      expect(fetchSpy).not.toHaveBeenCalled();
    } finally {
      globalThis.fetch = original;
    }
  });

  it("renders the tiles and the bar from the extras", () => {
    render(<InstantBlock sport="nfl" bundle={NFL} extras={{ tiles: TILES, segments: SEGMENTS }} />);
    expect(screen.getByTestId("tile-moneyline")).toBeInTheDocument();
    // One fill per segment: the plan wrote `getByTestId("pbar-fill")`, which is
    // "the bar" to the reader and "two elements" to the query.
    expect(screen.getAllByTestId("pbar-fill")).toHaveLength(2);
  });

  it("renders the record strip when the site passes a record", () => {
    render(
      <InstantBlock
        sport="nfl"
        bundle={NFL}
        extras={{ record: { label: "Picks made before kickoff", hits: 11, settled: 15 } }}
      />,
    );
    expect(screen.getByTestId("record-fill")).toBeInTheDocument();
  });

  it("renders no record strip when the site passes none", () => {
    render(<InstantBlock sport="nfl" bundle={NFL} />);
    expect(screen.queryByTestId("record-fill")).toBeNull();
  });

  it("shows the rebuilt badge and says the pick is not counted", () => {
    render(<InstantBlock sport="nba" bundle={{ ...NFL, pick_timing: "rebuilt" }} />);
    // The badge's own words, not a regex the sentence repeats: `/after tip-off/i`
    // matches both the badge and the sentence beside it.
    expect(screen.getByText("Rebuilt after tip-off")).toBeInTheDocument();
    expect(screen.getByText(/not counted/i)).toBeInTheDocument();
  });

  it("shows the quiet chip for a pick made before the start", () => {
    render(<InstantBlock sport="nfl" bundle={NFL} />);
    expect(screen.getByText("Made before kickoff")).toBeInTheDocument();
    // StatusBadge carries no testid, so its own words are the handle: none of
    // the three badge readings is on the page for a pick made before the start.
    expect(screen.queryByText(/Rebuilt after|Timing not confirmed|No pick yet/)).toBeNull();
  });

  it("shows the unverified badge when F1's schedule gave no start time", () => {
    render(<InstantBlock sport="f1" bundle={{ driver: "Max Verstappen", pick: "Max Verstappen", pick_timing: "unknown", session_start: null }} />);
    expect(screen.getByText(/did not provide the start time/i)).toBeInTheDocument();
  });

  it("words a rebuilt F1 pick as the session, not a kickoff", () => {
    render(<InstantBlock sport="f1" bundle={{ driver: "Max Verstappen", pick: "Max Verstappen", pick_timing: "rebuilt" }} />);
    // "after the game started" on a race page names a moment F1 does not have.
    expect(screen.getByText(/after the session started/)).toBeInTheDocument();
  });

  it("says there is no pick, and still shows the numbers", () => {
    render(
      <InstantBlock
        sport="nfl"
        bundle={{ home_team: "GB", away_team: "ATL", home_win_prob: 0.5 }}
        extras={{ tiles: TILES, segments: SEGMENTS }}
      />,
    );
    expect(screen.getByText(/no pick/i)).toBeInTheDocument();
    expect(screen.getByTestId("tile-moneyline")).toBeInTheDocument();
  });

  it("renders no tiles and no bar when the site passes none (F1's reduced rule)", () => {
    render(<InstantBlock sport="f1" bundle={{ driver: "Max Verstappen", pick: "Max Verstappen", pick_timing: "unknown" }} />);
    expect(screen.queryByTestId("pbar-fill")).toBeNull();
    expect(screen.getByText("Max Verstappen is the pick.")).toBeInTheDocument();
  });

  it("renders nothing at all when the bundle has no pick and no extras", () => {
    const { container } = render(<InstantBlock sport="nfl" bundle={{ home_team: "GB", away_team: "ATL" }} />);
    expect(container.firstChild).toBeNull();
  });

  // --- Review fixes (CodeRabbit on hub#52), each proven red before the fix ---

  it("accents the bar segment of the PICK, and only that one, whichever side it is on", () => {
    const accented = (c: HTMLElement) =>
      Array.from(c.querySelectorAll<HTMLElement>('[data-testid="pbar-fill"]'))
        .map((el, i) => ({ i, on: (el.getAttribute("style") || "").includes("color-pr-accent") }))
        .filter((x) => x.on).map((x) => x.i);
    // Pick GB = first segment.
    const a = render(<InstantBlock sport="nfl" bundle={NFL} extras={{ tiles: TILES, segments: SEGMENTS }} />);
    expect(accented(a.container)).toEqual([0]);
    a.unmount();
    // Pick ATL = second segment: emphasis follows the pick, never the order.
    const ATL = { ...NFL, home_win_prob: 0.4, away_win_prob: 0.6, pick: { label: "ATL", prob: 0.6 } };
    const b = render(<InstantBlock sport="nfl" bundle={ATL}
      extras={{ tiles: TILES, segments: [{ label: "GB", prob: 0.4, market: "moneyline" }, { label: "ATL", prob: 0.6, market: "moneyline" }] }} />);
    expect(accented(b.container)).toEqual([1]);
  });

  it("accents nothing when the bundle has no pick", () => {
    const { container } = render(<InstantBlock sport="nfl" bundle={{ home_team: "GB", away_team: "ATL" }}
      extras={{ tiles: TILES, segments: SEGMENTS }} />);
    const on = Array.from(container.querySelectorAll<HTMLElement>('[data-testid="pbar-fill"]'))
      .filter((el) => (el.getAttribute("style") || "").includes("color-pr-accent"));
    expect(on).toHaveLength(0);
  });

  it("still renders the record when the bundle has no pick and the extras carry only a record", () => {
    const { container } = render(<InstantBlock sport="nfl" bundle={{ home_team: "GB", away_team: "ATL" }}
      extras={{ record: { label: "Picks made before kickoff", hits: 11, settled: 15 } }} />);
    expect(container.firstChild).not.toBeNull();
    expect(screen.getByText(/11\s*\/\s*15|11 of 15/)).toBeInTheDocument();
  });
});
