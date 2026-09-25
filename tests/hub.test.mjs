import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");

test("links point at the VPS sites, not the retired Azure apps", () => {
  assert.doesNotMatch(html, /azurecontainerapps\.io/);
  for (const sub of ["pl", "f1", "sports", "nba"]) {
    assert.match(html, new RegExp(`href="https://${sub}\\.40-160-91-131\\.sslip\\.io"`));
  }
});

test("status labels are honest and copy is plain", () => {
  assert.doesNotMatch(html, /Work in progress/);
  assert.doesNotMatch(html, /walk-forward/);
  assert.doesNotMatch(html, /no login required/i);
  assert.match(html, /<span class="badge soon">Preseason<\/span>/);
  assert.equal((html.match(/class="badge live"/g) || []).length, 3);
});

test("badge text is at least 12px", () => {
  const badge = html.match(/\.badge\s*\{[^}]*font-size:\s*([\d.]+)rem/);
  assert.ok(badge && parseFloat(badge[1]) >= 0.75, `badge font-size ${badge && badge[1]}rem is under 0.75rem`);
});
