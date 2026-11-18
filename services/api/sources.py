"""Parse scoped data from editable simulated source documents."""
import re
from html import escape
from html.parser import HTMLParser

SHOPPING_PAGES = {
    "Store A": "Price INR: 2999\nStorage GB: 128\nDelivery INR: 149\nStandard delivery.",
    "Store B": "Price INR: 2499\nStorage GB: 128\nDelivery INR: 0\nPickup available.",
    "Store C": "Price INR: 3299\nStorage GB: 256\nDelivery INR: 0\nExpress delivery available.",
}
STORE_SLUGS = {"a": "Store A", "b": "Store B", "c": "Store C"}
SHOPPING_FIELDS = ("Price INR", "Storage GB", "Delivery INR")
STOREFRONT_DETAILS = {
    "a": ("Ochre Mobile", "Everyday essentials", "Standard delivery", "3–5 working days",
          "A straightforward phone listing with standard home delivery."),
    "b": ("Circuit Market", "Mobile & electronics", "Local pickup", "Pickup at the demo counter",
          "Compare the listing and check pickup details before you decide."),
    "c": ("Verdant Device Co.", "The device collection", "Express delivery", "1–2 working days",
          "A higher-capacity listing with express delivery in the demo."),
}

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
    "Delivery INR": (0, 50_000),
    "Storage GB": (1, 4096),
    "Sample size": (1, 1_000_000),
    "Duration weeks": (1, 520),
    "Completion percent": (0, 100),
}
PRICE_FORMAT = re.compile(r"(?:₹\s*)?([0-9]{1,7}|[0-9]{1,3}(?:,[0-9]{3})+|[0-9]{1,2}(?:,[0-9]{2})+,[0-9]{3})")
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
            if key in ("Price INR", "Delivery INR"):
                match = PRICE_FORMAT.fullmatch(value)
                value = match[1].replace(",", "") if match else ""
            if re.fullmatch(r"[0-9]{1,7}", value) is None or not low <= int(value) <= high:
                raise ValueError(f"{key} must be an integer from {low} to {high}.")
            values[key] = int(value)
        elif value in CHOICES[key]:
            values[key] = value
        else:
            choices = ", ".join(sorted(CHOICES[key]))
            raise ValueError(f"{key} must be one of: {choices}.")
    missing = ", ".join(name for name in names if name not in values and name != "Delivery INR")
    if missing:
        raise ValueError(f"Missing field: {missing}. Restore it in the source editor and run again.")
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
    brand, collection, fulfillment, timing, description = STOREFRONT_DETAILS[slug]
    entries = []
    for key, value in fields:
        prefix = ' class="add-currency"' if key in ("Price INR", "Delivery INR") and not value.startswith("₹") else ""
        entries.append(f'<dt>{escape(key)}</dt><dd{prefix} data-catalog-field="{escape(key)}">{escape(value)}</dd>')
    product_facts = "".join(entries)
    return (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>{escape(brand)} · Product X · {escape(title)}</title>'
        '<link rel="stylesheet" href="/assets/style.css">'
        '<script src="/assets/storefront.js" defer></script></head>'
        f'<body class="storefront storefront-{slug}"><main>'
        '<header class="shop-header">'
        f'<a class="shop-brand" href="#product">{escape(brand)}</a>'
        '<nav aria-label="Store sections"><a href="#product">Shop</a>'
        '<a href="#specifications">Specifications</a><a href="#delivery">Delivery</a></nav>'
        '<a class="shop-back" href="/#judge-guide">Back to lab ↗</a></header>'
        f'<div class="shop-path"><span>{escape(title)}</span><span aria-hidden="true">/</span>'
        f'<span>{escape(collection)}</span><span aria-hidden="true">/</span><span>Product X</span></div>'
        '<section class="store-product" id="product" aria-label="Product listing">'
        '<div class="product-art" aria-hidden="true"><div class="product-device-back"><i></i></div>'
        '<div class="product-device"><i></i><span>X</span></div></div>'
        f'<div class="product-details"><p class="shop-category">{escape(collection)}</p>'
        f'<h1>Product X</h1><p class="shop-description">{escape(description)}</p>'
        f'<dl id="specifications">{product_facts}</dl>'
        '<form id="store-bag" class="shop-buy"><label for="shop-quantity">Quantity</label>'
        '<select id="shop-quantity"><option>1</option><option>2</option><option>3</option></select>'
        '<button type="submit">Add to demo bag</button>'
        '<output id="shop-bag-status" role="status">Your bag is empty.</output></form></div></section>'
        '<div class="shop-lower">'
        f'<section id="delivery"><h2>{escape(fulfillment)}</h2><p>{escape(timing)}</p></section>'
        f'<section class="shop-listing"><h2>From the seller</h2><pre>{escape(prose)}</pre></section>'
        '</div><footer class="shop-footer"><p>Fictional storefront for the Ghost//Shield shopping lab.</p>'
        '<a href="/#judge-guide">Return to the comparison ↗</a></footer>'
        '</main></body></html>'
    )



def extract_sources(scenario: str, pages: dict[str, str]) -> dict:
    templates = SOURCE_PAGES[scenario]
    if pages.keys() != templates.keys():
        raise ValueError("Provide exactly the source pages listed for this scenario.")
    withheld = []
    facts = {}
    specifications = {}
    checkout_totals = {}
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
            delivery = fields.get("Delivery INR", 0)
            specifications[title] = {"storage_gb": fields["Storage GB"], "delivery_inr": delivery}
            checkout_totals[title] = fields["Price INR"] + delivery
        else:
            facts.update({key.lower().replace(" ", "_"): value for key, value in fields.items()})
    result = {"facts": facts, "specifications": specifications, "withheld_page_notes": withheld}
    if scenario == "shopping":
        result["checkout_totals_inr"] = checkout_totals
    return result
