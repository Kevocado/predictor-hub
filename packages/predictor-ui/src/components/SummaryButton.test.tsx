/** SummaryButton — the only network caller.
 *
 *  The request function is injected, so no test here touches the network. What
 *  these prove: the button fires once and cannot double-fire, a resolved summary
 *  is handed to the parent, every failure mode (reject, timeout, unexpected
 *  shape) funnels to `onUnavailable`, and the fixed upstream message is never
 *  rendered — a proxy 502 and a dead container look the same to a reader.
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { SummaryButton, type SummaryButtonProps } from "./SummaryButton";
import type { Explanation } from "./ExplainerPanel";

/** A complete v2 answer, the shape the button accepts as a summary. */
const VALID: Explanation = {
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

/** Render the button with the given request, capturing the two callbacks. */
const renderButton = (props: Partial<SummaryButtonProps> & { request: () => Promise<unknown> }) => {
  const onSummary = vi.fn();
  const onUnavailable = vi.fn();
  render(
    <SummaryButton
      request={props.request}
      onSummary={onSummary}
      onUnavailable={onUnavailable}
      label={props.label}
      budgetMs={props.budgetMs}
    />,
  );
  return { onSummary, onUnavailable };
};

describe("SummaryButton", () => {
  it("renders a button", () => {
    renderButton({ request: () => Promise.resolve(VALID) });
    expect(screen.getByRole("button")).toBeInTheDocument();
  });

  it("calls the request function once when clicked", async () => {
    const request = vi.fn(() => Promise.resolve(VALID));
    const user = userEvent.setup();
    renderButton({ request });
    await user.click(screen.getByRole("button"));
    expect(request).toHaveBeenCalledTimes(1);
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
    renderButton({ request });
    const button = screen.getByRole("button");
    await user.click(button);
    // The button is disabled while loading, so the second press is a no-op even
    // before the guard in the handler is reached.
    await user.click(button);
    expect(request).toHaveBeenCalledTimes(1);
    resolve(VALID);
  });

  it("hands a resolved summary to the parent", async () => {
    const { onSummary } = renderButton({ request: () => Promise.resolve(VALID) });
    const user = userEvent.setup();
    await user.click(screen.getByRole("button"));
    expect(onSummary).toHaveBeenCalledTimes(1);
    expect(onSummary).toHaveBeenCalledWith(VALID);
  });

  it("sends a rejecting request to onUnavailable", async () => {
    const { onUnavailable } = renderButton({ request: () => Promise.reject(new Error("unreachable")) });
    const user = userEvent.setup();
    await user.click(screen.getByRole("button"));
    expect(onUnavailable).toHaveBeenCalledTimes(1);
  });

  it("treats a proxy 502 as unavailable and never shows the upstream message", async () => {
    const { onUnavailable } = renderButton({
      request: () => Promise.reject(new Error("502 Bad Gateway")),
    });
    const user = userEvent.setup();
    await user.click(screen.getByRole("button"));
    expect(onUnavailable).toHaveBeenCalledTimes(1);
    // The fixed upstream message is never shown to a reader.
    expect(screen.queryByText(/502/)).toBeNull();
    expect(screen.queryByText(/bad gateway/i)).toBeNull();
  });

  it("gives up after the budget and offers a retry", async () => {
    const { onUnavailable } = renderButton({
      // Never resolves: the budget is the only thing that can end this.
      request: () => new Promise(() => {}),
      budgetMs: 50,
    });
    const user = userEvent.setup();
    await user.click(screen.getByRole("button"));
    // Wait past the budget in real time; the injected budget keeps the test fast
    // while the component's default stays at the spec's 15 s.
    await new Promise((r) => setTimeout(r, 100));
    expect(onUnavailable).toHaveBeenCalledTimes(1);
  });

  it("treats a 2xx that is not the expected shape as unavailable", async () => {
    const { onSummary, onUnavailable } = renderButton({
      request: () => Promise.resolve({ not: "a summary" }),
    });
    const user = userEvent.setup();
    await user.click(screen.getByRole("button"));
    expect(onUnavailable).toHaveBeenCalledTimes(1);
    expect(onSummary).not.toHaveBeenCalled();
  });

  it("treats a 2xx with no verdict as unavailable", async () => {
    const { onSummary, onUnavailable } = renderButton({
      request: () => Promise.resolve({ factors: [] }),
    });
    const user = userEvent.setup();
    await user.click(screen.getByRole("button"));
    expect(onUnavailable).toHaveBeenCalledTimes(1);
    expect(onSummary).not.toHaveBeenCalled();
  });

  it("spins while loading and shows the label when idle", async () => {
    const request = vi.fn(() => new Promise(() => {}));
    renderButton({ request, label: "Get the AI summary" });
    const button = screen.getByRole("button");
    expect(button).toHaveTextContent("Get the AI summary");
    expect(button).toBeEnabled();

    const user = userEvent.setup();
    await user.click(button);
    expect(button).toBeDisabled();
    expect(button).toHaveTextContent("Writing");
  });

  it("shows the label the parent passes, so a retry reads as a retry", () => {
    renderButton({ request: () => Promise.resolve(VALID), label: "Try again" });
    expect(screen.getByRole("button")).toHaveTextContent("Try again");
  });
});
