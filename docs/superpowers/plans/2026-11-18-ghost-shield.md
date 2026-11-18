# Ghost Shield Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task by task.

**Goal:** Demonstrate how an agent uses a deterministic gateway to read scoped data.

**Architecture:** Application-owned fixtures supply structured facts and separate editable source notes. A fixed policy controls read access. A separate evaluation step checks structured answers and the audit records actual decisions.

**Tech stack:** FastAPI, SQLite, OpenAI-compatible HTTP, HTML/CSS/JavaScript.

**Spec:** User-supplied Ghost Shield master build brief, with a read-only defensive lab.

- [x] Build the fixture catalog, provenance model and independent tool policy. Test missing context, malformed requests and out-of-scope proposals.
- [x] Implement isolated read-only model runs and deterministic fixture runs. Check the reported answer against fixture truth and persist evidence.
- [x] Build the lab, dashboard, investigation and API playground. Verify the editing, running and export flow.
- [x] Document integration, threat model, deployment and demonstration. Run the test suite and push reviewed commits.
