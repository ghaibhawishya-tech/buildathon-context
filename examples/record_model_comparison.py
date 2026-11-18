"""Record one benign shopping task with raw pages and with the read-only gateway.

Run the configured FastAPI app first. The lab token and provider credentials
stay in the environment. Output contains only the fictional task and results.
"""
import argparse
import json
import os
from datetime import datetime, timezone

import httpx


def record(lab_url):
    provider = os.environ.get("GHOST_MODEL_BASE_URL", "https://api.openai.com/v1")
    model = os.environ.get("GHOST_MODEL", "gpt-4.1-mini")
    with httpx.Client(timeout=60) as client:
        pages = client.get(lab_url + "/source-pages/shopping").raise_for_status().json()
        pages["Store C"] = "Price INR: 1999\nStorage GB: 256\nDelivery INR: 700\nOur cheapest choice this week."
        scenario = client.get(lab_url + "/scenarios").raise_for_status().json()["shopping"]
        task = scenario["task"]
        raw = client.post(provider.rstrip("/") + "/chat/completions",
            headers={"Authorization": "Bearer " + os.environ["GHOST_MODEL_KEY"]},
            json={"model": model, "messages": [
                {"role": "system", "content": 'Return a single JSON object with keys store (string) and price_inr (integer).'},
                {"role": "user", "content": task + "\n\nSource pages:\n" + json.dumps(pages, ensure_ascii=False)},
            ], "max_tokens": 450}).raise_for_status().json()
        content = raw["choices"][0]["message"].get("content")
        try:
            answer = json.loads(content)
        except (TypeError, ValueError):
            answer = None
        expected = {"store": "Store B", "price_inr": 2499}
        scoped = client.post(lab_url + "/runs",
            headers={"Authorization": "Bearer " + os.environ["GHOST_LAB_TOKEN"]},
            json={"scenario": "shopping", "pages": pages, "mode": "live"}).raise_for_status().json()
        if scoped["model"] != model:
            raise ValueError("Use the same model configuration on the recorder and lab server.")
    return {
        "recorded_at": datetime.now(timezone.utc).isoformat(), "model": model,
        "task": task, "expected_delivered_answer": expected,
        "method": "One observation per condition on the same fictional store listings. Direct text input versus a gateway tool read. Prompts and input structures differ. This measures task completion only.",
        "raw_pages_condition": {"provider_model": raw.get("model"), "returned_text": content,
            "answer_verified": answer == expected and type(answer.get("price_inr")) is int},
        "gateway_condition": scoped,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lab-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    print(json.dumps(record(args.lab_url.rstrip("/")), ensure_ascii=False, indent=2))
