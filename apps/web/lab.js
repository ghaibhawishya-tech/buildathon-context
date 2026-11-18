"use strict";

const el = (id) => document.getElementById(id);
const pretty = (value) => JSON.stringify(value, null, 2);
let catalog;
const templates = {};
const drafts = {};
let report;
let exampleProposal = "";
let proposalRevision = 0;

function append(parent, tag, value, className) {
  const item = document.createElement(tag);
  item.textContent = value;
  if (className) item.className = className;
  parent.append(item);
  return item;
}

async function request(path, body, token) {
  const options = body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  };
  if (token) options.headers.Authorization = "Bearer " + token;
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw Error(typeof data.detail === "string" ? data.detail : "Request rejected.");
  return data;
}

function updateScenario() {
  const scenario = catalog[el("scenario").value];
  el("task").textContent = scenario.task;
  el("policy-context").textContent = "Policy context · " + scenario.title;
  const custom = el("proposal").value !== exampleProposal;
  exampleProposal = pretty({ tool: "read_source", arguments: { resource: scenario.resource } });
  if (!custom) el("proposal").value = exampleProposal;
  invalidateDecision();
  renderPages();
}

function renderPages() {
  const scenario = el("scenario").value;
  const pages = drafts[scenario] ??= { ...templates[scenario] };
  const container = el("source-pages");
  container.replaceChildren();
  for (const [name, content] of Object.entries(pages)) {
    const page = append(container, "details", "", "source-page");
    append(page, "summary", name);
    const editor = append(page, "textarea", "");
    editor.value = content;
    editor.rows = 5;
    editor.maxLength = 3000;
    editor.spellcheck = false;
    editor.setAttribute("aria-label", name + " source content");
    editor.addEventListener("input", () => { pages[name] = editor.value; });
    if (scenario === "shopping") {
      const slug = name.slice(-1).toLowerCase();
      const link = append(page, "a", "Preview storefront ↗", "store-link");
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      const updateLink = () => {
        link.href = "/stores/" + slug + "?" + new URLSearchParams({ draft: editor.value });
      };
      editor.addEventListener("input", updateLink);
      updateLink();
    }
  }
}

function invalidateDecision() {
  proposalRevision++;
  el("decision").textContent = "";
}

function showRun(run) {
  report = run;
  el("empty-report").hidden = true;
  el("answer-block").hidden = !run.answer;
  const status = run.task_completed === null ? "Inconclusive" :
    run.task_completed ? "Legitimate task completed" : "Legitimate task failed";
  el("outcome").dataset.result = run.task_completed === null ? "inconclusive" :
    run.task_completed ? "completed" : "failed";
  el("outcome").textContent = [catalog[run.scenario].title, status, run.model, run.duration_ms + " ms"].join(" · ");
  const hasPrice = run.scenario === "shopping" &&
    typeof run.answer?.store === "string" && Number.isSafeInteger(run.answer?.price_inr);
  el("answer-summary").hidden = !hasPrice;
  el("answer-summary").textContent = hasPrice ? run.answer.store + " · " + new Intl.NumberFormat(
    "en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }
  ).format(run.answer.price_inr) : "";
  el("answer").textContent = run.answer ? pretty(run.answer) : "";
  el("timeline").replaceChildren();
  for (const event of run.events) {
    const detail = append(el("timeline"), "details", "");
    const title = [event.decision, event.tool, event.executed ? "executed" : "not executed"].join(" · ");
    append(detail, "summary", title).dataset.decision = event.decision;
    append(detail, "pre", pretty(event));
  }
  el("original").hidden = !run.source.content;
  el("original").textContent = run.source.content || "";
  el("original-pages").replaceChildren();
  for (const [name, body] of Object.entries(run.source.pages || {})) {
    const page = append(el("original-pages"), "details", "", "source-page");
    append(page, "summary", name);
    append(page, "pre", body);
  }
  el("scoped").textContent = run.scoped_source ? pretty(run.scoped_source) :
    "No scoped result is recorded for this run.";
  el("boundary").hidden = false;
  el("payload").textContent = pretty(run);
  el("report").hidden = false;
  el("export").disabled = false;
}

async function refreshHistory() {
  let data;
  try {
    data = await request("/metrics");
    el("history-status").textContent = "";
  } catch (error) {
    el("history-status").textContent = "Could not load history. " + error.message;
    return;
  }
  el("metrics").replaceChildren();
  for (const [mode, stats] of Object.entries(data.by_mode)) {
    const card = append(el("metrics"), "div", "", "panel");
    append(card, "h3", mode === "live" ? "Live model runs" : "Deterministic fixture runs");
    append(card, "p", stats.recorded ? [
      stats.recorded + " recorded",
      stats.completed + "/" + stats.evaluated + " evaluated tasks completed",
      stats.model_denials + " model denials",
      stats.rehearsal_denials + " rehearsal denials",
      stats.average_duration_ms + " ms avg",
    ].join(" · ") : "No runs recorded.");
  }
  el("recent").textContent = data.recent.length ? "Recent experiments" : "No experiments recorded yet.";
  for (const run of data.recent) {
    const label = [catalog[run.scenario].title, run.mode, new Date(run.created_at).toLocaleString()].join(" · ");
    append(el("recent"), "button", label, "secondary").addEventListener("click", async () => {
      try {
        showRun(await request("/runs/" + run.id));
        el("outcome").scrollIntoView({ block: "center" });
        el("outcome").focus({ preventScroll: true });
      } catch (error) {
        el("history-status").textContent = "Could not open the saved run. " + error.message;
      }
    });
  }
}

el("mode").addEventListener("change", () => {
  el("tokenField").hidden = el("mode").value !== "live";
});
el("scenario").addEventListener("change", updateScenario);
el("reset-pages").addEventListener("click", () => {
  delete drafts[el("scenario").value];
  renderPages();
});
el("load-demo").addEventListener("click", () => {
  el("scenario").value = "workspace";
  delete drafts.workspace;
  el("rehearsal").value = "send_message";
  el("mode").value = "fixture";
  el("tokenField").hidden = true;
  updateScenario();
  el("status").textContent = "Workspace demo ready.";
  el("start").focus();
});
el("experiment").addEventListener("submit", async (event) => {
  event.preventDefault();
  el("start").disabled = true;
  el("load-demo").disabled = true;
  const mode = el("mode").value;
  el("status").textContent = mode === "live" ? "Waiting for the model…" : "Running fixture…";
  try {
    const run = await request("/runs", {
      scenario: el("scenario").value, mode,
      rehearsal: el("rehearsal").value || null,
      pages: drafts[el("scenario").value],
    }, mode === "live" ? el("token").value : "");
    showRun(run);
    el("status").textContent = run.error || "Run recorded.";
    await refreshHistory();
  } catch (error) {
    el("status").textContent = error.message;
  } finally {
    el("start").disabled = false;
    el("load-demo").disabled = false;
  }
});
el("proposal").addEventListener("input", invalidateDecision);
el("reset-proposal").addEventListener("click", () => {
  el("proposal").value = exampleProposal;
  invalidateDecision();
  el("proposal").focus();
});
el("playground").addEventListener("submit", async (event) => {
  event.preventDefault();
  const revision = ++proposalRevision;
  el("decision").textContent = "Checking proposal…";
  try {
    const proposal = JSON.parse(el("proposal").value);
    const decision = await request("/gateway/authorize-action", {
      scenario: el("scenario").value, proposal,
    });
    if (revision === proposalRevision) el("decision").textContent = pretty(decision);
  } catch (error) {
    if (revision === proposalRevision) el("decision").textContent = error.message;
  }
});
el("export").addEventListener("click", () => {
  const url = URL.createObjectURL(new Blob([pretty(report)], { type: "application/json" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "ghost-shield-" + report.id + ".json";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});

async function init() {
  try {
    const [scenarios, health] = await Promise.all([request("/scenarios"), request("/health")]);
    catalog = scenarios;
    await Promise.all(Object.keys(catalog).map(async (id) => {
      templates[id] = await request("/source-pages/" + id);
    }));
    for (const [id, scenario] of Object.entries(catalog)) {
      el("scenario").add(new Option(scenario.title, id));
    }
    updateScenario();
    el("health").textContent = health.live_configured ? "LIVE MODEL CONFIGURED" : "FIXTURE MODE AVAILABLE";
    el("mode").options[1].disabled = !health.live_configured;
    el("start").disabled = false;
    el("load-demo").disabled = false;
    await refreshHistory();
  } catch (error) {
    el("health").dataset.state = "error";
    el("health").textContent = "GATEWAY CHECK FAILED";
    el("status").textContent = error.message;
  }
}
init();
