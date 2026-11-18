"use strict";

const el = (id) => document.getElementById(id);
const pretty = (value) => JSON.stringify(value, null, 2);
let catalog;
let report;

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
  el("proposal").value = pretty({ tool: "read_source", arguments: { resource: scenario.resource } });
}

function showRun(run) {
  report = run;
  const status = run.task_completed === null ? "Inconclusive" :
    run.task_completed ? "Legitimate task completed" : "Legitimate task failed";
  el("outcome").textContent = [status, run.model, run.duration_ms + " ms"].join(" · ");
  el("answer").textContent = run.answer ? pretty(run.answer) : "";
  el("timeline").replaceChildren();
  for (const event of run.events) {
    const detail = append(el("timeline"), "details", "");
    const title = [event.decision, event.tool, event.executed ? "executed" : "not executed"].join(" · ");
    append(detail, "summary", title).dataset.decision = event.decision;
    append(detail, "pre", pretty(event));
  }
  el("payload").textContent = pretty(run);
  el("report").hidden = false;
  el("export").disabled = false;
}

async function refreshHistory() {
  const data = await request("/metrics");
  el("metrics").replaceChildren();
  for (const [mode, stats] of Object.entries(data.by_mode)) {
    const card = append(el("metrics"), "div", "", "panel");
    append(card, "h3", mode === "live" ? "Live model runs" : "Deterministic fixture runs");
    append(card, "p", stats.recorded ? [
      stats.recorded + " recorded",
      stats.completed + "/" + stats.evaluated + " evaluated tasks completed",
      stats.blocked + " denials", stats.average_duration_ms + " ms avg",
    ].join(" · ") : "No runs recorded.");
  }
  el("recent").textContent = data.recent.length ? "Recent experiments" : "No experiments recorded yet.";
  for (const run of data.recent) {
    const label = [catalog[run.scenario].title, run.mode, new Date(run.created_at).toLocaleString()].join(" · ");
    append(el("recent"), "button", label, "secondary").addEventListener("click", async () => {
      try {
        showRun(await request("/runs/" + run.id));
        el("outcome").scrollIntoView({ block: "center" });
      } catch (error) {
        el("recent").prepend(document.createTextNode(error.message + " "));
      }
    });
  }
}

el("mode").addEventListener("change", () => {
  el("tokenField").hidden = el("mode").value !== "live";
});
el("scenario").addEventListener("change", updateScenario);
el("experiment").addEventListener("submit", async (event) => {
  event.preventDefault();
  el("start").disabled = true;
  const mode = el("mode").value;
  el("status").textContent = mode === "live" ? "Waiting for the model…" : "Running fixture…";
  try {
    const run = await request("/runs", {
      scenario: el("scenario").value, mode, note: el("note").value,
      rehearsal: el("rehearsal").value || null,
    }, mode === "live" ? el("token").value : "");
    showRun(run);
    el("status").textContent = run.error || "Run recorded.";
    await refreshHistory();
  } catch (error) {
    el("status").textContent = error.message;
  } finally {
    el("start").disabled = false;
  }
});
el("playground").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const proposal = JSON.parse(el("proposal").value);
    el("decision").textContent = pretty(await request("/gateway/authorize-action", {
      scenario: el("scenario").value, proposal,
    }));
  } catch (error) {
    el("decision").textContent = error.message;
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
    for (const [id, scenario] of Object.entries(catalog)) {
      el("scenario").add(new Option(scenario.title, id));
    }
    updateScenario();
    el("health").textContent = health.live_configured ? "LIVE MODEL CONFIGURED" : "FIXTURE MODE AVAILABLE";
    el("mode").options[1].disabled = !health.live_configured;
    el("start").disabled = false;
    await refreshHistory();
  } catch (error) {
    el("health").textContent = "GATEWAY CHECK FAILED";
    el("status").textContent = error.message;
  }
}
init();
