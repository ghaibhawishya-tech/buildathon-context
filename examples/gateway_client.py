"""Check a proposed read for a task whose context your app already authorized."""
import json
from urllib.request import Request, urlopen


def authorize_workspace_read(resource: str) -> dict:
    body = json.dumps({
        "scenario": "workspace",
        "proposal": {"tool": "read_source", "arguments": {"resource": resource}},
    }).encode()
    request = Request(
        "http://127.0.0.1:8000/gateway/authorize-action",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=5) as response:
        return json.load(response)


if __name__ == "__main__":
    decision = authorize_workspace_read("project-update")
    print(json.dumps(decision, indent=2))
    # Enforce ALLOW before any application-owned tool dispatch. Fail closed on errors.
