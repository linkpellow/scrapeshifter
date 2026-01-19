"""
Extraction validators for people-search data.
Used by auto_map and selector_discovery to reject garbage before commit.
"""

import re
from typing import Optional


def is_plausible_phone(value: Optional[str]) -> bool:
    """Phone: at least 10 digits; optional +1 prefix."""
    if not value or not isinstance(value, str):
        return False
    digits = re.sub(r"\D", "", value)
    return len(digits) >= 10 and (len(digits) <= 11 and (digits[0] == "1" or len(digits) == 10))


def is_plausible_email(value: Optional[str]) -> bool:
    """Email: contains @ and a dot in the domain part."""
    if not value or not isinstance(value, str):
        return False
    s = value.strip()
    if "@" not in s or s.count("@") != 1:
        return False
    local, domain = s.split("@", 1)
    return bool(local) and "." in domain and len(domain) >= 4


def is_plausible_name(value: Optional[str]) -> bool:
    """Name: 2–4 words, no URLs, not mostly digits."""
    if not value or not isinstance(value, str):
        return False
    s = value.strip()
    if len(s) < 2 or len(s) > 120:
        return False
    if "http" in s.lower() or "www." in s.lower() or ".com" in s.lower():
        return False
    digits = sum(1 for c in s if c.isdigit())
    if digits > len(s) // 2:
        return False
    parts = [p for p in s.split() if p]
    return 2 <= len(parts) <= 6


def is_plausible_age(value: Optional[str]) -> bool:
    """Age: 1–3 digits, 1–120."""
    if not value or not isinstance(value, str):
        return False
    n = re.sub(r"\D", "", value)
    if not n:
        return False
    try:
        a = int(n)
        return 1 <= a <= 120
    except ValueError:
        return False


def is_reasonable_string(value: Optional[str], max_len: int = 300) -> bool:
    """Non-empty, reasonable length; for address, city, state, zipcode, income."""
    if not value or not isinstance(value, str):
        return False
    s = value.strip()
    return 0 < len(s) <= max_len
