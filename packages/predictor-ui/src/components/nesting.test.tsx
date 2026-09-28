/**
 * No rendered output of this library may put an interactive element inside
 * another one.
 *
 * This exists because `MatchCard` did, and because *nothing caught it*. A
 * `<button>` inside the card's own `<button>` sat in the tree through three
 * tasks and a screenshot review, and it surfaced only because React happens to
 * log it — a warning, in test output, that a green suite scrolls past. The edit
 * was one conditional; the reason the defect can come back is that the next
 * `<a>` inside a `<button>` will be just as quiet.
 *
 * **Why the tree is walked rather than queried with `button button`.** Two
 * reasons, and the first is measured rather than argued. The HTML parser
 * *repairs* this: setting `innerHTML` to `<button><span><button>x</button></span></button>`
 * yields `<button><span></span></button><button>x</button>` — two siblings,
 * because a `button` start tag in body closes an open `button`. So an assertion
 * written against parsed markup can never see this defect, and would pass on a
 * page that has it. React builds its tree with `createElement`, which no parser
 * touches, which is why React can emit it at all and why its warning says
 * "This will cause a hydration error" — a browser parsing server-rendered
 * markup silently rearranges the nodes into siblings instead. The second reason
 * is that one rule has to cover `<a>` in `<button>`, `<button>` in `<a>` and
 * `role="button"` in `<button>`, and a descendant selector per pair would be
 * three rules that each cover one case. Walking ancestors covers the class.
 *
 * **What this does not cover, so the next person does not assume more than it
 * does.** It covers the states listed in `CASES` below and nothing else: add a
 * prop to a component, render a state nobody listed, and that state is
 * unchecked. It is a floor, not a proof. It is also a *DOM* assertion, so it
 * says nothing about whether an element is reachable by keyboard, correctly
 * named, or correctly described — `aria-hidden` on a focusable element, an
 * unlabelled control and a control with no handler all pass here. It does not
 * look at a consuming site's own markup, only at what this library renders.
 */
import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";

import {
  AppFrame,
  BandChip,
  EmptyState,
  ErrorState,
  ExplainerPanel,
  FactorList,
  KeyNumberTile,
  MatchCard,
  PanelHeading,
  ProbabilityBar,
  RecordStrip,
  RoundNavigator,
  Skeleton,
  StatTable,
  StatTile,
  StatusBadge,
  TeamChip,
} from "../index";
import type { Explanation, MarketTile, Segment } from "../index";

/** What counts as interactive, for the purpose of "one inside another".
 *
 *  Native controls first, then the ARIA roles that make a non-native element
 *  operable, then the two ways an author marks their own element focusable —
 *  which together catch the `<div onClick>` that `FactorList`'s own comment says
 *  its real-button assertion exists to catch.
 *
 *  Two exclusions, both deliberate. An `<a>` with no `href` is not a control: it
 *  is a placeholder, no browser makes it focusable, and treating it as one
 *  would report faults on markup that has none. And `role="img"`,
 *  `role="status"` and `role="alert"` are not in the list, which is why this
 *  library's own bar graphics and live regions do not trip it. */
const INTERACTIVE = [
  "a[href]",
  "button",
  "input",
  "select",
  "textarea",
  "summary",
  "[contenteditable]:not([contenteditable='false'])",
  "[tabindex]",
  "[role='button']",
  "[role='link']",
  "[role='checkbox']",
  "[role='radio']",
  "[role='switch']",
  "[role='tab']",
  "[role='menuitem']",
  "[role='menuitemcheckbox']",
  "[role='menuitemradio']",
  "[role='option']",
  "[role='slider']",
  "[role='spinbutton']",
  "[role='textbox']",
  "[role='combobox']",
  "[role='searchbox']",
  "[role='treeitem']",
].join(", ");

/** Every interactive element that has an interactive ancestor, as
 *  `<outer> > <inner>`. Ancestors are walked from the element outward and the
 *  walk stops at the first interactive one, so a card holding two segment
 *  labels is reported once per label and not once per ancestor pair. */
function nestingFaults(root: ParentNode): string[] {
  const faults: string[] = [];
  for (const inner of root.querySelectorAll(INTERACTIVE)) {
    for (let outer = inner.parentElement; outer; outer = outer.parentElement) {
      if (outer.matches(INTERACTIVE)) {
        faults.push(`${outer.tagName.toLowerCase()} > ${inner.tagName.toLowerCase()}`);
        break;
      }
    }
  }
  return faults;
}

/** An element, built the way React builds one. Never `innerHTML` — see the
 *  note at the top: the parser closes the outer button and the defect becomes
 *  unrepresentable, which would make these cases test nothing. */
function el(tag: string, attrs: Record<string, string> = {}, ...kids: Node[]): HTMLElement {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(attrs)) node.setAttribute(name, value);
  for (const kid of kids) node.appendChild(kid);
  return node;
}

const text = (s: string) => document.createTextNode(s);

describe("the nesting assertion is capable of catching the class", () => {
  // A rule that has only ever been pointed at one defect is one defect's rule.
  // These are the shapes it is claimed to catch, each built by hand so the claim
  // is checkable without a component that does the wrong thing on purpose.
  const FAULTS: [string, HTMLElement][] = [
    ["a button inside a button", el("button", {}, el("span", {}, el("button", {}, text("x"))))],
    ["an anchor inside a button", el("button", {}, el("a", { href: "/x" }, text("x")))],
    ["a button inside an anchor", el("a", { href: "/x" }, el("button", {}, text("x")))],
    ["a div pretending to be a button, inside a button", el("button", {}, el("div", { role: "button" }, text("x")))],
    ["a focusable div inside a button", el("button", {}, el("div", { tabindex: "0" }, text("x")))],
    ["an editable span inside a button", el("button", {}, el("span", { contenteditable: "true" }, text("x")))],
    ["a text input inside a button", el("button", {}, el("input", {}))],
    ["a select inside a button", el("button", {}, el("select", {}))],
    ["a disclosure summary inside a button", el("button", {}, el("details", {}, el("summary", {}, text("s"))))],
    ["a checkbox inside a link", el("a", { href: "/x" }, el("input", { type: "checkbox" }))],
    // Deep enough that a walk with the wrong boundary would stop one level early.
    ["a button two levels inside a button", el("button", {}, el("span", {}, el("em", {}, el("button", {}, text("x")))))],
  ];

  it("reports every one of them", () => {
    for (const [name, tree] of FAULTS) {
      expect(nestingFaults(tree), name).toHaveLength(1);
    }
  });

  it("leaves the shapes that are legal alone, so it is not crying wolf", () => {
    const CLEAN: [string, HTMLElement][] = [
      ["a button holding text and spans", el("button", {}, el("span", {}, text("x")))],
      ["two sibling buttons", el("div", {}, el("button"), el("button"))],
      ["a link beside a button", el("div", {}, el("a", { href: "/x" }, text("a")), el("button", {}, text("b")))],
      ["an href-less anchor inside a button", el("button", {}, el("a", {}, text("x")))],
      ["a role=img graphic", el("div", { role: "img" }, el("span"))],
      ["a role=status live region holding a control", el("div", { role: "status" }, el("button", {}, text("x")))],
      ["a role=alert region holding a control", el("div", { role: "alert" }, el("button", {}, text("x")))],
      ["a form control inside a label", el("label", {}, text("n"), el("input", {}))],
    ];
    for (const [name, tree] of CLEAN) {
      expect(nestingFaults(tree), name).toEqual([]);
    }
  });

  it("is not a descendant selector in disguise: the HTML parser would hide this", () => {
    // The measured reason the walk exists. Parse the nested button and the parser
    // repairs it into two SIBLINGS, so `tree.querySelectorAll("button button")`
    // finds nothing on markup that has the defect — a green assertion over a
    // broken page. Built with `createElement`, as React does, it nests.
    const parsed = document.createElement("div");
    parsed.innerHTML = "<button><span><button>x</button></span></button>";
    expect(parsed.querySelectorAll("button button")).toHaveLength(0);
    expect(parsed.querySelectorAll("button")).toHaveLength(2);

    const built = el("button", {}, el("span", {}, el("button", {}, text("x"))));
    expect(built.querySelectorAll("button button")).toHaveLength(1);
    expect(nestingFaults(built)).toEqual(["button > button"]);
  });

  it("catches a real component in the shape a future call site would produce", () => {
    // The other half of the `insideControl` case in `CASES`, and the reason that
    // prop is not redundant. `ProbabilityBar` derives its labels' element from
    // `onSegmentFocus`, which reads as though nesting inside a button were
    // unreachable by accident — it is not, because a component cannot see its own
    // ancestors, and this is the very component the green case there renders.
    // So the mistake is pinned with the real component rather than a hand-built
    // tree: pass a listener, wrap the bar in a button, and the sweep reports
    // `button > button` twice.
    //
    // Deliberately NOT in `CASES`: that list asserts "no faults", so a case
    // asserting a fault is reporting the rule rather than obeying it, and putting
    // it there means either a permanently red suite or an exception the next
    // person reads as permission.
    //
    // React logs this shape too, and its warning is caught here rather than
    // allowed to scroll past: a suite that prints a nesting warning on every run
    // teaches everyone to ignore nesting warnings, which is how the first one of
    // these sat in the tree through three tasks. Asserting it also pins the
    // consequence — this is not a style rule, it is markup a browser is entitled
    // to refuse.
    const said: string[] = [];
    const real = console.error;
    console.error = (...args: unknown[]) => said.push(args.map(String).join(" "));
    try {
      const faulted = render(
        <button type="button">
          <ProbabilityBar segments={NFL_BAR} onSegmentFocus={() => {}} />
        </button>,
      );
      expect(nestingFaults(faulted.container)).toEqual(["button > button", "button > button"]);

      // And the annotation is what changes it. Asserted here as well, so the prop
      // cannot be dropped in a refactor that leaves both cases still passing.
      const safe = render(
        <button type="button">
          <ProbabilityBar segments={NFL_BAR} onSegmentFocus={() => {}} insideControl />
        </button>,
      );
      expect(nestingFaults(safe.container)).toEqual([]);
    } finally {
      console.error = real;
    }
    // React's own text, format placeholders and all — the assertion is that it
    // flagged the nesting, not that it flagged it in our wording.
    expect(said.join("\n")).toMatch(/cannot contain a nested/);
  });
});

// ---------------------------------------------------------------- the sweep --

const NFL: Explanation = {
  verdict: "Baltimore is the pick, but the line is thinner than the number.",
  band: "moderate",
  pick: { label: "BAL" },
  factors: [
    { key: "moneyline", direction: "up", headline: "Model leans Baltimore", text: "The rating gap has held all week." },
    { key: "spread", direction: "down", headline: "The line asks more", text: "The market is asking for more than the gap is worth." },
  ],
  source: "llm",
  model: "nemotron-3.5-lightning",
  generated_at: new Date().toISOString(),
  sport: "nfl",
  pick_timing: "pre_kickoff",
};

const TILES: MarketTile[] = [
  { market: "moneyline", label: "Moneyline", value: "62%", sub: "win · BAL" },
  { market: "spread", label: "Spread", value: "BAL −2.5", sub: "model −3.4" },
];

const NFL_BAR: Segment[] = [
  { label: "KC", prob: 0.38, market: "moneyline" },
  { label: "BAL", prob: 0.62, market: "moneyline" },
];

const PL_BAR: Segment[] = [
  { label: "Arsenal", prob: 0.48, market: "result" },
  { label: "Draw", prob: 0.26, market: "result" },
  { label: "Chelsea", prob: 0.26, market: "result" },
];

const MARKET: Segment[] = [
  { label: "Arsenal", prob: 0.44 },
  { label: "Draw", prob: 0.25 },
  { label: "Chelsea", prob: 0.31 },
];

const RESTING = { loading: false, error: false, onRetry: () => {} };

/** A v1 body, typed through `Explanation` so the union arm is named rather than
 *  guessed at: on the union `.factors` does not exist, so a hand-built legacy
 *  answer has to carry `Common` too or it will not compile. */
const LEGACY: Explanation = {
  headline: "h",
  sections: [{ market: "m", title: "t", text: "x" }],
  source: "template",
  model: "",
  generated_at: new Date().toISOString(),
  sport: "nfl",
  pick_timing: "none",
};

const CARD = {
  left: { code: "TOT", name: "Tottenham" },
  right: { code: "AVL", name: "Aston Villa" },
  centre: "2–3",
  status: "called" as const,
  onOpen: () => {},
};

/** Every component the library exports, in the states that carry a control.
 *
 *  `controls` is the number of interactive elements the case must actually
 *  render, measured rather than estimated, so a case cannot pass by rendering
 *  nothing — which is how a sweep rots quietly: someone guts a component, the
 *  assertion still says "no nesting", and it now means nothing.
 *
 *  A count of 0 is a claim too, and two of them are the point of this task:
 *  **a bare `ProbabilityBar` has no controls at all**, and `MatchCard` has
 *  exactly one — itself. The §13c labels come back the moment a caller passes
 *  `onSegmentFocus`, which is the "with a highlight" case below. */
const CASES: { name: string; element: ReactElement; controls: number }[] = [
  // The reported defect. A card's bar inside a card's button.
  { name: "MatchCard with a bar", element: <MatchCard {...CARD} pick={{ label: "AVL", prob: 0.6 }} bar={[{ label: "TOT", prob: 0.4 }, { label: "AVL", prob: 0.6 }]} />, controls: 1 },
  { name: "MatchCard, no pick, with a bar", element: <MatchCard {...CARD} status="nopick" bar={[{ label: "TOT", prob: 0.4 }]} />, controls: 1 },
  { name: "MatchCard, compact, rebuilt", element: <MatchCard {...CARD} status="rebuilt" moment="tip-off" compact meta="AVL −2.5" />, controls: 1 },

  // The other surface the bar is on: §13c's, where the labels ARE controls.
  { name: "ProbabilityBar on its own", element: <ProbabilityBar segments={NFL_BAR} pick={{ label: "BAL" }} />, controls: 0 },
  { name: "ProbabilityBar with a market row", element: <ProbabilityBar segments={PL_BAR} legend={MARKET} pick={{ label: "Arsenal" }} />, controls: 0 },
  { name: "ProbabilityBar with a listener: its labels are controls again", element: <ProbabilityBar segments={NFL_BAR} onSegmentFocus={() => {}} />, controls: 2 },
  { name: "ProbabilityBar, three-way with a listener", element: <ProbabilityBar segments={PL_BAR} legend={MARKET} highlightKey="result" onSegmentFocus={() => {}} />, controls: 3 },
  { name: "ProbabilityBar expandable", element: <ProbabilityBar segments={PL_BAR} legend={MARKET} expandable />, controls: 1 },

  // The call site nobody has written yet, pinned before it is written.
  //
  // `MatchCard` is not evidence that a bar is safe inside a button: the card is a
  // button by its own design and will stay one, but nothing says every surface
  // that embeds a bar is. This is the shape a link-row, a fixture or a future
  // card produces, and the rule has to hold there too.
  //
  // **The assumption this case found broken.** It was added expecting to pass,
  // because `SegmentFigure`'s comment claims the unsafe answer is "unreachable by
  // accident" — a caller that wraps the bar in a button and forgets a flag gets
  // plain text. That is true of a caller that forgets the *listener*. It was never
  // true of a caller that passes one: a component cannot see its own ancestors,
  // and this case is `button > button` twice without the annotation. So the
  // guarantee needed a prop, and the case is here to hold it — `controls: 1`, not
  // 3, which fails on the arithmetic before anyone reads the fault list.
  {
    name: "a button wrapping a bar that has a listener",
    element: (
      <button type="button">
        <ProbabilityBar segments={NFL_BAR} onSegmentFocus={() => {}} insideControl />
      </button>
    ),
    controls: 1,
  },

  // The composition a site actually ships: a frame's links and tabs, and a
  // card, all on one page. The only place an `<a>` and a `<button>` meet.
  {
    name: "AppFrame with tabs, links and a card",
    element: (
      <AppFrame
        sport="nfl"
        sportName="NFL"
        sites={[{ sport: "pl", label: "PL", href: "/pl" }, { sport: "nfl", label: "NFL", href: "/nfl" }]}
        tabs={[{ id: "games", label: "Games" }, { id: "picks", label: "Picks" }]}
        activeTab="games"
        onTab={() => {}}
      >
        <MatchCard {...CARD} pick={{ label: "AVL", prob: 0.6 }} bar={[{ label: "TOT", prob: 0.4 }, { label: "AVL", prob: 0.6 }]} />
      </AppFrame>
    ),
    controls: 5,
  },

  { name: "RoundNavigator with everything", element: <RoundNavigator label="Week 5" canPrev canNext onPrev={() => {}} onNext={() => {}} onJumpToCurrent={() => {}} record={{ hits: 41, settled: 68, rebuilt: 2 }} />, controls: 3 },
  { name: "RoundNavigator at the ends", element: <RoundNavigator label="Week 5" canPrev={false} canNext={false} onPrev={() => {}} onNext={() => {}} />, controls: 2 },

  // The panel, in the states that draw a control.
  { name: "ExplainerPanel, v2, resting", element: <ExplainerPanel {...RESTING} data={NFL} tiles={TILES} segments={NFL_BAR} record={{ label: "Picks", hits: 41, settled: 68 }} />, controls: 4 },
  { name: "ExplainerPanel, collapsed", element: <ExplainerPanel {...RESTING} data={NFL} collapsed tiles={TILES} segments={NFL_BAR} />, controls: 1 },
  { name: "ExplainerPanel, expandable market row", element: <ExplainerPanel {...RESTING} data={NFL} segments={PL_BAR} legend={MARKET} expandable />, controls: 6 },
  { name: "ExplainerPanel, a legacy answer", element: <ExplainerPanel {...RESTING} data={LEGACY} />, controls: 0 },
  { name: "ExplainerPanel, error", element: <ExplainerPanel {...RESTING} error data={null} />, controls: 1 },

  { name: "FactorList, rows and a clamped sentence", element: <FactorList factors={NFL.factors} onSelect={() => {}} expandable />, controls: 4 },
  { name: "FactorList, headings only", element: <FactorList factors={NFL.factors} />, controls: 0 },

  {
    name: "StatTable, sortable with a detail row",
    element: (
      <StatTable
        rows={[{ name: "a", n: 1 }, { name: "b", n: 2 }]}
        columns={[{ key: "name", label: "Name", value: (r) => r.name }, { key: "n", label: "N", value: (r) => r.n, numeric: true, tooltip: "how many" }]}
        rowKey={(r) => r.name}
        caption="A table"
        expand={(r) => <span>{r.n} detail</span>}
      />
    ),
    controls: 4,
  },

  { name: "EmptyState with an action", element: <EmptyState message="Nothing yet." action={{ label: "Reload", onClick: () => {} }} />, controls: 1 },
  { name: "ErrorState", element: <ErrorState message="It did not come through." onRetry={() => {} } />, controls: 1 },
  { name: "Skeleton", element: <Skeleton label="Writing…" />, controls: 0 },

  // The parts with no control of their own, listed so their file being edited is
  // still covered rather than silently absent from the sweep.
  { name: "BandChip", element: <BandChip band="strong" />, controls: 0 },
  { name: "PanelHeading", element: <PanelHeading id="h">In plain English</PanelHeading>, controls: 0 },
  { name: "KeyNumberTile, highlighted", element: <KeyNumberTile tile={TILES[1]} highlighted />, controls: 0 },
  { name: "KeyNumberTile, absent market", element: <KeyNumberTile tile={{ market: "total", label: "", value: "" }} />, controls: 0 },
  { name: "RecordStrip", element: <RecordStrip label="Picks" hits={41} settled={68} />, controls: 0 },
  { name: "StatTile", element: <StatTile label="Edge" value="4.1%" sub="pts" />, controls: 0 },
  { name: "StatusBadge", element: <StatusBadge status="rebuilt" moment="tip-off" />, controls: 0 },
  { name: "TeamChip", element: <TeamChip code="AVL" name="Aston Villa" color="#E31837" />, controls: 0 },
];

describe("no component in this library nests one control inside another", () => {
  for (const { name, element, controls } of CASES) {
    it(name, () => {
      const { container, unmount } = render(element);
      // The invariant first, so its message is the one a reader is given when a
      // component really does nest something: "button > button" says what
      // happened, where the count below would only say the number moved.
      expect(nestingFaults(container), name).toEqual([]);
      // The non-vacuity half, second. Without it a component that stopped
      // rendering its control would make this case pass for a new and wrong
      // reason.
      expect(container.querySelectorAll(INTERACTIVE).length, `${name} rendered a different number of controls`).toBe(controls);
      unmount();
    });
  }
});
