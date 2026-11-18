# Evaluation

Use the test suite to reproduce allow and deny decisions, run fixture tasks against known answers, and check that reports and metrics are persisted. Cases include malformed arguments, incorrect resource identifiers, harmless instruction-like wording and denied simulated proposals. These checks cover the policy and controlled fixtures.

The dashboard separates deterministic fixture runs from live model runs. Task completion uses evaluated runs as its denominator. Denials are shown separately for model proposals and manual rehearsals. Every new event records its origin and timestamp. Average duration covers recorded runs. Provider failures and timeouts are recorded as inconclusive with any partial tool evidence. They are excluded from the task completion denominator.

A fixture run verifies deterministic behavior. A live run measures the configured model's answer on that task and may vary on repetition. No attack success rate or general false positive rate is inferred from these runs.
