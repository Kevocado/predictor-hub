/** FixtureExplainer — the panel, three states.
 *
 *  The default state is the flow: an instant, local description built from facts
 *  the site already has, with no request made. The AI summary is behind a
 *  button, so nothing is spent until a reader asks. When the button's request
 *  resolves, the summary swaps in over a flow that never unmounts — there is no
 *  frame in which the panel is empty. When the request fails, the flow is still
 *  on screen and the button offers a retry.
 *
 *  The flow is always mounted. It is the one state that is always true, and
 *  keeping it mounted is what "the flow does not flicker away" means: the
 *  summary appears above it, not instead of it after a gap.
 */
import { useState } from "react";
import { FixtureFlow, type FlowState } from "./FixtureFlow";
import { SummaryButton } from "./SummaryButton";
import { ExplainerPanel, type Explanation } from "./ExplainerPanel";

/** A summary as the service sends it: a v2 answer, plus the optional news date.
 *  The news date arrives with the summary body; when it is absent the element is
 *  omitted entirely, so the panel ships before the service sends the field. */
export type Summary = Explanation & { news_date?: string };

/** The panel's three states. `unavailable` differs from `flow` only in what the
 *  button offers: a retry, rather than a first ask. */
type PanelState = "flow" | "summary" | "unavailable";

export interface FixtureExplainerProps {
  sport: string;
  state: FlowState;
  bundle: any;
  /** The panel's request function for the AI summary. Passed to both children;
   *  the flow never calls it. */
  request: () => Promise<unknown>;
}

/** The AI prose, rendered from the summary the button fetched. Reuses the
 *  existing panel so the verdict, band, factors and footer are the same ones
 *  every site already shows. */
function SummaryView({ summary }: { summary: Summary }) {
  return (
    <div className="flex flex-col gap-3" data-testid="fixture-summary">
      <ExplainerPanel data={summary} loading={false} error={false} onRetry={() => {}} />
      {summary.news_date && (
        <p className="text-xs text-pr-text-faint" data-testid="news-date">
          Team news from {summary.news_date}
        </p>
      )}
    </div>
  );
}

export function FixtureExplainer({ sport, state, bundle, request }: FixtureExplainerProps) {
  const [panelState, setPanelState] = useState<PanelState>("flow");
  const [summary, setSummary] = useState<Summary | null>(null);

  const handleSummary = (s: Explanation) => {
    // The button has already validated the shape; the news date rides along.
    setSummary(s as Summary);
    setPanelState("summary");
  };

  const handleUnavailable = () => {
    setPanelState("unavailable");
  };

  return (
    <div className="flex flex-col gap-3" data-testid="fixture-explainer">
      {panelState === "summary" && summary && <SummaryView summary={summary} />}
      <FixtureFlow sport={sport} state={state} bundle={bundle} request={request} />
      {panelState !== "summary" && (
        <SummaryButton
          request={request}
          onSummary={handleSummary}
          onUnavailable={handleUnavailable}
          label={panelState === "unavailable" ? "Try again" : "Get the AI summary"}
        />
      )}
    </div>
  );
}
