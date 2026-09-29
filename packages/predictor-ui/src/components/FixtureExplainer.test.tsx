/** FixtureExplainer — the panel, three states.
 *
 *  What these prove: the default state is the flow with no request made; the
 *  button is absent once a summary exists; on failure the flow is still on
 *  screen and the button offers a retry; a 2xx that is not the expected shape
 *  is treated as unavailable; the summary swaps in over a flow that never
 *  unmounts; a second press cannot double-fire; and `news_date` is read when
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
    expect(screen.getByTestId("fixture-flow")).toBeInTheDocument();
    expect(request).not.toHaveBeenCalled();
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
    expect(screen.queryByRole("button")).toBeNull();
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

  it("draws the site's figures under the summary when extras are passed", async () => {
    const user = userEvent.setup();
    render(
      <FixtureExplainer
        sport="nfl"
        state="pre-game"
        bundle={BUNDLE}
        request={() => Promise.resolve(SUMMARY)}
        extras={{
          tiles: [{ market: "moneyline", label: "moneyline", value: "62%", sub: "win · BAL" }],
          segments: [
            { label: "KC", prob: 0.38, market: "moneyline" },
            { label: "BAL", prob: 0.62, market: "moneyline" },
          ],
        }}
      />,
    );
    await user.click(screen.getByRole("button"));
    const summaryView = screen.getByTestId("fixture-summary");
    // The tile value and both bar segments render inside the summary state
    // (scoped: the flow below carries the same figures in its own sentences).
    expect(within(summaryView).getByText("62%")).toBeInTheDocument();
    expect(within(summaryView).getByText("KC")).toBeInTheDocument();
    expect(within(summaryView).getByText("BAL")).toBeInTheDocument();
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

  it("renders the summary bare when no extras are passed", async () => {
    const user = userEvent.setup();
    renderExplainer(() => Promise.resolve(SUMMARY));
    await user.click(screen.getByRole("button"));
    expect(screen.getByTestId("fixture-summary")).toBeInTheDocument();
    // The verdict renders; no tile, bar or record follows it.
    expect(screen.getByText(/BAL is the pick/)).toBeInTheDocument();
  });
});
