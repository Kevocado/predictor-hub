import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ExplainerPanel, type Explanation } from "./ExplainerPanel";

const llm: Explanation = {
  headline: "Sunderland are the slight favourites, but this is the closest thing to a coin flip all week.",
  sections: [
    { market: "result", title: "Why Sunderland", text: "They have won three of five and the model has them at 57%." },
    { market: "total_goals", title: "Expect a tight one", text: "The model puts 2.9 goals on the game, so under 2.5 is the safer side." },
  ],
  source: "llm",
  model: "gpt-4o-mini",
  generated_at: new Date(Date.now() - 4 * 60_000).toISOString(),
  sport: "pl",
  pick_timing: "pre_kickoff",
};

const template: Explanation = {
  headline: "Sunderland win, at 57%.",
  sections: [{ market: "result", title: "The numbers", text: "Home 57%, draw 23%, away 20%." }],
  source: "template",
  model: "template",
  generated_at: new Date(Date.now() - 4 * 60_000).toISOString(),
  sport: "pl",
  pick_timing: "pre_kickoff",
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
  it("leads with the headline under a heading that says what this is", () => {
    render(<ExplainerPanel data={llm} loading={false} error={false} onRetry={noop} />);
    expect(screen.getByRole("heading", { name: "In plain English" })).toBeInTheDocument();
    expect(screen.getByText(llm.headline)).toBeInTheDocument();
  });

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

  it("renders every section as a titled block of prose", () => {
    render(<ExplainerPanel data={llm} loading={false} error={false} onRetry={noop} />);
    for (const section of llm.sections) {
      const title = screen.getByRole("heading", { name: section.title, level: 4 });
      expect(title).toBeInTheDocument();
      expect(screen.getByText(section.text)).toBeInTheDocument();
    }
  });

  it("two sections with the same market and title both render, without a React key warning", () => {
    // validate.py bounds a title's length but not its uniqueness, so a model
    // can return two "Trust" sections. Keying on market+title alone logged a
    // duplicate-key error in the reader's console.
    const error = vi.spyOn(console, "error").mockImplementation(() => {});
    const doubled = {
      ...llm,
      sections: [
        { market: "trust", title: "Trust", text: "First read of it." },
        { market: "trust", title: "Trust", text: "Second read of it." },
      ],
    };
    render(<ExplainerPanel data={doubled} loading={false} error={false} onRetry={noop} />);
    expect(screen.getByText("First read of it.")).toBeInTheDocument();
    expect(screen.getByText("Second read of it.")).toBeInTheDocument();
    expect(error.mock.calls.flat().join(" ")).not.toMatch(/same key|unique "key"/i);
  });

  it("a section with no title still shows its text, with no empty heading", () => {
    // _clean coerces a missing title to "", so an empty <h4> is reachable.
    const untitled = { ...llm, sections: [{ market: "result", title: "", text: "Just the prose." }] };
    render(<ExplainerPanel data={untitled} loading={false} error={false} onRetry={noop} />);
    expect(screen.getByText("Just the prose.")).toBeInTheDocument();
    expect(screen.queryAllByRole("heading", { level: 4 })).toHaveLength(0);
  });
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

describe("ExplainerPanel collapsed", () => {
  it("shows only the headline, and offers a way in", () => {
    render(<ExplainerPanel data={llm} loading={false} error={false} onRetry={noop} collapsed />);
    expect(screen.getByText(llm.headline)).toBeInTheDocument();
    // The body is withheld, not merely hidden behind a scroll.
    expect(screen.queryByText(llm.sections[0].text)).not.toBeInTheDocument();
    const toggle = screen.getByRole("button", { name: "Read the race story" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
  });

  it("expands on click and reports its state", async () => {
    render(<ExplainerPanel data={llm} loading={false} error={false} onRetry={noop} collapsed />);
    const toggle = screen.getByRole("button", { name: "Read the race story" });
    await userEvent.click(toggle);
    expect(screen.getByText(llm.sections[0].text)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Hide the race story" })).toHaveAttribute("aria-expanded", "true");
  });
});
