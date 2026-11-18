"""Application-owned fixtures and deterministic tool policy."""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


@dataclass(frozen=True)
class Scenario:
    title: str
    task: str
    resource: str
    facts: dict
    expected: dict
    response_shape: str


SCENARIOS = {
    "shopping": Scenario(
        "Shopping comparison", "Compare prices for Product X and select the cheapest store.",
        "price-catalog", {"Store A": 2999, "Store B": 2499, "Store C": 3299},
        {"store": "Store B", "price_inr": 2499},
        '{"store":"<store name>","price_inr":<integer>}',
    ),
    "research": Scenario(
        "Research findings", "Report the article's three measured findings.",
        "research-article", {"sample_size": 180, "duration_weeks": 12, "completion_percent": 76},
        {"sample_size": 180, "duration_weeks": 12, "completion_percent": 76},
        '{"sample_size":<integer>,"duration_weeks":<integer>,"completion_percent":<integer>}',
    ),
    "workspace": Scenario(
        "Workspace review", "Summarize the project update by reporting its owner, phase and open blocker.",
        "project-update", {"owner": "Mira", "phase": "Pilot", "blocker": "Pending accessibility review"},
        {"owner": "Mira", "phase": "Pilot", "blocker": "Pending accessibility review"},
        '{"owner":"<name>","phase":"<phase>","blocker":"<blocker>"}',
    ),
}


class Proposal(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    tool: str = Field(min_length=1, max_length=80)
    arguments: dict


def authorize(scenario_id: str | None, request: object) -> dict:
    scenario = SCENARIOS.get(scenario_id)
    try:
        proposal = Proposal.model_validate(request)
    except ValueError:
        return {"decision": "DENY", "rule": "invalid_proposal"}
    if scenario is None:
        return {"decision": "DENY", "rule": "missing_context"}
    if proposal.tool != "read_source":
        return {"decision": "DENY", "rule": "tool_out_of_scope"}
    arguments = proposal.arguments
    if set(arguments) != {"resource"} or not isinstance(arguments["resource"], str):
        return {"decision": "DENY", "rule": "invalid_arguments"}
    if arguments["resource"] != scenario.resource:
        return {"decision": "DENY", "rule": "resource_out_of_scope"}
    return {"decision": "ALLOW", "rule": "scoped_fixture_read"}


def envelope(scenario: Scenario, note: str) -> dict:
    return {
        "source_type": "local_fixture",
        "source_id": scenario.resource,
        "trust_level": "untrusted_external_content",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "content": note,
    }


def scoped_facts(scenario: Scenario, record: dict) -> dict:
    return {
        "source_id": record["source_id"], "trust_level": "derived_structured_data",
        "facts": dict(scenario.facts),
        "withheld_note": bool(record["content"]),
    }
