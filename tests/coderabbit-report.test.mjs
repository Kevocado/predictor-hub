import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const script = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "scripts", "lib", "coderabbit_report.py");
const run = (comments) => spawnSync("python3", [script, ""], { input: JSON.stringify(comments), encoding: "utf8" });

const finding = (id, sev = "Major") => ({ id, user: { login: "coderabbitai[bot]" }, body: `**x** | **${sev}** | **y**\n\nSomething.`, path: "a/b.py", line: 3, html_url: "u" });
const reply = (id, to, body) => ({ id, in_reply_to_id: to, user: { login: "coderabbitai[bot]" }, body });
const human = (id, to, body) => ({ id, in_reply_to_id: to, user: { login: "Kevocado" }, body });

test("an open Major fails the gate", () => {
  assert.equal(run([finding(1)]).status, 2);
});

test("a Major CodeRabbit itself resolved no longer fails the gate", () => {
  assert.equal(run([finding(1), reply(2, 1, "Re-checked.\n\n\u2705 Review thread resolved.")]).status, 0);
});

test("the reviewer saying it is fixed does NOT clear a Major", () => {
  assert.equal(run([finding(1), human(2, 1, "verified fixed, please resolve")]).status, 2);
});

test("a CodeRabbit reply that does not resolve the thread does not clear it", () => {
  assert.equal(run([finding(1), reply(2, 1, "Still not fixed: line 57 writes in place.")]).status, 2);
});

test("only the resolved Major is cleared; another open one still fails", () => {
  assert.equal(run([finding(1), finding(3), reply(2, 1, "Review thread resolved.")]).status, 2);
});

test("replies are not counted as findings", () => {
  const r = run([finding(1), reply(2, 1, "**Critical** words in a reply. Review thread resolved.")]);
  assert.equal(r.status, 0);
  assert.match(r.stdout, /1 inline finding/);
});
