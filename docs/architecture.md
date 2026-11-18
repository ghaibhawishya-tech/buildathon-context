# Architecture

```mermaid
flowchart LR
    UI[Lab or API client] --> Runner[Run controller]
    Runner --> Model[Read-only agent]
    Model --> Policy[Deterministic policy]
    Policy -->|Allowed scoped read| Fixture[Structured fixture facts]
    Policy -->|Denied| Audit[SQLite audit]
    Fixture --> Model
    Model --> Evaluation[Independent task check]
    Evaluation --> Audit
    Audit --> UI
```

The runner selects the task and resource from an application-controlled catalog. The model can propose a read but cannot choose the policy context. The same policy function serves the authorization endpoint. That endpoint reports a decision only. External integrations must supply task context from trusted application state and enforce the result before dispatch.

The original note and application-assigned provenance are recorded together. Facts come from a separate structured fixture and never incorporate the note. The workspace rehearsal invokes the same dispatcher as model proposals and marks the origin as manual.

For a hosted demo, install the requirements on a Python host and run `python -m uvicorn services.api.main:app --host 0.0.0.0 --port "${PORT:-8000}"`. Use one process, HTTPS, a persistent writable volume for `GHOST_DB`, and a proxy that caps request volume. The model configuration belongs in the host's environment settings. Keep the demo behind access controls if visitors should not share history.
