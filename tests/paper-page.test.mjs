import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

// The paper-trading page. It is the one page in the hub that shows the
// ledger's own evidence, so the things it asserts about itself are about
// honesty rather than looks: no segment may be called "has an edge" below the
// gate, and every figure a reader sees has to be one the report actually
// carries.
const html = readFileSync(new URL("../paper.html", import.meta.url), "utf8");
const report = JSON.parse(
  readFileSync(new URL("../data/paper/report.json", import.meta.url), "utf8")
);

test("the page shows per-sport rows and one segment table", () => {
  assert.match(html, /id="sport-table"/);
  assert.match(html, /id="segment-table"/);
  // ONE table of segments: a second one would mean two places to read, and
  // the spec asks for one table with a sport filter.
  assert.equal((html.match(/id="segment-table"/g) || []).length, 1);
});

test("the segment table can be filtered by sport", () => {
  assert.match(html, /class="sport-filter"/);
  assert.match(html, /data-sport-filter="all"/);
  // The chips are buttons with an accessible group label, not divs.
  assert.match(html, /role="group" aria-label="Filter by sport"/);
  assert.match(html, /<button type="button" class="sport-chip/);
});

test("the filter hides rows rather than removing them", () => {
  // Removing rows would lose the reader's place and change the table's shape
  // as they filter.
  assert.match(html, /classList\.toggle\("is-hidden"/);
  assert.match(html, /tr\.is-hidden\s*\{\s*display:\s*none/);
});

test("the report carries the per-sport rows the page reads", () => {
  assert.ok(report.per_sport, "report.json has no per_sport");
  for (const [sport, row] of Object.entries(report.per_sport)) {
    assert.equal(row.sport, sport);
    for (const key of ["n_logged", "n_shadow", "n_settled", "pnl",
                       "mean_clv_cents", "n_clv", "share_clv_positive",
                       "excluded_legacy_total_rows", "qualifies_for_edge_claim"]) {
      assert.ok(key in row, `${sport} row has no ${key}`);
    }
  }
});

test("no sport below the gate is called as having an edge", () => {
  for (const [sport, row] of Object.entries(report.per_sport || {})) {
    if (row.qualifies_for_edge_claim) continue;
    assert.equal(row.has_edge_claim, false, `${sport} is below the gate but claims an edge`);
    assert.ok(row.why_not_yet, `${sport} is below the gate but gives no reason`);
  }
});

test("a sport below the gate says why in plain words", () => {
  for (const [sport, row] of Object.entries(report.per_sport || {})) {
    if (row.qualifies_for_edge_claim) continue;
    const why = row.why_not_yet || "";
    assert.ok(why.length > 0, `${sport} gives no reason`);
    // A reason that is only the gate's internal wording is not plain words:
    // it has to say what is missing in the reader's terms.
    assert.ok(
      /settled bets|interval|calibration|shadow|model/i.test(why),
      `${sport} reason is not in plain words: ${why}`
    );
  }
});

test("the page states that CLV is a leading indicator and not a gate", () => {
  // The report's CLV is beside the result, and the page must not let a reader
  // take it for a gate condition.
  assert.match(html, /leading indicator/i);
});

test("the gate is what the page says it is", () => {
  const min = report.gate.min_settled;
  assert.equal(min, 300);
  assert.match(html, new RegExp(`about ${min} settled paper bets`));
  assert.match(html, /cannot be judged yet/i);
});

test("the page carries the excluded-legacy note", () => {
  const excluded = report.totals.excluded_legacy_total_rows || 0;
  if (excluded > 0) {
    assert.match(html, /earlier total-points rows excluded/i);
  }
});
