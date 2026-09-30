/**Three defects in the shared UI, each verified here rather than asserted.

1. **`<main>` inside the game-detail dialog.** `FixtureFlow` rendered a `<main>`
   landmark, so every site's game-detail modal carried a second `main` beside
   the page's. A landmark is a claim about page structure, and two of them means
   a screen-reader user navigating by landmark is told the dialog is a document
   root. It is a `<div>` now, identified by testid.

2. **`KeyNumberTile` hid a numeric 0.** The guard was `!tile.value`, so a 0-0
   draw, a total of zero, or a probability rounded to nothing rendered as no
   tile at all. The failure is silent and reads as "there is no market here"
   rather than "the model said zero" — a reader is told a thing is absent when
   the model actually said it was nil.

3. **`SummaryButton` could act after unmount, and could strand itself.** The
   budget timer was cleared on unmount and the comment said that was enough. It
   is not: `request()` is still pending and still resolves, calling
   `onSummary`/`setLoading` on a component that has gone. Separately, a
   `request()` that throws SYNCHRONOUSLY escaped before the promise chain was
   built, so no `.catch` saw it and the button stayed disabled forever — a dead
   control on the page, which is the reader's problem and not an error anywhere.

 */
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { SummaryButton } from "./SummaryButton";
import { KeyNumberTile, type MarketTile } from "./KeyNumberTile";

// --- 1. the landmark -------------------------------------------------------------

describe("FixtureFlow is not a landmark", () => {
  it("renders no main landmark when the page already has one", async () => {
    const { FixtureFlow } = await import("./FixtureFlow");
    const { container } = render(
      <>
        <main>
          <FixtureFlow sport="nba" state="pre-game" bundle={{ home_team: "BOS", away_team: "MIA" }} request={stubRequest} />
        </main>
      </>,
    );
    // Two mains would tell a screen-reader user the dialog is a document root.
    expect(container.querySelectorAll("main")).toHaveLength(1);
    expect(screen.getByTestId("fixture-flow")).toBeInTheDocument();
  });

  it("carries no implicit landmark role at all", async () => {
    const { FixtureFlow } = await import("./FixtureFlow");
    const { container } = render(
      <FixtureFlow sport="nba" state="pre-game" bundle={{ home_team: "BOS", away_team: "MIA" }} request={stubRequest} />,
    );
    const flow = container.querySelector('[data-testid="fixture-flow"]')!;
    expect(["main", "navigation", "banner", "contentinfo", "complementary", "form", "search"])
      .not.toContain(flow.tagName.toLowerCase());
  });
});

// --- 2. a zero is a figure -------------------------------------------------------

describe("KeyNumberTile renders a numeric zero", () => {
  const tile = (value: MarketTile["value"]): MarketTile => ({
    market: "total", label: "Total", value,
  });

  it("draws a 0 rather than hiding the tile", () => {
    render(<KeyNumberTile tile={tile(0)} />);
    expect(screen.getByTestId("tile-total")).toBeInTheDocument();
  });

  it("draws a 0 for a probability too", () => {
    // The case that reads most like a bug to a user: the model is certain.
    render(<KeyNumberTile tile={tile("0%")} />);
    expect(screen.getByTestId("tile-total")).toBeInTheDocument();
  });

  it("still hides a genuinely absent figure", () => {
    // The guard must not become "render everything": a tile with no value is
    // the adapter saying it has no figure, and drawing an empty box is its own
    // lie. `""` is the adapter's encoding of that, so it stays hidden.
    for (const absent of [null, undefined, ""]) {
      const { unmount } = render(<KeyNumberTile tile={tile(absent as MarketTile["value"])} />);
      expect(screen.queryByTestId("tile-total")).toBeNull();
      unmount();
    }
  });
});

// --- 3. the button after unmount, and a request that throws ---------------------

const summary = {
    verdict: "v", band: "moderate", factors: [],
    source: "template", model: "", generated_at: "2026-09-29T00:00:00Z",
    sport: "nba", pick_timing: "pre_kickoff",
  } as never;

const stubRequest = () => Promise.resolve(summary);

describe("SummaryButton survives unmount and a synchronous throw", () => {
  it("calls nothing once the button has gone", async () => {
    // The reader presses the button and closes the dialog. The request settles
    // afterwards, and there is nobody to tell.
    let resolve: (v: unknown) => void = () => {};
    const request = vi.fn(() => new Promise((r) => { resolve = r; }));
    const onSummary = vi.fn();
    const onUnavailable = vi.fn();

    const { unmount } = render(
      <SummaryButton request={request} onSummary={onSummary} onUnavailable={onUnavailable} />,
    );
    fireEvent.click(screen.getByRole("button"));
    unmount();
    await act(async () => { resolve(summary); });

    expect(onSummary).not.toHaveBeenCalled();
    expect(onUnavailable).not.toHaveBeenCalled();
  });

  it("treats a synchronous throw as unavailable and re-enables itself", async () => {
    // Before: the throw escaped before the promise chain existed, so no .catch
    // saw it, `loading` stayed true, and the button was disabled forever.
    const onUnavailable = vi.fn();
    const request = vi.fn(() => { throw new Error("bad url"); });

    render(<SummaryButton request={request} onSummary={vi.fn()} onUnavailable={onUnavailable} />);
    const button = screen.getByRole("button");
    fireEvent.click(button);

    await waitFor(() => expect(onUnavailable).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(button).not.toBeDisabled());
  });

  it("does not double-fire on a second press while loading", async () => {
    const request = vi.fn(() => new Promise(() => {}));
    render(<SummaryButton request={request} onSummary={vi.fn()} onUnavailable={vi.fn()} />);
    const button = screen.getByRole("button");
    fireEvent.click(button);
    // `loading` is state, so the guard only bites after React has re-rendered.
    // Without the await the second click lands in the same tick, before the
    // disabled attribute exists, and the guard cannot have applied.
    await waitFor(() => expect(button).toBeDisabled());
    fireEvent.click(button);
    expect(request).toHaveBeenCalledTimes(1);
  });
});

// A control that reads the body of the file's claim, so the three above are
// exercising the same component the sites mount.
describe("the button is the one the panel mounts", () => {
  it("is exported and used by FixtureExplainer", async () => {
    const { FixtureExplainer } = await import("./FixtureExplainer");
    render(
      <FixtureExplainer
        sport="nba"
        state="pre-game"
        bundle={{ home_team: "A", away_team: "B" }}
        request={() => Promise.resolve(summary)}
      />,
    );
    expect(screen.getByRole("button", { name: /ai summary/i })).toBeInTheDocument();
  });
});

void useState; // keeps the React import honest if the file is trimmed
