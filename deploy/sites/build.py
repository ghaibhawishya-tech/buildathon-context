"""Package the public fixture edition for Sites. No local audit data or keys are copied."""
import json
import sys
from pathlib import Path

from services.api.gateway import SCENARIOS
from services.api.sources import SOURCE_PAGES, STORE_SLUGS, render_storefront

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "apps" / "web"
DEPLOY = ROOT / "deploy" / "sites"


def build(checkout: Path):
    manifest = json.loads((ROOT / ".openai" / "hosting.json").read_text())
    html = (WEB / "index.html").read_text().replace(
        "<h2 id=\"history-title\">Run history</h2>",
        "<h2 id=\"history-title\">Run history</h2><p>Your latest runs are stored in this browser.</p>",
    )
    lab = (DEPLOY / "history.js").read_text() + "\n" + (WEB / "lab.js").read_text()
    lab = lab.replace("async function request(path, body, token) {", """async function request(path, body, token) {
  if (path === "/metrics") return publicMetrics();
  if (path.startsWith("/runs/")) {
    const run = publicRuns.find(entry => entry.id === path.slice(6));
    if (!run) throw Error("This run isn't stored in this browser.");
    return run;
  }""", 1)
    lab = lab.replace("  return data;\n}", '  if (path === "/runs") rememberPublicRun(data);\n  return data;\n}', 1)
    assets = {
        "/": html, "/assets/lab.js": lab,
        "/assets/style.css": (WEB / "style.css").read_text(),
        "/assets/storefront.js": (WEB / "storefront.js").read_text(),
    }
    stores = {
        slug: render_storefront(title, "Price INR: 1\nStorage GB: 1\nGHOST_LISTING_PROSE")
        for slug, title in STORE_SLUGS.items()
    }
    scenarios = {key: {"title": row.title, "task": row.task, "resource": row.resource}
                 for key, row in SCENARIOS.items()}
    docs = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Ghost//Shield · Hosted API</title><link rel="stylesheet" href="/assets/style.css">
<body class="storefront storefront-c"><main><a href="/">← Back to the lab</a><h1>Hosted API</h1>
<p>The public edition runs deterministic fixtures. The last 20 results stay in your browser.</p>
<h2>Endpoints</h2><ul><li>GET /scenarios</li><li>GET /source-pages/shopping</li>
<li>POST /runs · scenario, pages, optional rehearsal</li>
<li>POST /gateway/authorize-action · scenario and proposal</li></ul>
<p>The authorization endpoint returns a decision. Your application must enforce it at dispatch.</p>
</main></body></html>"""
    values = {"ASSETS": assets, "STORE_HTML": stores, "SCENARIOS": scenarios, "PAGES": SOURCE_PAGES, "DOCS": docs}
    package = "\n".join(f"const {key} = {json.dumps(value, ensure_ascii=False)};" for key, value in values.items())
    for directory in [checkout / ".openai", checkout / "dist" / ".openai", checkout / "dist" / "server", checkout / "worker"]:
        directory.mkdir(parents=True, exist_ok=True)
    for directory in [checkout / ".openai", checkout / "dist" / ".openai"]:
        (directory / "hosting.json").write_text(json.dumps(manifest, indent=2) + "\n")
    worker = package + "\n" + (DEPLOY / "worker.js").read_text()
    (checkout / "worker" / "index.js").write_text(worker)
    (checkout / "dist" / "server" / "index.js").write_text(worker)
    (checkout / "package.json").write_text('{"name":"ghost-shield-context","type":"module","scripts":{"build":"mkdir -p dist/server && cp worker/index.js dist/server/index.js"}}\n')
    (checkout / ".gitignore").write_text("dist/\n")


if __name__ == "__main__":
    build(Path(sys.argv[1]).resolve())
