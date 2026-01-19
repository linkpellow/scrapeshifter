"""
Heuristic selector discovery for people-search HTML.
Port of Dojo discover-selectors logic; outputs extraction map compatible with BlueprintExtractor.
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from app.enrichment.validators import (
    is_plausible_age,
    is_plausible_email,
    is_plausible_name,
    is_plausible_phone,
    is_reasonable_string,
)

try:
    from bs4 import BeautifulSoup
    HTML_PARSING_AVAILABLE = True
except ImportError:
    HTML_PARSING_AVAILABLE = False
    BeautifulSoup = None  # type: ignore

# CSS-based patterns only; regex is used to validate/skip, not to produce selectors.
FIELD_PATTERNS: Dict[str, List[Dict[str, Any]]] = {
    "phone": [
        {"selector": "a[href^='tel:']", "extract": "href", "transform": "stripTel"},
        {"selector": "a[href^='tel:']", "extract": "text"},
        {"selector": ".phone-number", "extract": "text"},
        {"selector": ".phone", "extract": "text"},
        {"selector": "[class*='phone']", "extract": "text"},
        {"selector": "[data-phone]", "extract": "attr:data-phone"},
        {"selector": "[itemprop='telephone']", "extract": "text"},
    ],
    "email": [
        {"selector": "a[href^='mailto:']", "extract": "href", "transform": "stripMailto"},
        {"selector": "a[href^='mailto:']", "extract": "text"},
        {"selector": ".email", "extract": "text"},
        {"selector": "[class*='email']", "extract": "text"},
        {"selector": "[itemprop='email']", "extract": "text"},
    ],
    "name": [
        {"selector": "h1", "extract": "text"},
        {"selector": "[itemprop='name']", "extract": "text"},
        {"selector": ".card-title", "extract": "text"},
        {"selector": ".name", "extract": "text"},
    ],
    "age": [
        {"selector": ".age", "extract": "text"},
        {"selector": "[class*='age']", "extract": "text"},
        {"selector": ".detail-box-age", "extract": "text"},
    ],
    "address": [
        {"selector": "[itemprop='streetAddress']", "extract": "text"},
        {"selector": ".address", "extract": "text"},
        {"selector": "[class*='address']", "extract": "text"},
        {"selector": ".detail-box-address", "extract": "text"},
    ],
    "city": [
        {"selector": "[itemprop='addressLocality']", "extract": "text"},
        {"selector": ".city", "extract": "text"},
    ],
    "state": [
        {"selector": "[itemprop='addressRegion']", "extract": "text"},
        {"selector": ".state", "extract": "text"},
    ],
    "zipcode": [
        {"selector": "[itemprop='postalCode']", "extract": "text"},
        {"selector": ".zip", "extract": "text"},
        {"selector": ".zipcode", "extract": "text"},
    ],
    "income": [
        {"selector": ".income", "extract": "text"},
        {"selector": "[class*='income']", "extract": "text"},
    ],
}


def _accept(field: str, value: str) -> bool:
    if not value or not value.strip():
        return False
    if field == "phone":
        return is_plausible_phone(value)
    if field == "email":
        return is_plausible_email(value)
    if field == "name":
        return is_plausible_name(value)
    if field == "age":
        return is_plausible_age(value)
    return is_reasonable_string(value)


def _confidence(field: str, pattern: Dict[str, Any], value: str, selector: str) -> float:
    c = 0.5
    sel = pattern.get("selector", "")
    if "itemprop" in sel:
        c += 0.3
    if field in sel:
        c += 0.2
    if "tel:" in sel or "mailto:" in sel:
        c += 0.3
    if _accept(field, value):
        c += 0.1
    return min(c, 1.0)


def discover(html: str, base_url: str) -> Tuple[Dict[str, str], Dict[str, float]]:
    """
    Discover CSS selectors from HTML. Returns (extraction, confidence_per_field).
    extraction: { field: "selector::text" or "selector::attr(x)" } for BlueprintExtractor.
    """
    extraction: Dict[str, str] = {}
    confidence_per: Dict[str, float] = {}
    if not HTML_PARSING_AVAILABLE or not BeautifulSoup:
        logger.warning("BeautifulSoup not available for selector discovery")
        return extraction, confidence_per
    if not html or len(html.strip()) < 100:
        return extraction, confidence_per
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")

    for field, patterns in FIELD_PATTERNS.items():
        for p in patterns:
            sel = p.get("selector")
            if not sel:
                continue
            el = soup.select_one(sel)
            if not el:
                continue
            extract = p.get("extract", "text")
            value: Optional[str] = None
            out_sel: str
            if extract == "text":
                value = el.get_text(strip=True)
                out_sel = f"{sel}::text"
            elif extract == "href":
                value = el.get("href") or ""
                if p.get("transform") == "stripTel" and value.startswith("tel:"):
                    value = value[4:].strip()
                elif p.get("transform") == "stripMailto" and value.startswith("mailto:"):
                    value = value[7:].strip()
                out_sel = f"{sel}::attr(href)"
            elif extract.startswith("attr:"):
                attr = extract.split(":", 1)[1]
                value = el.get(attr) or ""
                out_sel = f"{sel}::attr({attr})"
            else:
                value = el.get_text(strip=True)
                out_sel = f"{sel}::text"
            if _accept(field, value):
                extraction[field] = out_sel
                confidence_per[field] = _confidence(field, p, value, sel)
                break

    return extraction, confidence_per


def overall_confidence(confidence_per: Dict[str, float], extraction: Dict[str, str]) -> float:
    """Weighted average; having phone or email boosts floor."""
    if not confidence_per:
        return 0.0
    vals = list(confidence_per.values())
    o = sum(vals) / len(vals) if vals else 0.0
    if "phone" in extraction or "email" in extraction:
        o = max(o, 0.55)
    return min(o, 1.0)
