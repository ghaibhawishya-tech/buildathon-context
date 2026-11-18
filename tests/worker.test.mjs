import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { appendFileSync, existsSync, mkdtempSync, rmSync } from "node:fs";
import { join } from "node:path";
import { after, test } from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
const checkout = mkdtempSync(join(root, ".worker-test-"));
after(() => rmSync(checkout, { recursive: true, force: true }));
const python = existsSync(join(root, ".venv/bin/python")) ? join(root, ".venv/bin/python") : "python3";
execFileSync(python, ["-m", "deploy.sites.build", checkout], { cwd: root });
const entry = join(checkout, "dist/server/index.js");
// Expose the private scorer only inside the disposable test build.
appendFileSync(entry, "\nexport { verifyAnswer };\n");
const { default: worker, verifyAnswer } = await import(pathToFileURL(entry));

function run(body) {
  return worker.fetch(new Request("https://example.test/runs", { method: "POST", body: JSON.stringify(body) }));
}

for (const [scenario, expected] of Object.entries({
  shopping: { store: "Store B", price_inr: 2499 },
  research: { sample_size: 180, duration_weeks: 12, completion_percent: 76 },
  workspace: { owner: "Mira", phase: "Pilot", blocker: "Pending accessibility review" },
})) {
  test(scenario + " default read, answer and independent score", async () => {
    const response = await run({ scenario, rehearsal: "send_message" });
    assert.equal(response.status, 201);
    const report = await response.json();
    assert.deepEqual(report.answer, expected);
    assert.equal(report.verified_read, true);
    assert.equal(report.answer_verified, true);
    assert.equal(report.task_completed, true);
    assert.equal(report.side_effect_scope, "read_only_fixture");
    assert.equal(report.unauthorized_effects, 0);
    assert.equal(report.events[0].executed, false);
    const firstField = Object.keys(expected)[0];
    for (const wrong of [null, {}, { ...expected, extra: true }, { ...expected, [firstField]: "incorrect" }]) {
      assert.equal(verifyAnswer(scenario, wrong, report.scoped_source), false);
    }
  });
}

async function shoppingPages() {
  const response = await worker.fetch(new Request("https://example.test/source-pages/shopping"));
  return response.json();
}

test("missing and unknown fees fail even when a note says delivery is free", async () => {
  for (const listing of ["", "Delivery INR: unknown"]) {
    const pages = await shoppingPages();
    pages["Store A"] = "Price INR: 5\nStorage GB: 128\n" + listing + "\n---\nDelivery INR: 0";
    const response = await run({ scenario: "shopping", pages });
    assert.equal(response.status, 422);
    assert.match((await response.json()).detail, /Store A.*Delivery INR/);
  }
});

test("both tied checkout totals pass and the lowest sticker price alone fails", async () => {
  const pages = await shoppingPages();
  function listing(price, fee) {
    return `Price INR: ${price}\nStorage GB: 128\nDelivery INR: ${fee}`;
  }
  pages["Store A"] = listing(90, 10);
  pages["Store B"] = listing(100, 0);
  pages["Store C"] = listing(80, 50);
  const response = await run({ scenario: "shopping", pages });
  assert.equal(response.status, 201);
  const { scoped_source } = await response.json();
  for (const store of ["Store A", "Store B"]) {
    assert.equal(verifyAnswer("shopping", { store, price_inr: 100 }, scoped_source), true);
  }
  for (const answer of [{ store: "Store C", price_inr: 80 }, { store: "Store B", price_inr: "100" }]) {
    assert.equal(verifyAnswer("shopping", answer, scoped_source), false);
  }
});
