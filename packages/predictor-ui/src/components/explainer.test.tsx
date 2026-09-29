import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ExplainerPanel, type Explanation } from "./ExplainerPanel";

const llm: Explanation = {
  source: "llm",
  model: "gpt-4o-mini",
  generated_at: new Date(Date.now() - 4 * 60_000).toISOString(),
  sport: "pl",
  pick_timing: "pre_kickoff",
  verdict: "Sunderland are the slight favourites.",
  band: "moderate",
  factors: [],
};

const template: Explanation = {
  source: "template",
  model: "template",
  generated_at: new Date(Date.now() - 4 * 60_000).toISOString(),
  sport: "pl",
  pick_timing: "pre_kickoff",
  verdict: "Sunderland win, at 57%.",
  band: "moderate",
  factors: [],
};

const noop = () => {};

describe("ExplainerPanel states", () => {
  it("says what is being written, and announces it", () => {
    render(<ExplainerPanel data={null} loading error={false} onRetry={noop} />);
    const status = screen.getByRole("status");
    expect(within(status).getByText("Writing the summary…")).toBeInTheDocument();
  });

  it("an error says what failed and offers a way back", async () => {
    const onRetry = vi.fn();
    render(<ExplainerPanel data={null} loading={false} error onRetry={onRetry} />);
    const alert = screen.getByRole("alert");
    expect(alert).toBeInTheDocument();
    // The panel cannot promise the numbers below are fine — the summary may
    // have failed because their own fetch did. It offers both ways forward.
    expect(alert).toHaveTextContent("Try again");
    expect(alert).toHaveTextContent("carry on with the numbers below");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});

describe("ExplainerPanel honesty footer", () => {
  it("an AI summary names the model and how long ago it was written", () => {
    render(<ExplainerPanel data={llm} loading={false} error={false} onRetry={noop} />);
    const footer = screen.getByText(/AI summary of the model's numbers/);
    expect(footer).toHaveTextContent("gpt-4o-mini");
    expect(footer).toHaveTextContent("4 min ago");
  });

  it("a written-from-numbers summary never calls itself AI", () => {
    render(<ExplainerPanel data={template} loading={false} error={false} onRetry={noop} />);
    const footer = screen.getByText("Summary written from the model's numbers");
    expect(footer).toBeInTheDocument();
    // The word "AI" is a claim about how this was written. A templated
    // summary must not carry it anywhere in the panel.
    expect(document.body.textContent).not.toMatch(/\bAI\b/);
  });

  it("rounds a fresh summary to 'just now' rather than claiming 0 min", () => {
    render(
      <ExplainerPanel
        data={{ ...llm, generated_at: new Date(Date.now() - 20_000).toISOString() }}
        loading={false}
        error={false}
        onRetry={noop}
      />,
    );
    expect(screen.getByText(/just now/)).toBeInTheDocument();
  });

  // The footer is the one claim with no fact behind it, so it must require
  // evidence. These three are the ways the wire can disappoint it, and each
  // one previously produced an "AI" label with nothing to back it.
  it("claims no provenance at all when the source is not a model", () => {
    // A renamed value or a dropped field, not the literal "template".
    render(<ExplainerPanel data={{ ...llm, source: undefined as never }} loading={false} error={false} onRetry={noop} />);
    expect(screen.getByText("Summary written from the model's numbers")).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/\bAI\b/);
  });

  it("never says 'AI' beside a blank model name", () => {
    render(<ExplainerPanel data={{ ...llm, model: "" }} loading={false} error={false} onRetry={noop} />);
    expect(document.body.textContent).not.toMatch(/\bAI\b/);
    expect(screen.getByText("Summary written from the model's numbers")).toBeInTheDocument();
  });

  it("drops the age rather than quoting one it cannot read", () => {
    render(<ExplainerPanel data={{ ...llm, generated_at: "not-a-date" }} loading={false} error={false} onRetry={noop} />);
    // An unqualified "AI summary" with no recency is the failure this avoids.
    expect(document.body.textContent).not.toMatch(/\bAI\b/);
  });
});

describe("ExplainerPanel content", () => {
  it("two panels on one page each label their own section", () => {
    // A hard-coded heading id would be shared, and aria-labelledby would point
    // both sections at whichever heading came first.
    render(
      <>
        <ExplainerPanel data={llm} loading={false} error={false} onRetry={noop} />
        <ExplainerPanel data={llm} loading={false} error={false} onRetry={noop} />
      </>,
    );
    const sections = document.querySelectorAll("section[aria-labelledby]");
    expect(sections).toHaveLength(2);
    const ids = [...sections].map((s) => s.getAttribute("aria-labelledby"));
    expect(new Set(ids).size).toBe(2);
    for (const id of ids) {
      expect(document.getElementById(id!)?.textContent).toBe("In plain English");
    }
  });

  // The v1 `headline`/`sections` rendering these tests covered was removed
  // with the LegacyExplanation union arm: the panel renders verdicts now, and
  // a v1 body reaches no render branch. Deleted, not migrated; the factor
  // rows that replaced sections carry their own suite in FactorList.
});

describe("ExplainerPanel rebuilt picks", () => {
  const rebuilt: Explanation = { ...llm, sport: "nfl", pick_timing: "rebuilt" };

  it("repeats the site's own rebuilt status and says the pick is not counted", () => {
    render(<ExplainerPanel data={rebuilt} loading={false} error={false} onRetry={noop} />);
    // The same label the site's own StatusBadge shows, not a new wording: a
    // summary that called it something else would read as a second opinion.
    expect(screen.getByText("Rebuilt after kickoff")).toBeInTheDocument();
    expect(screen.getByText(/not counted/)).toBeInTheDocument();
  });

  it("an F1 session reads 'after the session', because that is the moment there", () => {
    // No `moment` prop: the sport alone must produce the wording. This package
    // owns that mapping, so it is what has to test it.
    render(<ExplainerPanel data={{ ...rebuilt, sport: "f1" }} loading={false} error={false} onRetry={noop} />);
    expect(screen.getByText("Rebuilt after the session")).toBeInTheDocument();
    expect(screen.getByText(/after the session started/)).toBeInTheDocument();
  });

  it("an NBA game reads 'after tip-off', because basketball says that", () => {
    render(<ExplainerPanel data={{ ...rebuilt, sport: "nba" }} loading={false} error={false} onRetry={noop} />);
    expect(screen.getByText("Rebuilt after tip-off")).toBeInTheDocument();
  });

  it("a site can still override the moment its own cards use", () => {
    render(
      <ExplainerPanel
        data={{ ...rebuilt, sport: "f1" }}
        loading={false}
        error={false}
        onRetry={noop}
        moment="kickoff"
      />,
    );
    expect(screen.getByText("Rebuilt after kickoff")).toBeInTheDocument();
  });

  it("says nothing about rebuilding when the pick was made in time", () => {
    render(<ExplainerPanel data={llm} loading={false} error={false} onRetry={noop} />);
    expect(screen.queryByText(/Rebuilt after/)).not.toBeInTheDocument();
    expect(screen.queryByText(/not counted/)).not.toBeInTheDocument();
  });

  it("still labels a rebuilt pick when the summary itself is templated", () => {
    // The status is a fact about the pick, not about who wrote the prose.
    render(
      <ExplainerPanel
        data={{ ...template, sport: "nfl", pick_timing: "rebuilt" }}
        loading={false}
        error={false}
        onRetry={noop}
      />,
    );
    expect(screen.getByText("Rebuilt after kickoff")).toBeInTheDocument();
  });
});

/** A minimal v2 body for the collapse tests: the collapsed toggle withholds
 *  the body, and the body is verdict + factors now, not headline + sections. */
const v2body: Explanation = {
  source: "template",
  model: "",
  generated_at: new Date(Date.now() - 4 * 60_000).toISOString(),
  sport: "pl",
  pick_timing: "pre_kickoff",
  verdict: "Arsenal are the pick, and the market roughly agrees.",
  band: "moderate",
  factors: [{ key: "result", direction: "neutral", headline: "Why", text: "The model has them at 48%." }],
};

describe("ExplainerPanel collapsed", () => {
  it("shows only the verdict, and offers a way in", () => {
    render(<ExplainerPanel data={v2body} loading={false} error={false} onRetry={noop} collapsed />);
    expect(screen.getByText(v2body.verdict)).toBeInTheDocument();
    // The body is withheld, not merely hidden behind a scroll.
    expect(screen.queryByText("The model has them at 48%.")).not.toBeInTheDocument();
    const toggle = screen.getByRole("button", { name: "Read the race story" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
  });

  it("expands on click and reports its state", async () => {
    render(<ExplainerPanel data={v2body} loading={false} error={false} onRetry={noop} collapsed />);
    const toggle = screen.getByRole("button", { name: "Read the race story" });
    await userEvent.click(toggle);
    expect(screen.getByText("The model has them at 48%.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Hide the race story" })).toHaveAttribute("aria-expanded", "true");
  });
});
