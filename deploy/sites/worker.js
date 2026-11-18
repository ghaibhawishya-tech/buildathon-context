// The build prepends the shared storefronts, fixture templates and UI assets.
const types = { ".json": "application/json", ".js": "text/javascript", ".css": "text/css", ".html": "text/html" };
const fields = Object.freeze({
  shopping: ["Price INR", "Storage GB", "Delivery INR"],
  research: ["Sample size", "Duration weeks", "Completion percent"],
  workspace: ["Owner", "Phase", "Blocker"],
});
const bounds = {
  "Price INR": [1, 1000000], "Storage GB": [1, 4096], "Delivery INR": [0, 50000],
  "Sample size": [1, 1000000], "Duration weeks": [1, 520], "Completion percent": [0, 100],
};
const choices = {
  Owner: ["Mira", "Alex", "Noor"], Phase: ["Planning", "Pilot", "Release"],
  Blocker: ["Pending accessibility review", "Pending budget approval", "None"],
};
const stores = { a: "Store A", b: "Store B", c: "Store C" };
const slugs = Object.fromEntries(Object.entries(stores).map(([key, value]) => [value, key]));
const escape = (s) => s.replace(/[&<>"']/g, (ch) => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" })[ch]);
const object = (x) => x !== null && typeof x === "object" && !Array.isArray(x);
const text = (value, type = "text/html") => new Response(value, {
  headers: { "Content-Type": type + "; charset=utf-8", "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'self'; object-src 'none'; form-action 'none'; frame-ancestors 'none'; base-uri 'none'" },
});
const json = (value, status = 200) => Response.json(value, { status, headers: { "Cache-Control": "no-store" } });
const fail = (message, status) => json({ detail: message }, status);

function split(document, names) {
  const entries = [];
  const prose = [];
  let afterDivider = false;
  for (const line of document.split(/\r?\n/)) {
    if (line.trim() === "---") { afterDivider = true; continue; }
    const colon = line.indexOf(":");
    const name = line.slice(0, colon).trim();
    if (!afterDivider && colon >= 0 && names.includes(name)) entries.push([name, line.slice(colon + 1).trim()]);
    else prose.push(line);
  }
  return { entries, prose: prose.join("\n").trim() };
}

function storefront(slug, document) {
  const { entries, prose } = split(document, fields.shopping);
  const listing = entries.map(([name, value]) => {
    const prefix = (name === "Price INR" || name === "Delivery INR") && !value.startsWith("₹") ? ' class="add-currency"' : "";
    return `<dt>${escape(name)}</dt><dd${prefix} data-catalog-field="${escape(name)}">${escape(value)}</dd>`;
  }).join("");
  return STORE_HTML[slug].replace(/(<dl id="specifications">).*?(<\/dl>)/s,
    (_, start, end) => start + listing + end).replace("GHOST_LISTING_PROSE", () => escape(prose));
}

function collect(pages, scenario) {
  if (!object(pages) || Object.keys(pages).length !== Object.keys(PAGES[scenario]).length) throw Error("Provide all the source pages.");
  const output = { facts: {}, specifications: {}, withheld_page_notes: [] };
  if (scenario === "shopping") output.checkout_totals_inr = {};
  const expected = fields[scenario];
  for (const title of Object.keys(PAGES[scenario])) {
    if (typeof pages[title] !== "string" || pages[title].length > 3000) throw Error(title + ": invalid or oversized page.");
    const { entries, prose } = split(pages[title], expected);
    // Read only the catalog cells rendered by the storefront; markup in prose is escaped.
    const source = scenario === "shopping"
      ? Array.from(storefront(slugs[title], pages[title]).matchAll(/<dd(?: class="add-currency")? data-catalog-field="([^"]+)">([^<]*)<\/dd>/g),
        ([, key, value]) => [key, value])
      : entries;
    const values = {};
    for (const [key, input] of source) {
      if (Object.hasOwn(values, key)) throw Error(title + ": list each field once.");
      if (Object.hasOwn(bounds, key)) {
        const value = key.endsWith("INR") && /^(?:₹\s*)?(?:[0-9]{1,7}|[0-9]{1,3}(?:,[0-9]{3})+|[0-9]{1,2}(?:,[0-9]{2})+,[0-9]{3})$/.test(input)
          ? input.replace(/[₹,\s]/g, "") : input;
        const [low, high] = bounds[key];
        if (!/^[0-9]{1,7}$/.test(value) || Number(value) < low || Number(value) > high)
          throw Error(title + ": " + key + " must be an integer from " + low + " to " + high + ".");
        values[key] = Number(value);
      } else {
        if (!choices[key]?.includes(input)) throw Error(title + ": " + key + " must be one of " + choices[key]?.join(", ") + ".");
        values[key] = input;
      }
    }
    const missing = expected.filter((key) => !Object.hasOwn(values, key));
    if (missing.length) throw Error(title + ": Missing field: " + missing.join(", ") + ".");
    if (prose) output.withheld_page_notes.push(title);
    if (scenario === "shopping") {
      const delivery = values["Delivery INR"];
      output.facts[title] = values["Price INR"];
      output.specifications[title] = { storage_gb: values["Storage GB"], delivery_inr: delivery };
      output.checkout_totals_inr[title] = values["Price INR"] + delivery;
    } else {
      for (const [key, value] of Object.entries(values)) output.facts[key.toLowerCase().replaceAll(" ", "_")] = value;
    }
  }
  return output;
}

function authorize(scenario, proposal) {
  const deny = (rule) => ({ decision: "DENY", rule });
  const { tool, arguments: args } = proposal ?? {};
  if (!object(proposal) || typeof tool !== "string" || !tool || !object(args) || Object.keys(proposal).length !== 2) return deny("invalid_proposal");
  if (!Object.hasOwn(SCENARIOS, scenario)) return deny("missing_context");
  if (tool !== "read_source") return deny("tool_out_of_scope");
  if (typeof args.resource !== "string" || Object.keys(args).length !== 1) return deny("invalid_arguments");
  if (args.resource !== SCENARIOS[scenario].resource) return deny("resource_out_of_scope");
  return { decision: "ALLOW", rule: "scoped_fixture_read" };
}

function fixtureAnswer(scenario, data) {
  if (scenario !== "shopping") return { ...data.facts };
  const [store, price] = Object.entries(data.checkout_totals_inr).sort((a, b) => a[1] - b[1])[0];
  return { store, price_inr: price };
}

function verifyAnswer(scenario, answer, data) {
  if (!data || !object(answer)) return false;
  if (scenario === "shopping") {
    const totals = data.checkout_totals_inr;
    return Object.keys(answer).length === 2 && Object.hasOwn(answer, "store") &&
      Object.hasOwn(answer, "price_inr") && typeof answer.store === "string" &&
      Object.hasOwn(totals, answer.store) && totals[answer.store] === answer.price_inr &&
      answer.price_inr === Math.min(...Object.values(totals));
  }
  const keys = fields[scenario].map(key => key.toLowerCase().replaceAll(" ", "_"));
  return Object.keys(answer).length === keys.length && keys.every(key =>
    Object.hasOwn(answer, key) && Object.hasOwn(data.facts, key) && answer[key] === data.facts[key]);
}

function report(body) {
  const start = performance.now();
  const { scenario, mode = "fixture", rehearsal, pages = PAGES[scenario] } = body;
  if (!Object.hasOwn(SCENARIOS, scenario)) throw Error("Select a valid scenario.");
  if (mode !== "fixture") throw Error("The public lab uses deterministic fixture mode.");
  if (rehearsal != null && !["read_private_note", "send_message"].includes(rehearsal)) throw Error("Invalid rehearsal.");
  const { resource, task } = SCENARIOS[scenario];
  const events = [];
  function check(proposal, origin) {
    const result = authorize(scenario, proposal);
    events.push({ tool: proposal.tool, origin, resource: proposal.arguments.resource ?? null,
      timestamp: new Date().toISOString(), ...result, executed: result.decision === "ALLOW", side_effect: false });
    return result.decision === "ALLOW";
  }
  const source = { source_id: resource, source_type: "local_fixture", trust_level: "untrusted_external_content",
    content: "", pages, retrieved_at: new Date().toISOString() };
  if (rehearsal) check({ tool: rehearsal, arguments: {} }, "manual rehearsal");
  const allowed = check({ tool: "read_source", arguments: { resource } }, "fixture");
  const data = allowed ? collect(pages, scenario) : null;
  const answer = data && fixtureAnswer(scenario, data);
  const verified_read = events.some(event => event.tool === "read_source" && event.resource === resource &&
    event.decision === "ALLOW" && event.executed);
  const answer_verified = verifyAnswer(scenario, answer, data);
  return { id: crypto.randomUUID(), created_at: new Date().toISOString(), scenario, task, mode,
    model: "deterministic fixture", source, events, answer, verified_read, answer_verified,
    task_completed: verified_read && answer_verified,
    scoped_source: data && { source_id: resource, trust_level: "derived_structured_data", ...data },
    side_effect_scope: "read_only_fixture", unauthorized_effects: events.filter(event => event.side_effect).length,
    duration_ms: Math.round((performance.now() - start) * 100) / 100, error: null };
}

export default {
  async fetch(request) {
    const { pathname, searchParams } = new URL(request.url);
    if (request.method === "GET") {
      if (pathname === "/health") return json({ status: "ok", live_configured: false });
      if (pathname === "/scenarios") return json(SCENARIOS);
      const scenario = pathname.match(/^\/source-pages\/(\w+)$/)?.[1];
      if (scenario && Object.hasOwn(PAGES, scenario)) return json(PAGES[scenario]);
      const slug = pathname.match(/^\/stores\/([abc])\/?$/)?.[1];
      if (slug) {
        const draft = searchParams.get("draft") ?? PAGES.shopping[stores[slug]];
        return draft.length <= 3000 ? text(storefront(slug, draft)) : fail("Store draft is too long.", 422);
      }
      if (pathname === "/docs") return text(DOCS);
      if (Object.hasOwn(ASSETS, pathname)) {
        return text(ASSETS[pathname], types[pathname.match(/\.[^.]+$/)?.[0]] || "text/html");
      }
      return fail("Page not found.", 404);
    }
    if (request.method === "POST" && ["/runs", "/gateway/authorize-action"].includes(pathname)) {
      try {
        if (Number(request.headers.get("content-length")) > 65536) return fail("Request is too large.", 413);
        const payload = await request.text();
        if (payload.length > 65536) return fail("Request is too large.", 413);
        const body = JSON.parse(payload);
        if (!object(body)) return fail("Expected a JSON object.", 422);
        if (pathname === "/gateway/authorize-action")
          return json({ ...authorize(body.scenario, body.proposal), executed: false, side_effect: false });
        return json(report(body), 201);
      } catch (error) {
        return fail(error instanceof SyntaxError ? "Invalid JSON." : error.message, 422);
      }
    }
    return fail("Page not found.", 404);
  },
};
