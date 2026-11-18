"""Enforce a gateway decision before reading an application-owned resource."""
import json
from urllib.request import Request, urlopen


def authorize_workspace_read(resource: str, base_url: str = "http://127.0.0.1:8000") -> dict:
    body = json.dumps({
        "scenario": "workspace",
        "proposal": {"tool": "read_source", "arguments": {"resource": resource}},
    }).encode()
    request = Request(
        base_url.rstrip("/") + "/gateway/authorize-action",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=5) as response:
        return json.load(response)


def read_workspace(resource, read_resource, base_url="http://127.0.0.1:8000"):
    """The application owns the workspace context and its read implementation."""
    decision = authorize_workspace_read(resource, base_url)
    if decision.get("decision") != "ALLOW":
        raise PermissionError(decision.get("rule", "missing_decision"))
    return read_resource(resource)


if __name__ == "__main__":
    records = {"project-update": {"owner": "Mira", "phase": "Pilot"}}
    print(json.dumps(read_workspace("project-update", records.__getitem__), indent=2))
