/** FixtureExplainer — the panel, three states.
 *
 *  What these prove: the facts render from the bundle before anything is asked
 *  for, with no request; the button is absent once a summary exists; on failure
 *  the facts and the flow are still on screen and the button offers a retry; a
 *  2xx that is not the expected shape is treated as unavailable; the summary
 *  swaps in over a block and a flow that never unmount; a second press cannot
 *  double-fire; the button says what it adds; and `news_date` is read when
 *  present and the element is omitted entirely when absent.
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { FixtureExplainer } from "./FixtureExplainer";
import type { Explanation } from "./ExplainerPanel";

/** A pre-game bundle: the facts the site already has, no request needed. */
const BUNDLE = {
  home_team: "KC",
  away_team: "BAL",
  market_line: -2.5,
  home_win_prob: 0.38,
  away_win_prob: 0.62,
  pick: { label: "BAL", prob: 0.62 },
  pick_timing: "pre_kickoff",
  score: null,
  result: null,
  drivers: [],
  context: {},
} as const;

/** A complete v2 answer, what a successful request resolves with. */
const SUMMARY: Explanation = {
  source: "llm",
  model: "test-model",
  generated_at: new Date().toISOString(),
  sport: "nfl",
  pick_timing: "pre_kickoff",
  verdict: "BAL is the pick, but the line is thinner than the number.",
  band: "moderate",
  factors: [
    { key: "moneyline", direction: "up", headline: "Model leans BAL", text: "The rating gap has held." },
  ],
};

/** Render the panel with the given request, the only thing a test stubs. */
const renderExplainer = (request: () => Promise<unknown>) =>
  render(<FixtureExplainer sport="nfl" state="pre-game" bundle={BUNDLE} request={request} />);

describe("FixtureExplainer", () => {
  it("defaults to the flow state and makes no request", () => {
    const request = vi.fn(() => Promise.resolve(SUMMARY));
    renderExplainer(request);
    // The block renders too, from the same bundle, with no request either.
    expect(screen.getByTestId("instant-block")).toBeInTheDocument();
    expect(screen.getByTestId("fixture-flow")).toBeInTheDocument();
    expect(request).not.toHaveBeenCalled();
  });

  it("shows the facts before the button, with no request", () => {
    const request = vi.fn(() => Promise.resolve(SUMMARY));
    render(
      <FixtureExplainer
        sport="nfl"
        state="pre-game"
        bundle={BUNDLE}
        request={request}
        extras={{
          tiles: [{ market: "moneyline", label: "moneyline", value: "62%", sub: "win · BAL" }],
          segments: [
            { label: "KC", prob: 0.38, market: "moneyline" },
            { label: "BAL", prob: 0.62, market: "moneyline" },
          ],
        }}
      />,
    );
    const block = screen.getByTestId("instant-block");
    expect(block).toBeInTheDocument();
    expect(within(block).getByTestId("tile-moneyline")).toBeInTheDocument();
    expect(within(block).getAllByTestId("pbar-fill")).toHaveLength(2);
    // Order is the claim: the figures a reader came for are above the ask. The
    // plan named `getByTestId("summary-button")`; the button carries no testid
    // (every other test reaches it by role), so the role is the handle here.
    const button = screen.getByRole("button", { name: /get the ai summary/i });
    expect(
      block.compareDocumentPosition(button) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(request).not.toHaveBeenCalled();
  });

  it("names what the AI adds", () => {
    renderExplainer(() => Promise.resolve(SUMMARY));
    expect(screen.getByTestId("ai-promise")).toHaveTextContent(
      "AI read: model vs line, trends, who's out.",
    );
  });

  it("shows the summary button in the flow state", () => {
    renderExplainer(() => Promise.resolve(SUMMARY));
    expect(screen.getByRole("button", { name: /get the ai summary/i })).toBeInTheDocument();
  });

  it("swaps in the summary and removes the button once a summary exists", async () => {
    const user = userEvent.setup();
    renderExplainer(() => Promise.resolve(SUMMARY));
    await user.click(screen.getByRole("button"));
    expect(screen.getByTestId("fixture-summary")).toBeInTheDocument();
    // The summary button is gone (factor rows are buttons too, so scope by name).
    expect(screen.queryByRole("button", { name: /ai summary/i })).toBeNull();
  });

  it("keeps the flow mounted when the summary lands — no flicker", async () => {
    const user = userEvent.setup();
    renderExplainer(() => Promise.resolve(SUMMARY));
    expect(screen.getByTestId("fixture-flow")).toBeInTheDocument();
    await user.click(screen.getByRole("button"));
    // The flow never unmounts: it is on screen before the click and after the
    // summary lands, so there is no frame where the panel is empty.
    expect(screen.getByTestId("fixture-flow")).toBeInTheDocument();
    expect(screen.getByTestId("fixture-summary")).toBeInTheDocument();
  });

  it("on failure the flow is still on screen and the button offers a retry", async () => {
    const user = userEvent.setup();
    renderExplainer(() => Promise.reject(new Error("unreachable")));
    await user.click(screen.getByRole("button"));
    expect(screen.getByTestId("fixture-flow")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
    // The failure is not shown as an empty panel or an error message.
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("treats a 2xx that is not the expected shape as unavailable", async () => {
    const user = userEvent.setup();
    renderExplainer(() => Promise.resolve({ not: "a summary" }));
    await user.click(screen.getByRole("button"));
    expect(screen.getByTestId("fixture-flow")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });

  it("cannot double-fire while one is in flight", async () => {
    let resolve: (value: unknown) => void = () => {};
    const request = vi.fn(
      () =>
        new Promise<unknown>((r) => {
          resolve = r;
        }),
    );
    const user = userEvent.setup();
    renderExplainer(request);
    const button = screen.getByRole("button");
    await user.click(button);
    await user.click(button);
    expect(request).toHaveBeenCalledTimes(1);
    resolve(SUMMARY);
  });

  it("reads news_date when present", async () => {
    const user = userEvent.setup();
    renderExplainer(() => Promise.resolve({ ...SUMMARY, news_date: "2026-09-28" }));
    await user.click(screen.getByRole("button"));
    expect(screen.getByTestId("news-date")).toHaveTextContent("2026-09-28");
  });

  it("omits the news date element entirely when absent", async () => {
    const user = userEvent.setup();
    renderExplainer(() => Promise.resolve(SUMMARY));
    await user.click(screen.getByRole("button"));
    expect(screen.queryByTestId("news-date")).toBeNull();
  });

  it("draws the site's figures ONCE, in the facts block above the summary, when extras are passed", async () => {
    const user = userEvent.setup();
    const extras = {
      tiles: [{ market: "moneyline", label: "moneyline", value: "62%", sub: "win · BAL" }],
      segments: [
        { label: "KC", prob: 0.38, market: "moneyline" },
        { label: "BAL", prob: 0.62, market: "moneyline" },
      ],
    };
    render(
      <FixtureExplainer
        sport="nfl"
        state="pre-game"
        bundle={BUNDLE}
        request={() => Promise.resolve(SUMMARY)}
        extras={extras}
      />,
    );
    // Before the request, the same figures are already in the instant block —
    // the tile and both bar segments the summary state will draw.
    const block = screen.getByTestId("instant-block");
    expect(within(block).getByTestId("tile-moneyline")).toBeInTheDocument();
    expect(within(block).getAllByTestId("pbar-fill")).toHaveLength(2);

    await user.click(screen.getByRole("button"));
    const summaryView = screen.getByTestId("fixture-summary");
    // Interpretation does not repeat the facts: the tile and the bar stay where
    // they already were (the block, above), and the summary carries neither.
    expect(within(summaryView).queryByTestId("tile-moneyline")).toBeNull();
    expect(within(summaryView).queryAllByTestId("pbar-fill")).toHaveLength(0);
    expect(within(screen.getByTestId("instant-block")).getByTestId("tile-moneyline")).toBeInTheDocument();
    expect(screen.getAllByTestId("tile-moneyline")).toHaveLength(1);
  });

  it("joins the answer's pick against the extras' segments, translating '<team> win'", async () => {
    const user = userEvent.setup();
    render(
      <FixtureExplainer
        sport="nfl"
        state="pre-game"
        bundle={BUNDLE}
        request={() =>
          Promise.resolve({ ...SUMMARY, pick: { label: "BAL win" } })
        }
        extras={{
          segments: [
            { label: "KC", prob: 0.38, market: "moneyline" },
            { label: "BAL", prob: 0.62, market: "moneyline" },
          ],
        }}
      />,
    );
    await user.click(screen.getByRole("button"));
    // Translated to the bare team name, the pick accents the BAL segment: the
    // bar says the emphasis as well as colours it. Untranslated, the label
    // would match no segment and the img would carry no pick clause.
    expect(
      screen.getByRole("img", { name: /the pick is BAL/i }),
    ).toBeInTheDocument();
  });

  it("puts the facts block BEFORE the AI summary, and the summary does not repeat the tiles, bar or record", async () => {
    const user = userEvent.setup();
    const extras = {
      tiles: [{ market: "moneyline", label: "moneyline", value: "62%", sub: "win · BAL" }],
      segments: [
        { label: "KC", prob: 0.38, market: "moneyline" },
        { label: "BAL", prob: 0.62, market: "moneyline" },
      ],
      record: { label: "Picks made before kickoff", hits: 11, settled: 15 },
    };
    const { container } = render(
      <FixtureExplainer sport="nfl" state="pre-game" bundle={BUNDLE}
        request={() => Promise.resolve(SUMMARY)} extras={extras} />,
    );
    await user.click(screen.getByRole("button"));
    const block = screen.getByTestId("instant-block");
    const summary = screen.getByTestId("fixture-summary");
    // Facts first, interpretation after.
    expect(block.compareDocumentPosition(summary) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    // Each figure exactly once on the page: one bar, one 62% tile, one record.
    expect(container.querySelectorAll('[data-testid="pbar-fill"]')).toHaveLength(2); // the two segments of ONE bar
    expect(screen.getAllByText("62%")).toHaveLength(1);
    expect(screen.getAllByText(/11\s*\/\s*15|11 of 15/)).toHaveLength(1);
    expect(within(summary).queryByText("62%")).toBeNull();
  });

  it("renders the summary bare when no extras are passed", async () => {
    const user = userEvent.setup();
    renderExplainer(() => Promise.resolve(SUMMARY));
    await user.click(screen.getByRole("button"));
    expect(screen.getByTestId("fixture-summary")).toBeInTheDocument();
    // The verdict renders; no tile, bar or record follows it. Scoped to the
    // summary, because the instant block now states the pick too.
    expect(
      within(screen.getByTestId("fixture-summary")).getByText(/BAL is the pick/),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId("fixture-summary")).queryByTestId("tile-moneyline"),
    ).toBeNull();
  });
});
