"""
Anti-Poisoning & Cross-Source Consensus (The Shield).

- Entropy-Based Poison Detection: If a provider returns the same Phone/Email for
  >3 distinct leads in 60 minutes, auto-blacklist the provider for 4 hours and
  notify WEBHOOK_URL.
- Cross-Source Consensus: For high-value leads, if two Magazine sites’ results
  differ significantly, mark NEEDS_RECONCILIATION.
- 2026 Consensus Protocol: If vision_confidence < 0.95, set NEEDS_OLMOCR_VERIFICATION.
"""

import hashlib
import json
import os
import urllib.request
from typing import Any, Dict, List, Optional

import redis

POISON_PREFIX = "poison:p:"
POISON_TTL = 3600  # 60 minutes
BLACKLIST_PREFIX = "blacklist:provider:"
BLACKLIST_TTL = 4 * 3600  # 4 hours

# 2026: below this, trigger olmOCR-2 verification (Brain does it; we flag for Golden Record)
CONFIDENCE_OLMOCR_THRESHOLD = 0.95

MAGAZINE = [
    "FastPeopleSearch",
    "TruePeopleSearch",
    "ZabaSearch",
    "SearchPeopleFree",
    "ThatsThem",
    "AnyWho",
]

_redis = None


def _get_redis() -> redis.Redis:
    global _redis
    if _redis is not None:
        return _redis
    url = os.getenv("REDIS_URL") or os.getenv("APP_REDIS_URL") or "redis://localhost:6379"
    _redis = redis.from_url(url, decode_responses=True)
    return _redis


def _norm_val(v: Any) -> str:
    s = (v or "").strip()
    return s.lower() if isinstance(s, str) else str(s)


def _hash_val(v: str) -> str:
    return hashlib.sha256(_norm_val(v).encode()).hexdigest()[:24]


# ---------------------------------------------------------------------------
# Provider blacklist (entropy poison + Dojo)
# ---------------------------------------------------------------------------


def is_provider_blacklisted(provider: str, r: Optional[redis.Redis] = None) -> bool:
    if r is None:
        r = _get_redis()
    try:
        return bool(r.exists(f"{BLACKLIST_PREFIX}{provider}"))
    except Exception:
        return False


def blacklist_provider(provider: str, reason: str, r: Optional[redis.Redis] = None) -> None:
    if r is None:
        r = _get_redis()
    try:
        key = f"{BLACKLIST_PREFIX}{provider}"
        r.set(key, "1", ex=BLACKLIST_TTL)
        url = os.getenv("WEBHOOK_URL")
        if url:
            body = json.dumps({
                "event": "provider_blacklisted",
                "provider": provider,
                "reason": reason,
                "ttl_hours": 4,
            }).encode()
            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=8)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Entropy-based poison detection
# ---------------------------------------------------------------------------


def record_data_point(
    provider: str,
    data_type: str,
    value: Any,
    lead_id: str,
    r: Optional[redis.Redis] = None,
) -> bool:
    """
    Record a (provider, data_type, value) for lead_id. If the same value was
    already returned for >3 distinct leads in the last 60 minutes, blacklist
    the provider and return True. Otherwise return False.
    """
    if r is None:
        r = _get_redis()
    v = _norm_val(value)
    if not v or data_type not in ("phone", "email"):
        return False
    h = _hash_val(v)
    key = f"{POISON_PREFIX}{provider}:{data_type}:{h}"
    try:
        r.sadd(key, lead_id)
        r.expire(key, POISON_TTL)
        n = r.scard(key)
        if n > 3:
            blacklist_provider(provider, "entropy_poison", r)
            return True
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# Cross-source consensus (high-value leads)
# ---------------------------------------------------------------------------


def is_high_value(lead: Dict[str, Any]) -> bool:
    """Heuristic: company + title suggests high-value."""
    c = (lead.get("company") or lead.get("Company") or "").strip()
    t = (lead.get("title") or lead.get("Title") or lead.get("headline") or "").strip()
    return bool(c and t)


def _norm_comp(a: Any, b: Any) -> bool:
    """True if a and b are effectively equal."""
    sa = _norm_val(a)
    sb = _norm_val(b)
    if sa == sb:
        return True
    # digits-only for phone
    da = "".join(c for c in str(sa) if c.isdigit())
    db = "".join(c for c in str(sb) if c.isdigit())
    if da and db and da == db:
        return True
    return False


def results_differ_significantly(r1: Dict[str, Any], r2: Dict[str, Any]) -> bool:
    """True if phone, email, or age differ between two Chimera results."""
    for k in ("phone", "email", "age"):
        v1 = r1.get(k) or r1.get(f"chimera_{k}")
        v2 = r2.get(k) or r2.get(f"chimera_{k}")
        if v1 is None and v2 is None:
            continue
        if not _norm_comp(v1, v2):
            return True
    return False


def check_cross_source(r1: Dict[str, Any], r2: Dict[str, Any]) -> Optional[str]:
    """
    If the two results differ significantly, return "NEEDS_RECONCILIATION".
    Otherwise None.
    """
    if results_differ_significantly(r1, r2):
        return "NEEDS_RECONCILIATION"
    return None


# ---------------------------------------------------------------------------
# 2026 Consensus Protocol: vision_confidence < 0.95 -> NEEDS_OLMOCR_VERIFICATION
# ---------------------------------------------------------------------------


def should_trigger_olmocr_verification(confidence: float) -> bool:
    """True when DeepSeek-VL2 confidence is below the olmOCR-2 verification threshold."""
    return float(confidence or 1.0) < CONFIDENCE_OLMOCR_THRESHOLD


def apply_consensus_protocol(chimera_raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    If vision_confidence from Chimera (DeepSeek-VL2) is < 0.95, return
    {NEEDS_OLMOCR_VERIFICATION: True}. The Brain runs olmOCR-2 when possible
    (USE_2026_VISION=1 and VLM_TIER=hybrid); this flags the Golden Record.
    When VLM_TIER=speed or USE_2026_VISION=0, olmOCR does not run; the flag
    still indicates low vision confidence. Otherwise return {}.
    """
    c = chimera_raw.get("vision_confidence", chimera_raw.get("confidence", 1.0))
    if should_trigger_olmocr_verification(c):
        return {"NEEDS_OLMOCR_VERIFICATION": True}
    return {}
