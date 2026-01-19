"""
BlueprintLoaderStation - Fetch BLUEPRINT:{domain} before ChimeraStation.

Runs before ChimeraStation. Resolves target provider via GPS router, fetches
BLUEPRINT:{domain} (or blueprint:{domain}) from Redis. If none, triggers
"Mapping Required" to Dojo (PUBLISH dojo:alerts) and sets _mapping_required.
"""

import json
import os
from typing import Any, Dict, Set, Tuple

from loguru import logger
import redis

from app.pipeline.station import PipelineStation
from app.pipeline.types import PipelineContext, StopCondition

try:
    from app.pipeline.router import select_provider
    ROUTER_AVAILABLE = True
except ImportError:
    ROUTER_AVAILABLE = False

BLUEPRINT_PREFIX = "BLUEPRINT:"
LEGACY_PREFIX = "blueprint:"
DOJO_ALERTS = "dojo:alerts"

_PROVIDER_TO_DOMAIN = {
    "FastPeopleSearch": "fastpeoplesearch.com",
    "TruePeopleSearch": "truepeoplesearch.com",
    "ZabaSearch": "zabasearch.com",
    "SearchPeopleFree": "searchpeoplefree.com",
    "ThatsThem": "thatsthem.com",
    "AnyWho": "anywho.com",
}


class BlueprintLoaderStation(PipelineStation):
    @property
    def name(self) -> str:
        return "Blueprint Loader"

    @property
    def required_inputs(self) -> Set[str]:
        return {"linkedinUrl"}

    @property
    def produces_outputs(self) -> Set[str]:
        return set()  # _blueprint, _mapping_required are internal

    @property
    def cost_estimate(self) -> float:
        return 0.0

    def _get_redis(self) -> redis.Redis:
        url = os.getenv("REDIS_URL") or os.getenv("APP_REDIS_URL") or "redis://localhost:6379"
        return redis.from_url(url, decode_responses=True)

    def _emit(self, ctx: PipelineContext, substep: str, detail: str) -> None:
        q = getattr(ctx, "progress_queue", None)
        if q is not None:
            try:
                q.put_nowait({"station": "Blueprint Loader", "substep": substep, "detail": detail})
            except Exception:
                pass

    async def process(self, ctx: PipelineContext) -> Tuple[Dict[str, Any], StopCondition]:
        out: Dict[str, Any] = {}
        r = self._get_redis()

        provider = None
        if ROUTER_AVAILABLE:
            try:
                provider = select_provider(ctx.data, r, tried=set())
            except Exception as e:
                logger.warning(
                    "Blueprint Loader: select_provider failed (linkedin=%s): %s",
                    (ctx.data.get("linkedinUrl") or "?")[:60], e,
                )
        if not provider:
            provider = "TruePeopleSearch"

        domain = _PROVIDER_TO_DOMAIN.get(provider) or provider.replace(" ", "").lower() + ".com"
        self._emit(ctx, "loading", domain)

        # Fetch BLUEPRINT:{domain} then blueprint:{domain}
        raw = None
        for prefix in (BLUEPRINT_PREFIX, LEGACY_PREFIX):
            key = f"{prefix}{domain}"
            try:
                raw = r.hgetall(key)
                if raw:
                    break
            except Exception as e:
                logger.warning("Blueprint Loader: Redis hgetall failed for key=%s: %s", key, e)

        if raw and isinstance(raw, dict):
            data_str = raw.get("data") or raw.get("blueprint_json")
            if data_str:
                try:
                    bp = json.loads(data_str)
                    out["_blueprint"] = bp
                    out["_blueprint_domain"] = domain
                    self._emit(ctx, "loaded", domain)
                    logger.info("Blueprint Loader: loaded for %s", domain)
                    return out, StopCondition.CONTINUE
                except Exception as e:
                    logger.exception(
                        "Blueprint Loader: failed to parse blueprint JSON (domain=%s): %s",
                        domain, e,
                    )
            # Fallback: use hash as blueprint-like map
            instr = raw.get("instructions")
            if isinstance(instr, str):
                try:
                    out["_blueprint"] = {"instructions": json.loads(instr), "domain": domain}
                    self._emit(ctx, "loaded_fallback", domain)
                    return out, StopCondition.CONTINUE
                except Exception as e:
                    logger.warning("Blueprint Loader: parse instructions for %s: %s", domain, e)

        # No usable blueprint: try auto-map once (rate-limited per domain)
        self._emit(ctx, "auto_map_attempt", domain)
        try:
            from app.enrichment.auto_map import attempt_auto_map

            res = await attempt_auto_map(domain, target_url=None)
            if res.get("committed") and isinstance(res.get("blueprint"), dict):
                for prefix in (BLUEPRINT_PREFIX, LEGACY_PREFIX):
                    try:
                        raw2 = r.hgetall(f"{prefix}{domain}")
                        if raw2 and isinstance(raw2, dict):
                            data_str = raw2.get("data") or raw2.get("blueprint_json")
                            if data_str:
                                bp = json.loads(data_str)
                                out["_blueprint"] = bp
                                out["_blueprint_domain"] = domain
                                self._emit(ctx, "auto_mapped_loaded", domain)
                                logger.info("Blueprint Loader: auto-mapped and loaded for %s", domain)
                                return out, StopCondition.CONTINUE
                    except Exception:
                        pass
        except Exception as e:
            logger.warning("Blueprint Loader: attempt_auto_map failed (domain=%s): %s", domain, e)
            self._emit(ctx, "auto_map_fail", str(e)[:200])

        try:
            r.publish(DOJO_ALERTS, json.dumps({"type": "mapping_required", "domain": domain}))
            r.sadd("dojo:domains_need_mapping", domain)
        except Exception as e:
            logger.warning("Blueprint Loader: publish dojo:alerts failed (domain=%s): %s", domain, e)
        out["_mapping_required"] = domain
        self._emit(ctx, "mapping_required", domain)
        logger.warning("Blueprint Loader: no blueprint for %s; Mapping Required", domain)
        return out, StopCondition.CONTINUE
