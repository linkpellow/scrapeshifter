"""
Core Types & Contracts for Production-Grade Pipeline Engine
"""
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Set
from datetime import datetime


class StopCondition(Enum):
    """Traffic Control: How should the pipeline proceed after this station?"""
    CONTINUE = "continue"           # Normal success, proceed to next station
    SKIP_REMAINING = "skip_rest"    # Success/Stop (e.g., Found DNC match, stop enriching)
    FAIL = "fail"                   # Error occurred, decide based on policy (retry/skip)


@dataclass
class PipelineContext:
    """
    Pipeline Context: Tracks state, costs, and history through the enrichment journey

    This is the "BrainScraper Bus" - carries data through stations with full accounting.
    progress_queue: optional queue.Queue for streaming diagnostic substeps (Blueprint, Chimera pivot/CAPTCHA/extract).
    """
    data: Dict[str, Any]
    budget_limit: float = 5.0       # Max spend per lead (auto stop-loss)

    # Diagnostic streaming: stations can put {"station", "substep", "detail"} for live UX and root-cause diagnosis
    progress_queue: Any = None

    # Internal Tracking
    history: List[Dict[str, Any]] = field(default_factory=list)
    total_cost: float = 0.0
    errors: List[str] = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.now)
    
    def update(
        self, 
        new_data: Dict[str, Any], 
        station_name: str, 
        cost: float, 
        status: StopCondition,
        error: str = None
    ) -> None:
        """
        Updates state, tracks cost, and logs history
        
        Args:
            new_data: New fields added by this station
            station_name: Name of the station that ran
            cost: Actual cost incurred (may differ from estimate)
            status: Stop condition returned
            error: Optional error message if status is FAIL
        """
        if new_data:
            self.data.update(new_data)
        
        self.total_cost += cost
        self.history.append({
            "station": station_name,
            "cost": cost,
            "status": status.value,
            "timestamp": datetime.now().isoformat(),
            "error": error
        })
        
        if error:
            self.errors.append(f"{station_name}: {error}")

    @property
    def available_fields(self) -> Set[str]:
        """Returns set of all available data fields (for prerequisite checking)"""
        return set(self.data.keys())
    
    @property
    def remaining_budget(self) -> float:
        """Calculate remaining budget"""
        return max(0.0, self.budget_limit - self.total_cost)
    
    def can_afford(self, estimated_cost: float) -> bool:
        """Check if we can afford this station"""
        return (self.total_cost + estimated_cost) <= self.budget_limit
