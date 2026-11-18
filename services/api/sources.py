"""Parse scoped data from editable simulated source documents."""
import re
from html import escape
from html.parser import HTMLParser

SHOPPING_PAGES = {
    "Store A": "Price INR: 2999\nStorage GB: 128\nStandard delivery.",
    "Store B": "Price INR: 2499\nStorage GB: 128\nPickup available.",
    "Store C": "Price INR: 3299\nStorage GB: 256\nExpress delivery available.",
}
STORE_SLUGS = {"a": "Store A", "b": "Store B", "c": "Store C"}
SHOPPING_FIELDS = ("Price INR", "Storage GB")

SOURCE_PAGES = {
    "shopping": SHOPPING_PAGES,
    "research": {
        "Research article": "Sample size: 180\nDuration weeks: 12\nCompletion percent: 76\nFictional study.",
    },
    "workspace": {
        "Project update": "Owner: Mira\nPhase: Pilot\nBlocker: Pending accessibility review\nFictional project memo.",
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


def split_document(document: str, names: tuple[str, ...]) -> tuple[list[tuple[str, str]], str]:
    fields = []
    prose = []
    after_divider = False
    for line in document.splitlines():
        if line.strip() == "---":
            after_divider = True
            continue
        key, colon, value = line.partition(":")
        if colon and key.strip() in names and not after_divider:
            fields.append((key.strip(), value.strip()))
        else:
            prose.append(line)
    return fields, "\n".join(prose).strip()


def validate_fields(fields: list[tuple[str, str]], names: tuple[str, ...]) -> dict:
    values = {}
    for key, value in fields:
        if key not in names or key in values:
            raise ValueError("List each product field once.")
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
    return values



class StorefrontReader(HTMLParser):
    """Collect text from the catalog cells. Other HTML is outside the schema."""

    def __init__(self):
        super().__init__()
        self.fields = []
        self.field = None
        self.value = ""

    def handle_starttag(self, tag, attrs):
        key = dict(attrs).get("data-catalog-field")
        if tag == "dd" and key in SHOPPING_FIELDS:
            self.field = key
            self.value = ""

    def handle_data(self, data):
        if self.field:
            self.value += data

    def handle_endtag(self, tag):
        if tag == "dd" and self.field:
            self.fields.append((self.field, self.value.strip()))
            self.field = None


def render_storefront(title: str, document: str) -> str:
    fields, prose = split_document(document, SHOPPING_FIELDS)
    slug = title[-1].lower()
    entries = "".join(
        f'<dt>{escape(key)}</dt><dd data-catalog-field="{escape(key)}">{escape(value)}</dd>'
        for key, value in fields
    )
    return (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>{escape(title)} · Product X</title>'
        '<link rel="stylesheet" href="/assets/style.css"></head>'
        f'<body class="storefront storefront-{slug}"><main>'
        '<header class="store-masthead"><a href="/">← Back to Ghost//Shield</a>'
        f'<p class="eyebrow">SIMULATED STOREFRONT</p><h1>{escape(title)}</h1></header>'
        '<section class="store-product" aria-label="Product listing">'
        '<div class="product-art" aria-hidden="true"><div class="product-device"><i></i></div></div>'
        f'<div class="product-details"><h2>Product X</h2><dl>{entries}</dl>'
        f'<h3>Listing copy</h3><pre>{escape(prose)}</pre></div></section>'
        '</main></body></html>'
    )


def extract_sources(scenario: str, pages: dict[str, str]) -> dict:
    templates = SOURCE_PAGES[scenario]
    if pages.keys() != templates.keys():
        raise ValueError("Provide exactly the source pages listed for this scenario.")
    withheld = []
    facts = {}
    specifications = {}
    for title in templates:
        names = tuple(
            line.partition(":")[0] for line in templates[title].splitlines() if ":" in line
        )
        try:
            fields, prose = split_document(pages[title], names)
            if scenario == "shopping":
                reader = StorefrontReader()
                reader.feed(render_storefront(title, pages[title]))
                reader.close()
                fields = reader.fields
            fields = validate_fields(fields, names)
            has_note = bool(prose)
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
