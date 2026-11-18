# Test Ghost//Shield

## Start the lab

From the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn services.api.main:app
```

Open [the lab](http://127.0.0.1:8000/) and look for **Fixture mode available**. Use fictional text because every run stores its source note. For a clean history, set `GHOST_DB` to a new writable database path before starting the server.

## Check the gateway and audit trail

1. Select **Load workspace demo**, then **Run experiment**.
2. In **Investigation**, confirm **Legitimate task completed** and the answer with owner **Mira**, phase **Pilot**, and blocker **Pending accessibility review**.
3. Expand **DENY · send_message · not executed**. Expect `origin: "manual rehearsal"`, `rule: "tool_out_of_scope"`, `executed: false`, and `side_effect: false`. The proposal exercises the policy and has no message sender behind it.
4. Expand **ALLOW · read_source · executed**. Expect `resource: "project-update"` and `rule: "scoped_fixture_read"`.
5. Under **Inspect the content boundary**, confirm the fictional memo appears on the left. On the right, look for the source identifier, derived facts, and `withheld_note: true`. The original memo does not appear in the returned facts.
6. Select **Export JSON**. Open the file and check the run ID, scenario, source content, ordered events, and `task_completed: true`. Refresh the app, then reopen the run through **Run history**. Check that it shows the Workspace scenario and the same evidence. The fixture rehearsal denial count should have increased by one.

## Check the other scenarios

Set **Execution mode** to **Deterministic fixture** and the rehearsal to **None**.

| Scenario | Expected answer |
| --- | --- |
| Shopping comparison | Store B at ₹2,499 |
| Research findings | Sample size 180, duration 12 weeks, completion 76% |

Run each scenario with a short fictional note. Confirm the outcome is completed, the read is allowed, and the report contains no denial. Clear the note and rerun. The answer should remain the same and `withheld_note` should be false.

## Prove the shopping answer uses edited pages

1. Choose **Shopping comparison** and expand **Store C** under **Simulated source pages**.
2. Change the first line to `Price INR: 1999`. Leave the storage field intact. Edit the fictional page copy below the divider.
3. Click **Run experiment**. The answer should change to **Store C at ₹1,999**. The original page is in the audit and the gateway output shows the extracted number without the page copy.
4. Add a second price line above the divider and run. The parser should reject the page instead of guessing which number to use.
5. Click **Reset pages** and run again. Store B should win at ₹2,499.

## Check the gateway API

1. Choose **Workspace review**. In **Gateway API**, select **Use example proposal** if needed. **Check authorization** should return `ALLOW` with rule `scoped_fixture_read` and `executed: false`. The playground only makes a decision.
2. Change the resource in the JSON from `project-update` to `price-catalog`, leaving the scenario on Workspace. The result should be `DENY` with rule `resource_out_of_scope`.
3. Remove a closing brace from the proposal and check again. The interface should show a parsing error. Restore the example and confirm it returns to `ALLOW`.
4. Open **OpenAPI reference** to inspect the request and response contracts.

## Verify live mode when credentials are available

Set `GHOST_MODEL_KEY` and `GHOST_LAB_TOKEN` in the server’s environment and restart it. Use `GHOST_MODEL` and `GHOST_MODEL_BASE_URL` to select a compatible provider if needed. Keep the model key on the server. The UI accepts only the lab token.

Choose **Shopping comparison**, **Live model**, and **None** for rehearsal. Enter the lab token and run. Confirm the report shows the configured model and an allowed read with `origin: "model"`. Check the recorded answer and whether the evaluator marked it complete. An incorrect model answer is a failed task. A provider error may appear as inconclusive. Live runs and fixture runs have separate history counts.

## Run the automated checks

Run from the repository root, with the server running for the browser check:

```sh
.venv/bin/python -m pytest -q
.venv/bin/python -m pip install playwright
.venv/bin/python -m playwright install chromium
.venv/bin/python tests/browser_smoke.py http://127.0.0.1:8000
python3 .github/scripts/check_team.py
```

The Python suite verifies scoping, evaluation, persistence, and simulated provider failures. The isolated browser checks the demo, evidence display, JSON export, mobile reflow, stale authorization responses, and history outages. It records test runs in the database used by the target server.
