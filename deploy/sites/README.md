# Public Sites edition

The ChatGPT Sites deployment runs the storefronts and deterministic fixture gateway on a lightweight Worker. It reuses the local lab UI, source templates, and storefront renderer at build time. The latest 20 public run reports are browser-local. The Python app remains the entry point for SQLite storage and optional live providers.

Generate a deployment checkout from the repository root using:

```sh
.venv/bin/python -m deploy.sites.build /absolute/path/to/site-checkout
node --check /absolute/path/to/site-checkout/dist/server/index.js
```

The build copies only the tracked Site manifest, application assets, fixture data, and Worker code. It does not read model keys, audio credentials, or runtime databases.
