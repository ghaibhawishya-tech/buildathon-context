# Evaluation

Use the test suite to reproduce allow and deny decisions, run fixture tasks against known answers, and check that reports and metrics are persisted. Cases include malformed arguments, incorrect resource identifiers, harmless instruction-like wording and denied simulated proposals. These checks cover the policy and controlled fixtures.

The dashboard separates deterministic fixture runs from live model runs. Task completion uses evaluated runs as its denominator. Denials are shown separately for model proposals and manual rehearsals. Every new event records its origin and timestamp. Average duration covers recorded runs. Provider failures and timeouts are recorded as inconclusive with any partial tool evidence. They are excluded from the task completion denominator.

A fixture run verifies deterministic behavior. A live run measures the configured model's answer on that task and may vary on repetition. No attack success rate or general false positive rate is inferred from these runs.

## Recorded shopping comparison

The evidence page preserves a single pair of real inferences using Qwen3-0.6B, GGUF Q4_K_M, served locally by llama.cpp b12503 with temperature 0 and reasoning off. Both conditions used the same fictional prices, shipping fees and seller copy. The direct condition received the source text in its prompt with no tools. The gateway condition used the lab’s regular live runner, which requests a tool call on its first turn. The server supplied validated fields and calculated checkout totals after the authorized read. [Recorded inputs, trace and outputs](../apps/web/model-evidence.json)

The direct response named Store C at ₹1,999. The model using the gateway chose Store C at ₹2,699. Both missed Store B at ₹2,499. The direct response also used Markdown fences instead of a bare JSON object. The evaluator rejected the gateway answer even though the read succeeded. Differences in prompt and input representation limit causal interpretation. These are two observations on one benign task.

To repeat the pair, start the Python service with a compatible provider, export the same model name, provider URL, provider key and lab token in the recorder shell, then run:

```sh
.venv/bin/python examples/record_model_comparison.py --lab-url http://127.0.0.1:8000
```

The recorder writes the new comparison to standard output. It leaves the published recording intact. Separate live smoke checks with this small model on Research and Workspace produced inconclusive responses before a verified read. Their deterministic fixture runs are covered by the automated suites.

Both executors are read-only. The effect count describes side effects recorded by this dispatcher; it cannot estimate how often a general-purpose agent would take an unauthorized action.
