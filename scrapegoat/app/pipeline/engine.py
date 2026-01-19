"""
Pipeline Engine: Orchestrates stations with stop conditions and cost tracking.
Failures are localized with step, reason, and suggested_fix when stations raise
ChimeraEnrichmentError.
"""
import datetime
import time

from loguru import logger

from typing import Any, Dict, List, Optional

from .exceptions import ChimeraEnrichmentError
from .station import PipelineStation
from .types import PipelineContext, StopCondition


class PipelineEngine:
    """
    Production-Grade Pipeline Engine
    
    Features:
    - Contract enforcement (prerequisites)
    - Budget management (auto stop-loss)
    - Stop conditions (early termination)
    - Full cost tracking
    - Error handling
    """
    
    def __init__(self, route: List[PipelineStation], budget_limit: float = 5.0):
        """
        Initialize pipeline engine with a route of stations.
        
        Args:
            route: Ordered list of stations to execute
            budget_limit: Maximum cost per lead (default: $5.00)
        """
        self.route = route
        self.budget_limit = budget_limit
    
    async def run(
        self,
        initial_data: Dict[str, Any],
        step_collector: Optional[List[Dict[str, Any]]] = None,
        log_buffer: Optional[List[str]] = None,
        progress_queue: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Execute the pipeline route with full tracking.
        step_collector: If provided, append per-station {station, duration_ms, condition, status, error?, recent_logs?}.
        log_buffer: If provided, on station exception the failing step gets recent_logs=last 20 lines for where/why.
        progress_queue: If provided (queue.Queue), put {step, total, pct, station, status, message, duration_ms?} at start/end of each station for streaming UX.
        """
        data = initial_data.copy()
        if not data.get("name") and (data.get("fullName") or data.get("full_name") or data.get("Name")):
            data["name"] = data.get("fullName") or data.get("full_name") or data.get("Name") or ""
        if not data.get("name") and (data.get("firstName") or data.get("lastName")):
            data["name"] = f"{data.get('firstName') or ''} {data.get('lastName') or ''}".strip()
        ctx = PipelineContext(data=data, budget_limit=self.budget_limit, progress_queue=progress_queue)
        steps = step_collector
        N = len(self.route)

        logger.info(f"🚀 Starting pipeline with {N} stations (budget: ${self.budget_limit:.2f})")

        for i, station in enumerate(self.route):
            t0 = time.perf_counter()
            started_at = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
            if progress_queue is not None:
                progress_queue.put_nowait({
                    "step": i + 1, "total": N, "pct": int(i / N * 100),
                    "station": station.name, "status": "running",
                    "message": f"Starting {station.name}",
                })
            try:
                result_data, condition = await station.execute(ctx)
                duration_ms = int((time.perf_counter() - t0) * 1000)
                status = "ok" if condition == StopCondition.CONTINUE else ("stop" if condition == StopCondition.SKIP_REMAINING else "fail")
                if steps is not None:
                    steps.append({"station": station.name, "started_at": started_at, "duration_ms": duration_ms, "condition": condition.value, "status": status})
                if progress_queue is not None:
                    progress_queue.put_nowait({
                        "step": i + 1, "total": N, "pct": int((i + 1) / N * 100),
                        "station": station.name, "status": status, "duration_ms": duration_ms,
                        "message": f"{station.name} done" if status == "ok" else f"{station.name} {status}",
                    })
                actual_cost = station.cost_estimate
                ctx.update(result_data, station.name, actual_cost, condition)
                if condition == StopCondition.SKIP_REMAINING:
                    logger.info("🛑 Stop Condition hit at %s. Finishing early.", station.name)
                    break
                if condition == StopCondition.FAIL:
                    logger.warning("⚠️  Station %s failed.", station.name)
                    continue
                logger.debug("✅ %s completed (cost=%.4f, total=%.4f)", station.name, actual_cost, ctx.total_cost)
            except ChimeraEnrichmentError as e:
                duration_ms = int((time.perf_counter() - t0) * 1000)
                recent = (log_buffer[-20:] if log_buffer and len(log_buffer) > 0 else []) if log_buffer else []
                err_msg = f"{e.reason} (step={e.step})"
                if e.suggested_fix:
                    err_msg += f" [suggested_fix: {e.suggested_fix}]"
                if steps is not None:
                    step_entry = {"station": station.name, "started_at": started_at, "duration_ms": duration_ms, "condition": "fail", "status": "fail", "error": err_msg}
                    if e.suggested_fix:
                        step_entry["suggested_fix"] = e.suggested_fix
                    if recent:
                        step_entry["recent_logs"] = recent
                    steps.append(step_entry)
                if progress_queue is not None:
                    progress_queue.put_nowait({
                        "step": i + 1, "total": N, "pct": int((i + 1) / N * 100),
                        "station": station.name, "status": "fail", "duration_ms": duration_ms,
                        "message": f"{station.name} failed", "error": err_msg,
                    })
                logger.exception("💥 ChimeraEnrichmentError at %s: step=%s reason=%s", station.name, e.step, e.reason)
                if e.suggested_fix:
                    logger.info("  Suggested fix: %s", e.suggested_fix)
                ctx.errors.append(err_msg)
            except Exception as e:
                duration_ms = int((time.perf_counter() - t0) * 1000)
                recent = (log_buffer[-20:] if log_buffer and len(log_buffer) > 0 else []) if log_buffer else []
                if steps is not None:
                    step_entry = {"station": station.name, "started_at": started_at, "duration_ms": duration_ms, "condition": "fail", "status": "fail", "error": str(e)}
                    if recent:
                        step_entry["recent_logs"] = recent
                    steps.append(step_entry)
                if progress_queue is not None:
                    progress_queue.put_nowait({
                        "step": i + 1, "total": N, "pct": int((i + 1) / N * 100),
                        "station": station.name, "status": "fail", "duration_ms": duration_ms,
                        "message": f"{station.name} failed", "error": str(e),
                    })
                logger.exception("💥 Critical Failure at %s: %s", station.name, e)
                ctx.errors.append(str(e))
        
        # Final summary
        logger.info(f"🏁 Pipeline complete: ${ctx.total_cost:.4f} spent, {len(ctx.history)} stations executed")
        if ctx.errors:
            logger.warning(f"⚠️  {len(ctx.errors)} errors encountered")
        
        # Add pipeline metadata to final data
        final_data = ctx.data.copy()
        final_data['_pipeline_cost'] = ctx.total_cost
        final_data['_pipeline_stations_executed'] = len(ctx.history)
        final_data['_pipeline_errors'] = len(ctx.errors)
        
        return final_data
    
    def visualize_route(self) -> str:
        """
        Generate a visual representation of the pipeline route.
        
        Returns:
            String representation of the pipeline graph
        """
        lines = ["Pipeline Route:"]
        for i, station in enumerate(self.route, 1):
            inputs = ", ".join(sorted(station.required_inputs)) or "none"
            outputs = ", ".join(sorted(station.produces_outputs)) or "none"
            cost = f"${station.cost_estimate:.4f}"
            
            lines.append(f"  {i}. {station.name}")
            lines.append(f"     Requires: [{inputs}]")
            lines.append(f"     Produces: [{outputs}]")
            lines.append(f"     Cost: {cost}")
        
        return "\n".join(lines)
