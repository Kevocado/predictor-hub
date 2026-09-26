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
    expect(screen.getByRole("alert")).toBeInTheDocument();
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
});

describe("ExplainerPanel content", () => {
  it("leads with the headline under a heading that says what this is", () => {
    render(<ExplainerPanel data={llm} loading={false} error={false} onRetry={noop} />);
    expect(screen.getByRole("heading", { name: "In plain English" })).toBeInTheDocument();
    expect(screen.getByText(llm.headline)).toBeInTheDocument();
  });

  it("renders every section as a titled block of prose", () => {
    render(<ExplainerPanel data={llm} loading={false} error={false} onRetry={noop} />);
    for (const section of llm.sections) {
      const title = screen.getByRole("heading", { name: section.title, level: 4 });
      expect(title).toBeInTheDocument();
      expect(screen.getByText(section.text)).toBeInTheDocument();
    }
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
    render(
      <ExplainerPanel
        data={{ ...rebuilt, sport: "f1" }}
        loading={false}
        error={false}
        onRetry={noop}
        moment="the session"
      />,
    );
    expect(screen.getByText("Rebuilt after the session")).toBeInTheDocument();
    expect(screen.getByText(/after the session started/)).toBeInTheDocument();
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
