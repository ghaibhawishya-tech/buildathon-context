"""Parse scoped data from editable simulated source documents."""
import re

SHOPPING_PAGES = {
    "Store A": "Price INR: 2999\nStorage GB: 128\n---\nStandard delivery.",
    "Store B": "Price INR: 2499\nStorage GB: 128\n---\nPickup available.",
    "Store C": "Price INR: 3299\nStorage GB: 256\n---\nExpress delivery available.",
}
SOURCE_PAGES = {
    "shopping": SHOPPING_PAGES,
    "research": {
        "Research article": "Sample size: 180\nDuration weeks: 12\nCompletion percent: 76\n---\nFictional study.",
    },
    "workspace": {
        "Project update": "Owner: Mira\nPhase: Pilot\nBlocker: Pending accessibility review\n---\nFictional project memo.",
    },
}
FIELD_LIMITS = {
    "Price INR": (1, 1_000_000),
    "Storage GB": (1, 4096),
    "Sample size": (1, 1_000_000),
    "Duration weeks": (1, 520),
    "Completion percent": (0, 100),
}
CHOICES = {
    "Owner": {"Mira", "Alex", "Noor"},
    "Phase": {"Planning", "Pilot", "Release"},
    "Blocker": {"Pending accessibility review", "Pending budget approval", "None"},
}


def parse_fields(document: str, names: tuple[str, ...]) -> tuple[dict, bool]:
    data, separator, note = document.partition("\n---\n")
    values = {}
    for line in data.splitlines():
        key, colon, raw = line.partition(":")
        value = raw.strip()
        if not colon or key not in names or key in values:
            raise ValueError("Use each listed field exactly once before the --- separator.")
        if key in FIELD_LIMITS:
            low, high = FIELD_LIMITS[key]
            if re.fullmatch(r"[0-9]{1,7}", value) is None or not low <= int(value) <= high:
                raise ValueError(f"{key} must be an integer from {low} to {high}.")
            values[key] = int(value)
        elif value in CHOICES[key]:
            values[key] = value
        else:
            choices = ", ".join(sorted(CHOICES[key]))
            raise ValueError(f"{key} must be one of: {choices}.")
    if values.keys() != set(names):
        raise ValueError("The source is missing a required field.")
    return values, bool(separator and note.strip())


def extract_sources(scenario: str, pages: dict[str, str]) -> dict:
    templates = SOURCE_PAGES[scenario]
    if pages.keys() != templates.keys():
        raise ValueError("Provide exactly the source pages listed for this scenario.")
    withheld = []
    facts = {}
    specifications = {}
    for title in templates:
        names = tuple(line.split(":", 1)[0] for line in templates[title].partition("\n---\n")[0].splitlines())
        try:
            fields, has_note = parse_fields(pages[title], names)
        except ValueError as exc:
            raise ValueError(f"{title}: {exc}") from exc
        if has_note:
            withheld.append(title)
        if scenario == "shopping":
            facts[title] = fields["Price INR"]
            specifications[title] = {"storage_gb": fields["Storage GB"]}
        else:
            facts.update({key.lower().replace(" ", "_"): value for key, value in fields.items()})
    return {"facts": facts, "specifications": specifications, "withheld_page_notes": withheld}
