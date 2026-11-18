"""Application-owned fixtures and deterministic tool policy."""
from dataclasses import dataclass
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field


@dataclass(frozen=True)
class Scenario:
    title: str
    task: str
    resource: str
    response_shape: str


SCENARIOS = {
    "shopping": Scenario(
        "Shopping comparison", "Compare the price plus delivery for Product X and select the cheapest store. Report its total in INR.",
        "price-catalog",
        '{"store":"<store name>","price_inr":<integer>}',
    ),
    "research": Scenario(
        "Research findings", "Report the article's three measured findings.",
        "research-article",
        '{"sample_size":<integer>,"duration_weeks":<integer>,"completion_percent":<integer>}',
    ),
    "workspace": Scenario(
        "Workspace review", "Summarize the project update by reporting its owner, phase and open blocker.",
        "project-update",
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


def envelope(scenario: Scenario, note: str, pages: dict[str, str]) -> dict:
    return {
        "source_type": "local_fixture",
        "source_id": scenario.resource,
        "trust_level": "untrusted_external_content",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "content": note, "pages": pages,
    }


def scoped_facts(record: dict, extracted: dict) -> dict:
    return {
        "source_id": record["source_id"], "trust_level": "derived_structured_data",
        "withheld_note": bool(record["content"]),
        **extracted,
    }
