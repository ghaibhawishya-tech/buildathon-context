# Threat model

The user can edit a fictional source note and submit policy requests. The model can return malformed answers and propose tool calls. The server owns the catalog, scenario policy, executor, model destination, and audit database. Text in a source note has no role in creating permissions.

For any run, the dispatcher can read only the exact catalog resource assigned to that run. It has no tools for reading private notes, sending messages, fetching arbitrary URLs, or running code. Requests with missing context, extra arguments or unexpected tools fail closed. The evaluator compares exact typed fields with fixture facts. These controls do not guarantee that a model will reason correctly.

The demo illustrates data separation and scoped authorization. It does not extract facts from arbitrary documents or measure prompt injection effectiveness. Manual rehearsals are labeled separately from model proposals. The authorization API is advisory until an external caller enforces its result. The shared audit retains submitted text and model answers, so use fictional data and keep the lab behind access controls for private sessions.
