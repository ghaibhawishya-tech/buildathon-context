const byId = id => document.getElementById(id);

function renderGrade(id, verified) {
  const el = byId(id);
  el.dataset.result = verified === true ? "passed" : verified === false ? "failed" : "inconclusive";
  el.textContent = verified === true ? "Passed · correct answer" :
    verified === false ? "Failed · incorrect or unparseable answer" : "Inconclusive · no grade recorded";
}

async function showRecording() {
  try {
    const response = await fetch("/assets/model-evidence.json");
    if (!response.ok) throw Error();
    const record = await response.json();
    const raw = record.raw_pages_condition;
    const gateway = record.gateway_condition;
    if (!raw || !gateway || !record.model || !record.recorded_at) throw Error();

    byId("model").textContent = record.model;
    const date = new Date(record.recorded_at);
    byId("recorded").dateTime = record.recorded_at;
    byId("recorded").textContent = Number.isNaN(date.valueOf()) ? record.recorded_at :
      new Intl.DateTimeFormat("en", { dateStyle: "medium", timeStyle: "long", timeZone: "UTC" }).format(date);
    byId("task").textContent = record.task;
    const expected = record.expected_delivered_answer;
    byId("expected").textContent = expected ? expected.store + " · ₹" + expected.price_inr.toLocaleString("en-IN") : "Unavailable";
    byId("raw-answer").textContent = raw.returned_text ?? "No response text recorded.";
    byId("gateway-answer").textContent = gateway.answer == null ? "No answer recorded." : JSON.stringify(gateway.answer, null, 2);
    renderGrade("raw-grade", raw.answer_verified);
    renderGrade("gateway-grade", gateway.error ? null : gateway.answer_verified);
    if (gateway.error) {
      byId("gateway-error").textContent = gateway.error;
      byId("gateway-error").hidden = false;
    }
    byId("read-check").textContent = gateway.verified_read === true ? "Scoped source read verified." :
      gateway.verified_read === false ? "Scoped source read failed verification." : "Read verification unavailable.";
    if (gateway.events?.length) {
      const list = document.createElement("ol");
      for (const event of gateway.events) {
        const item = document.createElement("li");
        item.textContent = (event.origin ?? "Unknown actor") + " requested " + (event.tool ?? "unknown tool") +
          " · " + (event.decision ?? "No decision recorded") + (event.resource ? " · " + event.resource : "");
        list.append(item);
      }
      byId("calls").append(list);
    } else {
      byId("calls").textContent = "No tool calls recorded.";
    }
    byId("results").hidden = false;
    byId("status").textContent = "";
  } catch {
    byId("status").textContent = "The recording could not be loaded. Open the raw JSON to check its availability.";
  }
}
showRecording();
