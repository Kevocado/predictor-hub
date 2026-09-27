/**
 * A merge to main must publish the landing page to the VPS.
 *
 * This repo had one workflow and it was Azure Static Web Apps, reachable only
 * by hand. So a merge published nothing: the landing page was updated by
 * someone remembering to run `bin/deploy hub`.
 *
 * The contract is asserted in the five site repos as
 * `tests/test_deploy_workflow.py`, and duplicated rather than shared because
 * there is no shared test runner between this repo (node:test) and five pytest
 * repos. A deploy guard that exists in five of six is a guard that exists in
 * five of six.
 *
 * Two things are deliberately different here. There is no `build` job and no
 * image: Caddy serves this repo's index.html off disk. And there is no paths
 * filter: every tracked file in this repo is served content, and nothing here
 * is generated or polled, so a filter would only create a way to change the
 * site without deploying it. Both are asserted below, so "add a filter like
 * the others" has to be a decision rather than a copy-paste.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const REPO = join(dirname(fileURLToPath(import.meta.url)), "..");
const WORKFLOW_DIR = join(REPO, ".github", "workflows");
const WORKFLOW = join(WORKFLOW_DIR, "deploy.yml");
const AZURE_WORKFLOW = join(WORKFLOW_DIR, "azure-static-web-apps-brave-moss-064ee9b0f.yml");

const GATE_VPS = "vars.VPS_HOST != ''";
const GATE_AZURE = "vars.DEPLOY_AZURE == 'true'";

const text = () => readFileSync(WORKFLOW, "utf8");

/** The `jobs:` block as {name: body}, so a gate can be read per job. */
function jobs(src) {
  const out = {};
  let name = null;
  let buf = [];
  let inJobs = false;
  for (const line of src.split("\n")) {
    if (/^jobs:[ \t]*$/.test(line)) {
      inJobs = true;
      continue;
    }
    if (!inJobs) continue;
    const m = /^ {2}([A-Za-z0-9_-]+):[ \t]*$/.exec(line);
    if (m) {
      if (name !== null) out[name] = buf.join("\n");
      name = m[1];
      buf = [];
    } else if (name !== null) {
      buf.push(line);
    }
  }
  if (name !== null) out[name] = buf.join("\n");
  return out;
}

const vpsJob = (src) => {
  const j = jobs(src);
  const found = Object.entries(j).filter(([, b]) => b.includes("vars.VPS_HOST")).map(([n]) => n);
  assert.equal(found.length, 1, `expected exactly one VPS job, found [${found}]`);
  return j[found[0]];
};

test("the deploy workflow exists", () => {
  assert.ok(existsSync(WORKFLOW), `${WORKFLOW} is missing; a merge publishes nothing`);
  assert.ok(text().length > 300, "the workflow looks like a stub");
});

test("a merge to main triggers it, and it can still be run by hand", () => {
  const src = text();
  assert.match(src, /^[ \t]+push:[ \t]*$/m, "the workflow does not run on push");
  assert.match(src, /^[ \t]+branches:[ \t]*\[?[ \t]*main/m, "the push trigger is not limited to main");
  assert.match(src, /^[ \t]+workflow_dispatch:/m, "workflow_dispatch is gone, so a deploy cannot be run by hand");
});

test("it has no paths filter, because every tracked file here is served", () => {
  // A filter copied from a site repo would be a way to change the landing page
  // without deploying it. If this repo ever gains generated or polled data, that
  // becomes the right thing to do -- and then this test should change with it.
  assert.ok(
    !/^[ \t]+paths:/m.test(text()),
    "the hub workflow has a paths filter; the site repos need one and this does not",
  );
});

test("it has no build job and pushes no image", () => {
  // Caddy serves index.html off disk. A build job here would push an image
  // nothing pulls.
  const src = text();
  assert.ok(!("build" in jobs(src)), "the hub workflow has a build job; it deploys no image");
  assert.ok(!/docker (build|push)/.test(src), "the hub workflow builds or pushes an image");
  assert.ok(!/packages: write/.test(src), "the hub workflow requests packages: write but pushes nothing");
});

test("it reaches the VPS and asks bin/deploy for the hub", () => {
  const body = vpsJob(text());
  const expected = "ssh deploy@${{ vars.VPS_HOST }} hub ${{ github.sha }}";
  assert.ok(body.includes(expected), `the deploy command must be exactly: ${expected}`);
});

test("it is gated on VPS_HOST and serialised against itself", () => {
  const body = vpsJob(text());
  const gate = new RegExp(`^[ \\t]+if:[ \\t]*${GATE_VPS.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}[ \\t]*$`, "m");
  assert.match(body, gate, `the VPS job must be gated on \`${GATE_VPS}\``);
  assert.match(
    body,
    /^[ \t]+concurrency:[ \t]*vps-deploy-hub[ \t]*$/m,
    "the VPS job must serialise on `concurrency: vps-deploy-hub`: two repos deploying at once race on /opt/stack/.env",
  );
});

test("it verifies the host before connecting", () => {
  const body = vpsJob(text());
  assert.match(body, /\$\{\{[ \t]*secrets\.VPS_SSH_KEY[ \t]*\}\}/, "VPS_SSH_KEY is never used");
  assert.match(
    body,
    /\$\{\{[ \t]*secrets\.VPS_KNOWN_HOSTS[ \t]*\}\}/,
    "VPS_KNOWN_HOSTS is never used, so the host is not verified",
  );
  assert.ok(
    body.indexOf("known_hosts") < body.indexOf("ssh deploy@"),
    "known_hosts is written after the ssh call, so the job hangs on a host prompt",
  );
});

test("Azure stays off unless asked, in both workflows", () => {
  // The Azure Static Web Apps workflow is legacy and being cut over. Gated on
  // `== 'true'` and not `!= 'false'`: the failing-open form turns Azure back on
  // for any repo that has not explicitly set the variable.
  for (const path of [WORKFLOW, AZURE_WORKFLOW]) {
    const src = readFileSync(path, "utf8");
    assert.ok(
      !src.includes("DEPLOY_AZURE != 'false'"),
      `${path}: \`vars.DEPLOY_AZURE != 'false'\` fails OPEN — any repo that has not set the variable turns Azure back on`,
    );
  }
  const azure = readFileSync(AZURE_WORKFLOW, "utf8");
  for (const m of azure.matchAll(/^[ \t]+if:[ \t]*(.*)$/gm)) {
    assert.ok(
      m[1].includes(GATE_AZURE),
      `${AZURE_WORKFLOW}: a job gate is \`${m[1].trim()}\`, which is not gated on \`${GATE_AZURE}\``,
    );
  }
  assert.ok(
    !existsSync(join(WORKFLOW_DIR, "deploy-azure.yml")),
    "an Azure-only deploy workflow is back; it should be the gated job inside deploy.yml",
  );
});

test("no secret material, and no secret reaches a log line", () => {
  for (const path of [WORKFLOW, AZURE_WORKFLOW]) {
    const src = readFileSync(path, "utf8");
    for (const m of src.matchAll(/secrets\.([A-Za-z0-9_]+)/g)) {
      assert.match(m[1], /^[A-Z0-9_]+$/, `${path}: secret ${m[1]} is not a UPPER_CASE name`);
    }
    for (const marker of ["BEGIN OPENSSH PRIVATE KEY", "BEGIN RSA PRIVATE KEY", "ghp_", "github_pat_"]) {
      assert.ok(!src.includes(marker), `${path}: contains credential material (${marker})`);
    }
    for (const line of src.split("\n")) {
      assert.ok(
        !(line.includes("secrets.") && (line.includes("echo") || line.includes("::"))),
        `${path}: a secret reaches the log: ${line.trim()}`,
      );
    }
  }
});

test("the YAML indentation is sane", () => {
  // Added to the site repos after a generated workflow put every Azure step two
  // spaces too deep, nesting them under the preceding step. Nothing noticed
  // except actionlint, which is required for that reason — but a merge should
  // not be the first place invalid YAML is found.
  const src = text();
  src.split("\n").forEach((line, i) => {
    const stripped = line.replace(/^ +/, "");
    const indent = line.length - stripped.length;
    if (stripped) assert.equal(indent % 2, 0, `line ${i + 1} is indented ${indent} spaces: ${JSON.stringify(line)}`);
  });
  for (const m of src.matchAll(/^[ \t]+steps:[ \t]*$/gm)) {
    const first = src.slice(m.index + m[0].length).replace(/^\n/, "").split("\n")[0] ?? "";
    assert.ok(first.startsWith("      - "), `a \`steps:\` block whose first item is not at six spaces: ${JSON.stringify(first)}`);
  }
});

test("every check above can fail", () => {
  // A guard that cannot fail is not a guard. Each mutation must be a string
  // that appears exactly once, or it is not breaking what it claims to.
  const good = text();
  const cases = [
    ["workflow_dispatch:", "workflow_DISABLED:", (s) => assert.match(s, /^[ \t]+workflow_dispatch:/m)],
    [
      "hub ${{ github.sha }}",
      "hub",
      (s) => assert.ok(vpsJob(s).includes("hub ${{ github.sha }}"), "deploy command"),
    ],
    [
      "vars.VPS_HOST != ''",
      "vars.VPS_HOST == ''",
      (s) => assert.match(vpsJob(s), /^[ \t]+if:[ \t]*vars\.VPS_HOST != ''[ \t]*$/m),
    ],
    ["vps-deploy-hub", "vps-deploy-hubb", (s) => assert.match(vpsJob(s), /^[ \t]+concurrency:[ \t]*vps-deploy-hub[ \t]*$/m)],
    [
      "secrets.VPS_SSH_KEY",
      "secrets.vps_ssh_key",
      (s) => {
        for (const m of s.matchAll(/secrets\.([A-Za-z0-9_]+)/g)) assert.match(m[1], /^[A-Z0-9_]+$/);
      },
    ],
  ];
  for (const [from, to, check] of cases) {
    assert.equal(
      good.split(from).length - 1,
      1,
      `the mutation ${from} is not unique, so breaking one copy leaves the check satisfied by another`,
    );
    check(good); // the real file satisfies it
    assert.throws(() => check(good.replace(from, to)), `a check passed with ${from} broken`);
  }
});

test("no other workflow commits a path that would loop the deploy", () => {
  // Derived from the other workflows rather than a hand-written list, so a new
  // refresh job cannot quietly start publishing on every run.
  for (const name of readdirSync(WORKFLOW_DIR)) {
    if (name === "deploy.yml" || !/\.ya?ml$/.test(name)) continue;
    const body = readFileSync(join(WORKFLOW_DIR, name), "utf8").replace(/\\\n/g, " ");
    for (const m of body.matchAll(/git add\s+(.*)/g)) {
      for (const token of m[1].split(/\s+/)) {
        const p = token.replace(/^['"]|['"]$/g, "");
        if (p.startsWith("-") || (!p.includes("/") && !p.endsWith(".json"))) continue;
        assert.fail(`${name} commits ${p}. This repo has no paths filter, so that would publish on every refresh.`);
      }
    }
  }
});
