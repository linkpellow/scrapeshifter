"""
Auto-map: when no blueprint exists, attempt to discover one from HTML, verify, and commit or save as pending.
Used by BlueprintLoader and POST /api/blueprints/auto-map.
"""

import json
import os
from typing import Any, Dict, Optional

from loguru import logger
import redis

from app.enrichment.blueprint_commit import commit_blueprint_impl
from app.enrichment.scraper_enrichment import BlueprintExtractor, URL_TEMPLATES
from app.enrichment.selector_discovery import discover, overall_confidence
from app.enrichment.validators import is_plausible_email, is_plausible_name, is_plausible_phone

AUTO_MAP_RATE_KEY = "auto_map:last:"
AUTO_MAP_RATE_TTL = 3600
PENDING_KEY_SUFFIX = ":pending"
PENDING_TTL = 86400 * 2


def _get_redis():
    url = os.getenv("REDIS_URL") or os.getenv("APP_REDIS_URL") or "redis://localhost:6379"
    return redis.from_url(url, decode_responses=True)


async def _fetch_html(url: str, use_browser: bool = False) -> tuple[str, int]:
    from app.scraping.base import BROWSER_MODE_AVAILABLE, BaseScraper, STEALTH_AVAILABLE

    class _HTMLFetcher(BaseScraper):
        async def extract(self, url: str = "", **_):
            return await self.get(url or "")

    use_browser = use_browser and BROWSER_MODE_AVAILABLE
    fetcher = _HTMLFetcher(
        stealth=bool(STEALTH_AVAILABLE),
        proxy=None,
        timeout=30,
        browser_mode=use_browser,
        max_retries=2,
    )
    try:
        result = await fetcher.run(url=url)
        if isinstance(result, dict):
            html = result.get("text", result.get("body", "")) or ""
            status = int(result.get("status", result.get("status_code", 200)))
        else:
            html = str(result) if result else ""
            status = 200
        if isinstance(html, bytes):
            html = html.decode("utf-8", errors="replace")
        return (html or "")[:500_000], status
    finally:
        await fetcher.close()


def _plausibility(name: Optional[str], phone: Optional[str], email: Optional[str]) -> str:
    """One of PLAUSIBLE, GARBAGE, EMPTY, UNKNOWN."""
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return "UNKNOWN"
    try:
        from openai import OpenAI

        client = OpenAI(api_key=key)
        prompt = f"""Given these strings extracted from a people-search page:
name={repr(name or '')}
phone={repr(phone or '')}
email={repr(email or '')}

Are they PLAUSIBLE person data, GARBAGE (ads/nav/random), or EMPTY? Reply with exactly one word: PLAUSIBLE, GARBAGE, or EMPTY."""
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=10,
        )
        text = (resp.choices[0].message.content or "").strip().upper()
        if "PLAUSIBLE" in text:
            return "PLAUSIBLE"
        if "GARBAGE" in text:
            return "GARBAGE"
        if "EMPTY" in text:
            return "EMPTY"
        return "UNKNOWN"
    except Exception as e:
        logger.debug("auto_map plausibility LLM failed: %s", e)
        return "UNKNOWN"


async def attempt_auto_map(domain: str, target_url: Optional[str] = None) -> Dict[str, Any]:
    """
    Try to produce and verify a blueprint for `domain`. Uses heuristics, apply_to_html, validators, and optional LLM plausibility.
    Returns: {status, committed, pending, blueprint?, error?}
    """
    r = _get_redis()
    rate_key = f"{AUTO_MAP_RATE_KEY}{domain}"
    if r.get(rate_key):
        return {"status": "rate_limited", "committed": False, "pending": False}

    url = target_url or f"https://{domain}"
    try:
        html, status = await _fetch_html(url, use_browser=False)
    except Exception as e:
        try:
            html, status = await _fetch_html(url, use_browser=True)
        except Exception as e2:
            logger.warning("auto_map fetch failed for %s: %s", domain, e2)
            r.set(rate_key, "1", ex=AUTO_MAP_RATE_TTL)
            return {"status": "fetch_failed", "committed": False, "pending": False, "error": str(e2)}

    if not html or len(html) < 500:
        r.set(rate_key, "1", ex=AUTO_MAP_RATE_TTL)
        return {"status": "empty_html", "committed": False, "pending": False}

    captcha = any(
        x in html.lower() for x in ("captcha", "challenge", "cf-browser-verification", "hcaptcha", "recaptcha")
    )
    if captcha and len(html) < 50_000:
        r.set(rate_key, "1", ex=AUTO_MAP_RATE_TTL)
        return {"status": "captcha", "committed": False, "pending": False}

    extraction, confidence_per = discover(html, url)
    if not extraction:
        r.set(rate_key, "1", ex=AUTO_MAP_RATE_TTL)
        return {"status": "no_selectors", "committed": False, "pending": False}

    overall = overall_confidence(confidence_per, extraction)
    target_url = URL_TEMPLATES.get(domain) or url
    blueprint = {"targetUrl": target_url, "method": "GET", "responseType": "html", "extraction": extraction}

    extractor = BlueprintExtractor(blueprint)
    extracted = extractor.apply_to_html(html)

    format_ok = any(
        [
            is_plausible_phone(extracted.get("phone")),
            is_plausible_email(extracted.get("email")),
            is_plausible_name(extracted.get("name")),
        ]
    )
    plausibility = _plausibility(
        extracted.get("name"),
        extracted.get("phone"),
        extracted.get("email"),
    )

    if overall >= 0.8 and format_ok and plausibility != "GARBAGE":
        try:
            commit_blueprint_impl(domain, blueprint, r)
            r.set(rate_key, "1", ex=AUTO_MAP_RATE_TTL)
            return {"status": "committed", "committed": True, "pending": False, "blueprint": blueprint}
        except Exception as e:
            logger.exception("auto_map commit failed for %s: %s", domain, e)
            r.set(rate_key, "1", ex=AUTO_MAP_RATE_TTL)
            return {"status": "commit_error", "committed": False, "pending": False, "error": str(e)}

    if overall >= 0.5 and extraction:
        try:
            r.set(f"blueprint:{domain}{PENDING_KEY_SUFFIX}", json.dumps(blueprint), ex=PENDING_TTL)
        except Exception:
            pass
        r.set(rate_key, "1", ex=AUTO_MAP_RATE_TTL)
        return {"status": "pending", "committed": False, "pending": True, "blueprint": blueprint}

    r.set(rate_key, "1", ex=AUTO_MAP_RATE_TTL)
    return {"status": "rejected", "committed": False, "pending": False}
