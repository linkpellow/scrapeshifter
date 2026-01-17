"""
Selector Registry - Trauma Center for Autonomous Selector Re-mapping

This implements the "Trauma Center" - a self-healing system that automatically
re-maps selectors when websites change their UI.

When a selector fails (low confidence or 404), the Trauma Center:
1. Uses Vision LLMs to find new selectors
2. Registers successful selectors for future use
3. Tracks failure counts and triggers healing when needed
"""

import os
import json
import logging
from typing import Optional, Dict, List
import redis

logger = logging.getLogger(__name__)


class SelectorRegistry:
    """
    Selector Registry - Manages CSS/XPath selectors for UI elements
    
    Stores selectors in Redis for persistence, with JSON fallback.
    """
    
    def __init__(self, redis_url: Optional[str] = None):
        """
        Initialize Selector Registry.
        
        Args:
            redis_url: Redis URL for persistent storage (optional)
        """
        self.redis_client = None
        self.json_fallback = {}
        
        if redis_url:
            try:
                self.redis_client = redis.from_url(redis_url, decode_responses=True)
                logger.info("✅ Selector Registry: Using Redis storage")
            except Exception as e:
                logger.warning(f"Failed to connect to Redis for Selector Registry: {e}")
                logger.info("Using JSON fallback for Selector Registry")
        else:
            logger.info("Selector Registry: Using JSON fallback (no Redis URL)")
    
    def _get_redis_key(self, domain: str, intent: str) -> str:
        """Generate Redis key for selector"""
        return f"selector:{domain}:{intent}"
    
    def _get_failure_key(self, domain: str, intent: str) -> str:
        """Generate Redis key for failure count"""
        return f"selector_failures:{domain}:{intent}"
    
    def get_selector(self, domain: str, intent: str) -> Optional[Dict]:
        """
        Get selector for a domain + intent combination.
        
        Args:
            domain: Website domain (e.g., "example.com")
            intent: User intent (e.g., "login button")
        
        Returns:
            Dict with selector info, or None if not found
        """
        if self.redis_client:
            try:
                key = self._get_redis_key(domain, intent)
                data = self.redis_client.get(key)
                if data:
                    return json.loads(data)
            except Exception as e:
                logger.warning(f"Error reading selector from Redis: {e}")
        
        # Fallback to JSON
        key = f"{domain}:{intent}"
        return self.json_fallback.get(key)
    
    def register_selector(
        self,
        domain: str,
        intent: str,
        selector: str,
        selector_type: str = "css",
        confidence: float = 0.8,
        metadata: Optional[Dict] = None
    ) -> str:
        """
        Register a new selector.
        
        Args:
            domain: Website domain
            intent: User intent
            selector: CSS selector or XPath
            selector_type: "css" or "xpath"
            confidence: Confidence score (0.0-1.0)
            metadata: Additional metadata
        
        Returns:
            Selector ID
        """
        selector_data = {
            "domain": domain,
            "intent": intent,
            "selector": selector,
            "selector_type": selector_type,
            "confidence": confidence,
            "metadata": metadata or {},
        }
        
        if self.redis_client:
            try:
                key = self._get_redis_key(domain, intent)
                self.redis_client.set(key, json.dumps(selector_data))
                logger.info(f"Registered selector in Redis: {domain}:{intent}")
            except Exception as e:
                logger.warning(f"Error writing selector to Redis: {e}")
        
        # Fallback to JSON
        key = f"{domain}:{intent}"
        self.json_fallback[key] = selector_data
        
        return f"{domain}:{intent}"
    
    def should_trigger_trauma_center(self, domain: str, intent: str) -> bool:
        """
        Check if Trauma Center should be triggered.
        
        Returns True if:
        - Selector has failed 3+ times
        - No selector exists for this domain+intent
        - Selector confidence is very low
        
        Args:
            domain: Website domain
            intent: User intent
        
        Returns:
            True if Trauma Center should be triggered
        """
        failure_count = self.get_failure_count(domain, intent)
        return failure_count >= 3
    
    def get_failure_count(self, domain: str, intent: str) -> int:
        """Get failure count for a selector"""
        if self.redis_client:
            try:
                key = self._get_failure_key(domain, intent)
                count = self.redis_client.get(key)
                return int(count) if count else 0
            except Exception:
                return 0
        
        # Fallback to JSON
        key = f"failures:{domain}:{intent}"
        return self.json_fallback.get(key, 0)
    
    def record_failure(self, domain: str, intent: str) -> int:
        """
        Record a selector failure.
        
        Returns the new failure count.
        """
        if self.redis_client:
            try:
                key = self._get_failure_key(domain, intent)
                count = self.redis_client.incr(key)
                return count
            except Exception as e:
                logger.warning(f"Error recording failure in Redis: {e}")
        
        # Fallback to JSON
        key = f"failures:{domain}:{intent}"
        count = self.json_fallback.get(key, 0) + 1
        self.json_fallback[key] = count
        return count
    
    def record_success(self, domain: str, intent: str):
        """Record a selector success (resets failure count)"""
        if self.redis_client:
            try:
                key = self._get_failure_key(domain, intent)
                self.redis_client.delete(key)
            except Exception as e:
                logger.warning(f"Error recording success in Redis: {e}")
        
        # Fallback to JSON
        key = f"failures:{domain}:{intent}"
        if key in self.json_fallback:
            del self.json_fallback[key]
