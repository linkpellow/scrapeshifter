"""
Pipeline Station Implementations
Wraps existing enrichment logic into contract-based stations
"""
import asyncio
import json
import os
import time
import uuid
import urllib.request
from typing import Dict, Any, Tuple, Optional
from loguru import logger
import redis

from app.pipeline.station import PipelineStation
from app.pipeline.types import PipelineContext, StopCondition
from app.pipeline.router import (
    select_provider,
    get_next_provider,
    record_result,
    get_lead_state,
)
from app.pipeline.stats import (
    get_preferred_carrier_for_domain,
    record_carrier_result,
)
from app.pipeline.validator import (
    record_data_point,
    is_high_value,
    check_cross_source,
    apply_consensus_protocol,
)

# Import existing enrichment functions
from app.enrichment.identity_resolution import resolve_identity
from app.enrichment.scraper_enrichment import enrich_with_scraper, scrape_enrich
from app.enrichment.skip_tracing import skip_trace
from app.enrichment.telnyx_gatekeep import validate_phone_telnyx
# scrub_dnc (DNC) disabled for now – DNCGatekeeperStation is a no-op
from app.enrichment.demographics import enrich_demographics
from app.enrichment.database import save_to_database


def _get_chimera_brain_http_url() -> Optional[str]:
    u = os.getenv("CHIMERA_BRAIN_HTTP_URL")
    if u:
        return u.rstrip("/")
    a = os.getenv("CHIMERA_BRAIN_ADDRESS", "")
    if a and "50051" in a:
        return a.replace("50051", "8080").rstrip("/")
    return "http://localhost:8080"


def _hive_predict_path(lead: Dict[str, Any]) -> Optional[str]:
    url = _get_chimera_brain_http_url()
    if not url:
        return None
    try:
        req = urllib.request.Request(
            f"{url}/api/hive-mind/predict-path",
            data=json.dumps({"lead_data": lead}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            out = json.loads(resp.read().decode())
            return (out or {}).get("provider") or None
    except Exception:
        return None


def _hive_store_pattern(company: str, city: str, title: str, data_found: Dict[str, Any]) -> None:
    url = _get_chimera_brain_http_url()
    if not url:
        return
    try:
        req = urllib.request.Request(
            f"{url}/api/hive-mind/store-pattern",
            data=json.dumps({"company": company, "city": city, "title": title, "data_found": data_found}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass


class IdentityStation(PipelineStation):
    """
    Station 1: Identity Resolution
    Resolves raw LinkedIn/Facebook data into structured identity
    """
    
    @property
    def name(self) -> str:
        return "Identity Resolution"
    
    @property
    def required_inputs(self) -> set:
        return {"name"}  # At minimum, we need a name
    
    @property
    def produces_outputs(self) -> set:
        return {"firstName", "lastName", "city", "state", "zipcode", "linkedinUrl", "company", "title"}
    
    @property
    def cost_estimate(self) -> float:
        return 0.0  # Free - just parsing
    
    async def process(self, ctx: PipelineContext) -> Tuple[Dict[str, Any], StopCondition]:
        """Resolve identity from raw lead data"""
        try:
            result = resolve_identity(ctx.data)
            
            # Validate required outputs
            if not result.get('firstName') or not result.get('lastName'):
                logger.warning("Identity resolution failed: missing firstName or lastName")
                return {}, StopCondition.FAIL
            
            logger.info(f"✅ Identity resolved: {result.get('firstName')} {result.get('lastName')}")
            return result, StopCondition.CONTINUE
            
        except Exception as e:
            logger.error(f"Identity resolution error: {e}")
            return {}, StopCondition.FAIL


class ChimeraStation(PipelineStation):
    """
    Chimera Deep Search: delegates to Chimera Core (V4) via Redis.

    GPS Router: Epsilon-Greedy provider selection from the Magazine (FastPeopleSearch,
    TruePeopleSearch, ZabaSearch, SearchPeopleFree, ThatsThem, AnyWho). On failure,
    re-queues the lead for the next provider. Records success/fail/captcha/latency
    for the heatmap.

    Mission format: target_provider (from router), instruction=deep_search, lead.
    """

    CHIMERA_MISSIONS = "chimera:missions"
    CHIMERA_RESULTS_PREFIX = "chimera:results:"
    SYSTEM_STATE_PAUSED = "SYSTEM_STATE:PAUSED"
    DEFAULT_TIMEOUT = int(os.getenv("CHIMERA_STATION_TIMEOUT", "120"))
    PAUSE_POLL_SEC = 15
    PAUSE_WAIT_MAX = 120

    @property
    def name(self) -> str:
        return "Chimera Deep Search"

    @property
    def required_inputs(self) -> set:
        return {"linkedinUrl"}

    @property
    def produces_outputs(self) -> set:
        return {"chimera_income", "chimera_age", "chimera_phone", "chimera_email", "chimera_raw"}

    @property
    def cost_estimate(self) -> float:
        return 0.05

    def _get_redis(self) -> redis.Redis:
        url = os.getenv("REDIS_URL") or os.getenv("APP_REDIS_URL") or "redis://localhost:6379"
        return redis.from_url(url)

    async def process(self, ctx: PipelineContext) -> Tuple[Dict[str, Any], StopCondition]:
        linkedin_url = ctx.data.get("linkedinUrl") or ctx.data.get("linkedin_url") or ""
        if not linkedin_url:
            return {}, StopCondition.FAIL

        r = self._get_redis()
        state = get_lead_state(ctx.data)

        # Pause-on-failure: do not push if SYSTEM_STATE:PAUSED
        try:
            waited = 0
            while waited < self.PAUSE_WAIT_MAX and r.get(self.SYSTEM_STATE_PAUSED):
                logger.warning(f"SYSTEM_STATE:PAUSED set; waiting up to {self.PAUSE_WAIT_MAX - waited}s")
                await asyncio.sleep(min(self.PAUSE_POLL_SEC, self.PAUSE_WAIT_MAX - waited))
                waited += self.PAUSE_POLL_SEC
            if r.get(self.SYSTEM_STATE_PAUSED):
                logger.warning("SYSTEM_STATE:PAUSED still set after wait; skipping Chimera")
                return {}, StopCondition.CONTINUE
        except Exception as e:
            logger.debug(f"SYSTEM_STATE:PAUSED check failed: {e}")

        tried: set = set()
        failed_provider: Optional[str] = None
        loop_exec = asyncio.get_event_loop()

        # Hive Mind: Path of Least Resistance (predict_path biases provider choice)
        preferred = _hive_predict_path(ctx.data)

        while True:
            if not tried:
                provider = select_provider(ctx.data, r, tried=tried, preferred=preferred)
            else:
                if failed_provider is None:
                    break
                provider = get_next_provider(failed_provider, tried=tried, r=r)
                if provider is None:
                    logger.warning("Chimera: all Magazine providers exhausted")
                    return {}, StopCondition.CONTINUE
            tried.add(provider)

            domain = (provider or "").lower().replace(" ", "")
            domain = domain if "." in domain else f"{domain}.com"
            carrier = get_preferred_carrier_for_domain(domain, r)

            mission_id = str(uuid.uuid4())
            results_key = f"{self.CHIMERA_RESULTS_PREFIX}{mission_id}"
            mission = {
                "mission_id": mission_id,
                "lead": {**ctx.data, "target_provider": provider},
                "instruction": "deep_search",
                "linkedin_url": linkedin_url,
                "target": "linkedin_profile",
                "target_provider": provider,
                "carrier": carrier,
            }
            if ctx.data.get("_blueprint"):
                mission["blueprint"] = ctx.data["_blueprint"]

            try:
                t0 = time.perf_counter()
                r.lpush(self.CHIMERA_MISSIONS, json.dumps(mission))
                logger.info(f"Chimera mission queued: {mission_id} provider={provider}")

                raw = await loop_exec.run_in_executor(
                    None,
                    lambda k=results_key: r.brpop(k, timeout=self.DEFAULT_TIMEOUT),
                )
                elapsed_ms = (time.perf_counter() - t0) * 1000
            except Exception as e:
                logger.warning(f"Chimera station error: {e}")
                record_result(provider, state, success=False, latency_ms=self.DEFAULT_TIMEOUT * 1000, r=r)
                record_carrier_result(domain, carrier or "default", False, r)
                failed_provider = provider
                continue

            if raw is None:
                logger.warning(f"Chimera results timeout for {mission_id} (provider={provider})")
                record_result(provider, state, success=False, latency_ms=self.DEFAULT_TIMEOUT * 1000, r=r)
                record_carrier_result(domain, carrier or "default", False, r)
                failed_provider = provider
                continue

            try:
                _, payload = raw
                data = json.loads(payload.decode("utf-8") if isinstance(payload, bytes) else payload)
            except Exception as parse_err:
                logger.warning(f"Chimera result parse error for {mission_id} (provider={provider}): {parse_err}")
                record_result(provider, state, success=False, latency_ms=elapsed_ms, r=r)
                record_carrier_result(domain, carrier or "default", False, r)
                failed_provider = provider
                continue

            try:
                r.delete(results_key)
            except Exception:
                pass

            if not isinstance(data, dict):
                logger.warning(f"Chimera result not a dict for {mission_id} (provider={provider})")
                record_result(provider, state, success=False, latency_ms=elapsed_ms, r=r)
                record_carrier_result(domain, carrier or "default", False, r)
                failed_provider = provider
                continue

            if data.get("status") == "failed":
                err = data.get("error")
                if err is None and data.get("errors"):
                    err = data["errors"] if isinstance(data.get("errors"), str) else " | ".join(data.get("errors") or [])
                if err is None:
                    err = "no message"
                logger.warning(f"Chimera result status=failed: mission_id={mission_id} provider={provider} error={err}")
                record_result(provider, state, success=False, latency_ms=elapsed_ms, r=r)
                record_carrier_result(domain, carrier or "default", False, r)
                failed_provider = provider
                continue

            # Success: update GPS heatmap and carrier health
            captcha_solved = data.get("captcha_solved") is True
            datatypes_found = [k for k in ("phone", "age", "income") if data.get(k)]
            record_result(
                provider, state, success=True, latency_ms=elapsed_ms,
                captcha_solved=captcha_solved, datatypes_found=datatypes_found, r=r
            )
            record_carrier_result(domain, carrier or "default", True, r)

            # Entropy poison: if same phone/email for >3 leads in 60min, blacklist (record_data_point does it)
            for typ, key in [("phone", "phone"), ("email", "email")]:
                val = data.get(key)
                if val is not None and val:
                    record_data_point(provider, typ, val, linkedin_url, r)

            out = {}
            for k in ("income", "age", "phone", "email"):
                if k in data and data[k] is not None:
                    out[f"chimera_{k}"] = data[k]
            out["chimera_raw"] = data

            # 2026 Consensus: if vision_confidence < 0.95, set NEEDS_OLMOCR_VERIFICATION
            out.update(apply_consensus_protocol(data))

            # Hive Mind: store successful pattern for Path of Least Resistance
            _hive_store_pattern(
                company=(ctx.data.get("company") or ctx.data.get("Company") or ""),
                city=(ctx.data.get("city") or ctx.data.get("City") or ""),
                title=(ctx.data.get("title") or ctx.data.get("headline") or ctx.data.get("job_title") or ""),
                data_found={"provider": provider, "phone": data.get("phone"), "age": data.get("age"), "income": data.get("income")},
            )

            # Cross-Source Consensus: for high-value, run second provider; if results differ -> NEEDS_RECONCILIATION
            if is_high_value(ctx.data):
                second = get_next_provider(provider, tried=tried, r=r)
                if second:
                    mission_id2 = str(uuid.uuid4())
                    results_key2 = f"{self.CHIMERA_RESULTS_PREFIX}{mission_id2}"
                    mission2 = {
                        "mission_id": mission_id2,
                        "lead": {**ctx.data, "target_provider": second},
                        "instruction": "deep_search",
                        "linkedin_url": linkedin_url,
                        "target": "linkedin_profile",
                        "target_provider": second,
                    }
                    if ctx.data.get("_blueprint"):
                        mission2["blueprint"] = ctx.data["_blueprint"]
                    try:
                        r.lpush(self.CHIMERA_MISSIONS, json.dumps(mission2))
                        raw2 = await loop_exec.run_in_executor(
                            None,
                            lambda k=results_key2: r.brpop(k, timeout=self.DEFAULT_TIMEOUT),
                        )
                        if raw2:
                            try:
                                _, pl = raw2
                                data2 = json.loads(pl.decode("utf-8") if isinstance(pl, bytes) else pl)
                                if isinstance(data2, dict) and data2.get("status") != "failed":
                                    record_result(
                                        second, state, success=True, latency_ms=0,
                                        captcha_solved=data2.get("captcha_solved") is True,
                                        datatypes_found=[k for k in ("phone", "age", "income") if data2.get(k)],
                                        r=r,
                                    )
                                    if check_cross_source(data, data2):
                                        out["NEEDS_RECONCILIATION"] = True
                                        logger.warning("Chimera: high-value lead NEEDS_RECONCILIATION (two providers differ)")
                            except Exception as e2:
                                logger.debug("Chimera cross-source second run: %s", e2)
                            try:
                                r.delete(results_key2)
                            except Exception:
                                pass
                    except Exception as e2:
                        logger.debug("Chimera cross-source: %s", e2)

            logger.info(f"Chimera result for {mission_id}: provider={provider} {list(out.keys())}")
            return out, StopCondition.CONTINUE

        return {}, StopCondition.CONTINUE


class ScraperEnrichmentStation(PipelineStation):
    """
    Station 2a: Scraper-Based Enrichment (Preferred)
    Uses free scrapers to find phone, age, income
    """
    
    @property
    def name(self) -> str:
        return "Scraper Enrichment"
    
    @property
    def required_inputs(self) -> set:
        return {"firstName", "lastName", "city", "state"}
    
    @property
    def produces_outputs(self) -> set:
        return {"phone", "age", "income", "address", "email"}
    
    @property
    def cost_estimate(self) -> float:
        return 0.0  # Free scraping (uses proxies, but no API costs)
    
    async def process(self, ctx: PipelineContext) -> Tuple[Dict[str, Any], StopCondition]:
        """Enrich using scrapers (free alternative to skip-tracing)"""
        try:
            # Use async version directly
            result = await scrape_enrich(ctx.data)
            
            if result.get('phone'):
                logger.info(f"✅ Scraper found phone: {result.get('phone')}")
                return result, StopCondition.CONTINUE
            else:
                logger.info("⚠️  Scraper enrichment found no phone - will fallback to skip-tracing")
                return result, StopCondition.CONTINUE  # Continue to allow fallback
            
        except Exception as e:
            logger.error(f"Scraper enrichment error: {e}")
            return {}, StopCondition.CONTINUE  # Don't fail - allow skip-tracing fallback


class SkipTracingStation(PipelineStation):
    """
    Station 2b: Skip-Tracing API (Fallback)
    Uses paid APIs to find phone and email
    """
    
    @property
    def name(self) -> str:
        return "Skip-Tracing API"
    
    @property
    def required_inputs(self) -> set:
        return {"firstName", "lastName", "city", "state"}
    
    @property
    def produces_outputs(self) -> set:
        return {"phone", "email"}
    
    @property
    def cost_estimate(self) -> float:
        return 0.15  # Estimated cost per API call
    
    async def process(self, ctx: PipelineContext) -> Tuple[Dict[str, Any], StopCondition]:
        """Skip-trace using paid APIs (fallback if scraper fails)"""
        # Only run if phone not already found
        if ctx.data.get('phone'):
            logger.info("Phone already found, skipping skip-tracing")
            return {}, StopCondition.CONTINUE
        
        try:
            # Run sync function in thread pool
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, skip_trace, ctx.data)
            
            if result.get('phone'):
                logger.info(f"✅ Skip-tracing found phone: {result.get('phone')}")
                return result, StopCondition.CONTINUE
            else:
                logger.warning("❌ Skip-tracing failed: No phone found")
                return {}, StopCondition.FAIL  # Fail if no phone found
            
        except Exception as e:
            logger.error(f"Skip-tracing error: {e}")
            return {}, StopCondition.FAIL


class TelnyxGatekeepStation(PipelineStation):
    """
    Station 3: Telnyx Gatekeep (Cost Saver)
    Validates phone and filters VOIP/Landline/junk carriers
    CRITICAL: Stops enrichment early to save API costs
    """
    
    @property
    def name(self) -> str:
        return "Telnyx Gatekeep"
    
    @property
    def required_inputs(self) -> set:
        return {"phone"}
    
    @property
    def produces_outputs(self) -> set:
        return {"is_valid", "is_mobile", "is_voip", "is_landline", "carrier", "is_junk"}
    
    @property
    def cost_estimate(self) -> float:
        return 0.01  # Telnyx API cost
    
    async def process(self, ctx: PipelineContext) -> Tuple[Dict[str, Any], StopCondition]:
        """Validate phone via Telnyx - STOP if invalid to save costs"""
        phone = ctx.data.get('phone')
        if not phone:
            return {}, StopCondition.FAIL
        
        try:
            # Run sync function in thread pool
            loop = asyncio.get_event_loop()
            validation = await loop.run_in_executor(None, validate_phone_telnyx, phone)
            
            # Check if we should reject
            is_junk = validation.get('is_junk', False)
            is_voip = validation.get('is_voip', False)
            is_landline = validation.get('is_landline', False)
            is_mobile = validation.get('is_mobile', False)
            
            # Reject if junk, VOIP, or landline (only mobile is acceptable)
            if is_junk or is_voip or (is_landline and not is_mobile):
                logger.warning(f"🚫 Phone rejected: {validation.get('carrier')} ({'VOIP' if is_voip else 'Landline' if is_landline else 'Junk'})")
                return validation, StopCondition.SKIP_REMAINING  # STOP HERE - save costs
            
            logger.info(f"✅ Phone validated: {validation.get('carrier')} (Mobile)")
            return validation, StopCondition.CONTINUE
            
        except Exception as e:
            logger.error(f"Telnyx validation error: {e}")
            # Fail open - continue if validation fails
            return {}, StopCondition.CONTINUE


class DNCGatekeeperStation(PipelineStation):
    """
    Station 4: DNC Scrubbing
    DNC DISABLED: No-op, always continues. Set dnc_status=SKIPPED, can_contact=True.
    To re-enable: call scrub_dnc(phone) and handle SKIP_REMAINING when can_contact=False.
    """
    
    @property
    def name(self) -> str:
        return "DNC Scrubbing (disabled)"
    
    @property
    def required_inputs(self) -> set:
        return set()  # No required inputs when disabled
    
    @property
    def produces_outputs(self) -> set:
        return {"dnc_status", "can_contact"}
    
    @property
    def cost_estimate(self) -> float:
        return 0.0  # No API call when disabled
    
    async def process(self, ctx: PipelineContext) -> Tuple[Dict[str, Any], StopCondition]:
        """No-op: DNC disabled. Always continue with can_contact=True."""
        return {"dnc_status": "SKIPPED", "can_contact": True}, StopCondition.CONTINUE


class DemographicsStation(PipelineStation):
    """
    Station 5: Demographic Enrichment
    Pulls census data (income, age, address)
    """
    
    @property
    def name(self) -> str:
        return "Demographic Enrichment"
    
    @property
    def required_inputs(self) -> set:
        return {"zipcode"}  # Need zipcode for census data
    
    @property
    def produces_outputs(self) -> set:
        return {"income", "income_range", "age", "address"}
    
    @property
    def cost_estimate(self) -> float:
        return 0.01  # Census API cost (often free, but estimate conservatively)
    
    async def process(self, ctx: PipelineContext) -> Tuple[Dict[str, Any], StopCondition]:
        """Enrich with demographic data"""
        try:
            # Merge identity location into contact info for enrichment
            contact_info = {
                'zipcode': ctx.data.get('zipcode'),
                'city': ctx.data.get('city'),
                'state': ctx.data.get('state'),
                'age': ctx.data.get('age'),  # May already be from scraper
            }
            
            # Run sync function in thread pool
            loop = asyncio.get_event_loop()
            demographics = await loop.run_in_executor(None, enrich_demographics, contact_info)
            
            if demographics:
                logger.info(f"✅ Demographics enriched: Income={demographics.get('income')}, Age={demographics.get('age')}")
            
            return demographics, StopCondition.CONTINUE
            
        except Exception as e:
            logger.error(f"Demographic enrichment error: {e}")
            return {}, StopCondition.CONTINUE  # Non-critical, continue


class DatabaseSaveStation(PipelineStation):
    """
    Station 6: Database Save
    Saves enriched lead to PostgreSQL with deduplication
    """
    
    @property
    def name(self) -> str:
        return "Database Save"
    
    @property
    def required_inputs(self) -> set:
        return {"linkedinUrl"}  # Need at least LinkedIn URL for deduplication
    
    @property
    def produces_outputs(self) -> set:
        return {"saved", "lead_id"}  # Indicates successful save
    
    @property
    def cost_estimate(self) -> float:
        return 0.0  # Database write is free
    
    async def process(self, ctx: PipelineContext) -> Tuple[Dict[str, Any], StopCondition]:
        """Save enriched lead to database"""
        try:
            # Build enriched lead from context
            enriched_lead = ctx.data.copy()
            
            # Run sync function in thread pool
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(None, save_to_database, enriched_lead)
            
            if success:
                logger.info(f"✅ Lead saved to database: {enriched_lead.get('name', 'Unknown')}")
                return {"saved": True}, StopCondition.CONTINUE
            else:
                logger.error("❌ Failed to save lead to database")
                return {"saved": False}, StopCondition.FAIL
            
        except Exception as e:
            logger.error(f"Database save error: {e}")
            return {"saved": False}, StopCondition.FAIL
