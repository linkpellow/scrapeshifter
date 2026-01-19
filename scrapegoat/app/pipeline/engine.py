"""
Pipeline Engine: Orchestrates stations with stop conditions and cost tracking
"""
import time
import datetime
from typing import List, Dict, Any, Optional
from loguru import logger
from .types import PipelineContext, StopCondition
from .station import PipelineStation


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
    ) -> Dict[str, Any]:
        """
        Execute the pipeline route with full tracking.
        step_collector: If provided, append per-station {station, duration_ms, condition, status, error?, recent_logs?}.
        log_buffer: If provided, on station exception the failing step gets recent_logs=last 20 lines for where/why.
        """
        ctx = PipelineContext(data=initial_data.copy(), budget_limit=self.budget_limit)
        steps = step_collector

        logger.info(f"🚀 Starting pipeline with {len(self.route)} stations (budget: ${self.budget_limit:.2f})")

        for station in self.route:
            t0 = time.perf_counter()
            started_at = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
            try:
                logger.debug(f"📍 Executing: {station.name}")
                result_data, condition = await station.execute(ctx)
                duration_ms = int((time.perf_counter() - t0) * 1000)
                if steps is not None:
                    status = "ok" if condition == StopCondition.CONTINUE else ("stop" if condition == StopCondition.SKIP_REMAINING else "fail")
                    steps.append({"station": station.name, "started_at": started_at, "duration_ms": duration_ms, "condition": condition.value, "status": status})
                actual_cost = station.cost_estimate
                ctx.update(result_data, station.name, actual_cost, condition)
                if condition == StopCondition.SKIP_REMAINING:
                    logger.info(f"🛑 Stop Condition hit at {station.name}. Finishing early.")
                    break
                if condition == StopCondition.FAIL:
                    logger.warning(f"⚠️  Station {station.name} failed.")
                    continue
                logger.debug(f"✅ {station.name} completed (cost: ${actual_cost:.4f}, total: ${ctx.total_cost:.4f})")
            except Exception as e:
                duration_ms = int((time.perf_counter() - t0) * 1000)
                recent = (log_buffer[-20:] if log_buffer and len(log_buffer) > 0 else []) if log_buffer else []
                if steps is not None:
                    step_entry = {"station": station.name, "started_at": started_at, "duration_ms": duration_ms, "condition": "fail", "status": "fail", "error": str(e)}
                    if recent:
                        step_entry["recent_logs"] = recent
                    steps.append(step_entry)
                logger.exception(f"💥 Critical Failure at {station.name}: {e}")
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
