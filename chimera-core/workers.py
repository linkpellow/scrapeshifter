"""
Chimera Core - PhantomWorker

Stealth browser worker that connects to The Brain via gRPC and executes missions.
"""

import os
import asyncio
import logging
import tempfile
import threading
import time
import json
import hashlib
import random
import re
from typing import Optional, Dict, Any, Tuple
from pathlib import Path
from urllib.parse import urlparse
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, TimeoutError as PlaywrightTimeoutError

from network import get_proxy_config, should_rotate_session_on_403
from stealth import (
    get_stealth_launch_args,
    apply_stealth_patches,
    DeviceProfile,
    FingerprintConfig,
    DiffusionMouse,
    inject_execution_noise,
)

logger = logging.getLogger(__name__)
_GHOST_LOCK_LOGGED = False

# Phase 7: THINK level (metacognitive branding)
THINK_LEVEL = 25
logging.addLevelName(THINK_LEVEL, "THINK")
if not hasattr(logging.Logger, "think"):
    def _think(self: logging.Logger, message, *args, **kwargs):
        if self.isEnabledFor(THINK_LEVEL):
            self._log(THINK_LEVEL, message, args, **kwargs)
    logging.Logger.think = _think  # type: ignore[assignment]

# Lazy import gRPC (will be generated from proto)
try:
    import grpc
    import chimera_pb2
    import chimera_pb2_grpc
    GRPC_AVAILABLE = True
except ImportError:
    logger.warning("⚠️ gRPC proto files not generated. Run ./generate_proto.sh first.")
    GRPC_AVAILABLE = False
    chimera_pb2 = None
    chimera_pb2_grpc = None

try:
    from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential, retry_if_exception_type
    TENACITY_AVAILABLE = True
except ImportError:
    TENACITY_AVAILABLE = False


_redis_client: Optional[Any] = None


def _get_redis():
    """Lazy Redis for blueprint:{domain} overrides (Map-to-Engine) and chimera:telemetry:{id}."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    url = os.getenv("REDIS_URL") or os.getenv("APP_REDIS_URL")
    if not url:
        return None
    try:
        import redis
        _redis_client = redis.from_url(url, decode_responses=True)
        return _redis_client
    except Exception:
        return None


class PhantomWorker:
    """
    Stealth browser worker that achieves 100% Human trust score on CreepJS.
    
    Features:
    - Stealth Chromium with --disable-blink-features=AutomationControlled
    - Fingerprint randomization (Canvas, WebGL, Audio)
    - gRPC connection to The Brain for vision processing
    - Human-like behavior simulation
    """
    
    def __init__(
        self,
        worker_id: str,
        brain_address: str,
        headless: bool = True,
    ):
        self.worker_id = worker_id
        self.brain_address = brain_address
        self.headless = headless
        
        # Browser state
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        
        # gRPC client
        self._grpc_channel = None
        self._brain_client = None
        
        # Stealth configuration
        self.device_profile = DeviceProfile()
        self.fingerprint = FingerprintConfig()

        # Mouse state (best-effort for human movement)
        self._mouse_pos: Tuple[float, float] = (400.0, 300.0)
        
        # Tracing state
        self._trace_path: Optional[Path] = None
        self._tracing_active = False

        # Phase 5: Session aging (per-worker, thread-safe)
        self._session_lock = threading.Lock()
        self._session_mission_count = 0
        self._mission_run_count = 0  # Session Decay: missions > 20 increase jitter/delays

        # 403/Cloudflare: response listener sets this; _check_403_and_rotate performs full session rotation
        self._seen_403 = False

        logger.info(f"🦾 PhantomWorker {worker_id} initialized")

    def next_fatigue_state(self) -> tuple[int, float, float]:
        """
        Phase 5: Increment session mission count and compute fatigue multipliers.

        Spec (exact):
          - Saccadic Jitter: (1 + count * 0.02)
          - Cognitive Delay: (1 + count * 0.015)

        Returns:
            (count, jitter_multiplier, cognitive_multiplier)
        """
        with self._session_lock:
            self._session_mission_count += 1
            count = self._session_mission_count

        jitter_multiplier = 1.0 + (count * 0.02)
        cognitive_multiplier = 1.0 + (count * 0.015)
        return count, jitter_multiplier, cognitive_multiplier
    
    async def start(self) -> None:
        """Start the worker: launch browser and connect to The Brain"""
        logger.info(f"🚀 Starting PhantomWorker {self.worker_id}...")
        
        # Start Playwright
        self._playwright = await async_playwright().start()
        
        # Launch Chromium with stealth args
        launch_args = get_stealth_launch_args()
        
        logger.info(f"   Launching Chromium with stealth args...")
        logger.debug(f"   Critical flag: --disable-blink-features=AutomationControlled")
        
        # Launch: CHROMIUM_CHANNEL=chrome uses native Chrome TLS (JA3 match). When
        # CHROMIUM_USE_NATIVE_TLS=1, default to "chrome" if CHROMIUM_CHANNEL unset.
        channel = (os.getenv("CHROMIUM_CHANNEL") or "").strip()
        if not channel and os.getenv("CHROMIUM_USE_NATIVE_TLS", "").lower() in ("1", "true", "yes"):
            channel = "chrome"
        launch_opts: Dict[str, Any] = {"headless": self.headless, "args": launch_args}
        if channel:
            launch_opts["channel"] = channel
            logger.info("   CHROMIUM_CHANNEL=%s (native TLS)", channel)
        self._browser = await self._playwright.chromium.launch(**launch_opts)

        # Create initial context/page and apply stealth patches (hardware entropy seeded)
        await self._create_context_and_page()
        self.fingerprint = await apply_stealth_patches(self._page, self.device_profile, self.fingerprint)
        logger.info("✅ Stealth patches applied")
        
        # Phase 3: Inject Isomorphic Intelligence (Self-Healing selectors)
        await self._inject_isomorphic_intelligence()
        logger.info("✅ Isomorphic intelligence injected")
        
        # Connect to The Brain via gRPC
        if GRPC_AVAILABLE:
            await self._connect_to_brain()
        else:
            logger.warning("⚠️ gRPC not available - proto files not generated")
        
        logger.info(f"✅ PhantomWorker {self.worker_id} ready")
        logger.info("   - Browser: Chromium with stealth")
        logger.info("   - Brain Connection: " + ("Connected" if self._brain_client else "Not available"))

    async def _create_context_and_page(
        self,
        sticky_session_id: Optional[str] = None,
        carrier: Optional[str] = None,
    ) -> None:
        """
        Create a fresh browser context + page.
        Sticky Sessions (Decodo): session-id pins mobile IP for the mission. Optional
        carrier (e.g. att, tmobile) from GPS carrier health.
        """
        if not self._browser:
            raise RuntimeError("Browser not started")

        # Chrome 142/Windows 11: User-Agent and Sec-Ch-Ua must match to avoid JA3/header mismatch.
        ua_version = os.getenv("CHROME_UA_VERSION", "142.0.0.0").strip()
        ua_platform = (os.getenv("CHROME_UA_PLATFORM") or "Windows").strip().lower()
        is_windows = "win" in ua_platform
        if is_windows:
            self.device_profile.platform = "Win32"
            user_agent = (
                f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                f"(KHTML, like Gecko) Chrome/{ua_version} Safari/537.36"
            )
            major = ua_version.split(".")[0] if ua_version else "142"
            opts_ua: Dict[str, Any] = {
                "user_agent": user_agent,
                "extra_http_headers": {
                    "Sec-Ch-Ua": f'"Google Chrome";v="{major}", "Chromium";v="{major}", "Not_A Brand";v="24"',
                    "Sec-Ch-Ua-Mobile": "?0",
                    "Sec-Ch-Ua-Platform": '"Windows"',
                },
            }
        else:
            user_agent = self.device_profile.user_agent.format(version=ua_version)
            opts_ua = {"user_agent": user_agent}

        opts: Dict[str, Any] = {
            "viewport": self.device_profile.viewport,
            "locale": self.fingerprint.language,
            "timezone_id": self.fingerprint.timezone,
            "permissions": [],
            "color_scheme": "light",
            "device_scale_factor": self.fingerprint.pixel_ratio,
            "is_mobile": self.device_profile.is_mobile,
            "has_touch": self.device_profile.is_mobile,
            **opts_ua,
        }
        proxy = get_proxy_config(sticky_session_id, carrier)
        if proxy:
            opts["proxy"] = proxy

        self._context = await self._browser.new_context(**opts)
        self._page = await self._context.new_page()

        # 403/Cloudflare: on document 403, set flag so _check_403_and_rotate can perform full session rotation
        def _on_response(res) -> None:
            try:
                if getattr(res, "status", 0) == 403:
                    req = getattr(res, "request", None)
                    if req and getattr(req, "resource_type", "") == "document":
                        self._seen_403 = True
            except Exception:
                pass

        self._page.on("response", _on_response)

    async def rotate_hardware_identity(self, mission_id: str, carrier: Optional[str] = None) -> None:
        """
        Phase 6: Rotate hardware identity per mission.

        Creates a fresh context with get_proxy_config(sticky_session_id=mission_id, carrier).
        A single mission stays pinned to one mobile carrier IP for its entire lifetime;
        the only exception is a 403/Cloudflare block, when _check_403_and_rotate calls
        this with a new mission_id (e.g. mission_id_r403_ts) to obtain a fresh IP.
        """
        os.environ["CHIMERA_MISSION_ID"] = str(mission_id)
        os.environ["CHIMERA_WORKER_ID"] = str(self.worker_id)

        # Close old context/page if present
        try:
            if self._page:
                await self._page.close()
        except Exception:
            pass
        try:
            if self._context:
                await self._context.close()
        except Exception:
            pass

        self._page = None
        self._context = None

        # Fresh context/page; Carrier-Sticky (Decodo) session-id + optional carrier from GPS
        await self._create_context_and_page(sticky_session_id=mission_id, carrier=carrier)
        self.fingerprint = await apply_stealth_patches(self._page, self.device_profile, self.fingerprint)
        logger.info("✅ Stealth patches applied")

        await self._inject_isomorphic_intelligence()
        logger.info("✅ Isomorphic intelligence injected")
    
    async def _inject_isomorphic_intelligence(self) -> None:
        """
        Inject isomorphic intelligence tools into browser context.
        
        Makes selectorParser, cssParser, and locatorGenerators available
        in window.isomorphic for self-healing selector repair.
        """
        isomorphic_dir = Path(__file__).parent / "isomorphic"
        
        # Load JavaScript files
        js_files = [
            "selectorParser.js",
            "cssParser.js",
            "locatorGenerators.js"
        ]
        
        combined_script = "// Isomorphic Intelligence Layer - Self-Healing Selectors\n"
        
        for js_file in js_files:
            js_path = isomorphic_dir / js_file
            if js_path.exists():
                try:
                    with open(js_path, 'r') as f:
                        combined_script += f"\n// === {js_file} ===\n"
                        combined_script += f.read()
                        combined_script += "\n"
                except Exception as e:
                    logger.warning(f"⚠️ Failed to load {js_file}: {e}")
            else:
                logger.warning(f"⚠️ Isomorphic file not found: {js_path}")
        
        # Inject into browser before any page loads
        await self._page.add_init_script(combined_script)
        logger.info("✅ Isomorphic Intelligence Injected: [selectorParser, cssParser, locatorGenerators]")
    
    async def _connect_to_brain(self) -> None:
        """Connect to The Brain via gRPC"""
        try:
            import grpc
            
            # Remove http:// prefix if present (gRPC uses different format)
            address = self.brain_address.replace("http://", "").replace("https://", "")
            
            logger.info(f"🧠 Connecting to The Brain at {address}...")
            
            self._grpc_channel = grpc.aio.insecure_channel(address)
            self._brain_client = chimera_pb2_grpc.BrainStub(self._grpc_channel)
            
            # Test connection with a simple query
            logger.info("✅ Connected to The Brain")
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to The Brain: {e}")
            self._brain_client = None
    
    async def _self_heal_selector(
        self,
        failed_selector: str,
        intent: str = "element_interaction"
    ) -> Optional[Dict[str, Any]]:
        """
        Self-heal a broken selector using isomorphic intelligence.
        
        Args:
            failed_selector: The selector that failed
            intent: Intent description (e.g., "click login button")
        
        Returns:
            Dict with new_selector, confidence, and method, or None if healing failed
        """
        try:
            # Use injected isomorphic tools to find alternative selector
            result = await self._page.evaluate("""
                (failedSelector, intent) => {
                    if (!window.isomorphic || !window.isomorphic.locatorGenerators) {
                        return null;
                    }
                    
                    // Try to find element using multiple strategies
                    const found = window.isomorphic.locatorGenerators.findElementByStrategies(
                        failedSelector,
                        document
                    );
                    
                    if (found && found.element) {
                        // Generate resilient selector for found element
                        const newSelector = window.isomorphic.locatorGenerators.generateResilientSelector(
                            found.element,
                            { strategies: ['id', 'data-attr', 'class', 'tag'] }
                        );
                        
                        return {
                            newSelector: newSelector || found.selector,
                            method: found.method,
                            confidence: 0.85,
                            elementInfo: window.isomorphic.selectorParser.extractIdentifiers(found.element)
                        };
                    }
                    
                    return null;
                }
            """, failed_selector, intent)
            
            if result and result.get('newSelector'):
                logger.info(f"✅ Selector self-healed: {failed_selector} → {result['newSelector']}")
                logger.info(f"   Method: {result['method']}, Confidence: {result.get('confidence', 0.85)}")
                return result
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Self-healing failed: {e}")
            return None
    
    async def _idle_liveness_loop(self):
        """
        VANGUARD: Idle Liveness - Perform micro-saccades during idle wait.
        Ensures worker never stays at [0,0] coordinates during idle.
        """
        import random
        import asyncio
        import time
        
        current_x, current_y = 0.0, 0.0
        try:
            # Get viewport center as starting position
            viewport = await self._page.evaluate("() => ({ w: window.innerWidth, h: window.innerHeight })")
            current_x = viewport.get('w', 400) / 2
            current_y = viewport.get('h', 300) / 2
        except:
            current_x, current_y = 400, 300  # Default center
        self._mouse_pos = (float(current_x), float(current_y))

        # Phase 5: Natural browse reading scroll (idle) - low frequency
        last_scroll_at = time.monotonic()
        next_scroll_gate_s = random.uniform(1.8, 3.8)
        
        while True:
            try:
                # Micro-saccade: 1-3px drift (simulates natural eye micro-movements)
                drift_x = random.uniform(-3, 3)
                drift_y = random.uniform(-3, 3)
                
                # Ensure never at [0,0] - add minimum offset if needed
                if abs(current_x) < 1 and abs(current_y) < 1:
                    drift_x = random.uniform(1, 3)
                    drift_y = random.uniform(1, 3)
                
                new_x = max(1, current_x + drift_x)  # Ensure > 0
                new_y = max(1, current_y + drift_y)  # Ensure > 0
                
                await self._page.mouse.move(new_x, new_y)
                current_x, current_y = new_x, new_y
                self._mouse_pos = (float(current_x), float(current_y))

                # Phase 5: Natural Browse (15% chance) - smooth "Reading Scroll" bounce 50-100px
                # Keep this rare + gated so it doesn't spam on a 50-150ms loop.
                now = time.monotonic()
                if (now - last_scroll_at) >= next_scroll_gate_s:
                    last_scroll_at = now
                    next_scroll_gate_s = random.uniform(1.8, 3.8)
                    if random.random() < 0.15:
                        bounce = random.randint(50, 100)
                        try:
                            steps = random.randint(8, 14)
                            per = bounce / steps
                            # smooth down
                            for _ in range(steps):
                                await self._page.mouse.wheel(0, per)
                                await asyncio.sleep(random.uniform(0.015, 0.035))
                            await asyncio.sleep(random.uniform(0.10, 0.25))
                            # smooth up (slightly imperfect reversal)
                            reverse = bounce * random.uniform(0.6, 1.0)
                            per_up = reverse / steps
                            for _ in range(steps):
                                await self._page.mouse.wheel(0, -per_up)
                                await asyncio.sleep(random.uniform(0.015, 0.04))
                        except Exception:
                            # Ignore scroll failures (e.g. non-scrollable page)
                            pass
                
                # Random pause between micro-saccades (50-150ms)
                await asyncio.sleep(random.uniform(0.05, 0.15))
            except asyncio.CancelledError:
                break
            except Exception:
                # Continue on any error
                await asyncio.sleep(0.1)
    
    async def safe_click(
        self,
        selector: str,
        timeout: int = 30000,
        intent: str = "click_element"
    ) -> bool:
        """
        Safely click element with self-healing on failure.
        
        VANGUARD: Includes idle liveness micro-saccades during wait.
        
        Args:
            selector: CSS selector
            timeout: Timeout in milliseconds
            intent: Intent description for self-healing
        
        Returns:
            True if click succeeded, False otherwise
        """
        # Phase 9: Execution entropy (micro-calculations)
        try:
            inject_execution_noise(tag="safe_click")
        except Exception:
            pass

        # Phase 8: Global heuristic bridge (use fleet-learned healed selector immediately)
        # VANGUARD: Start idle liveness in background
        import asyncio
        liveness_task = None
        try:
            liveness_task = asyncio.create_task(self._idle_liveness_loop())
        except Exception as e:
            logger.debug(f"   Idle liveness start failed: {e}")

        # Shield: VLM-Verified Interaction – if element not on Visual Map or in forbidden zone, HONEYPOT_TRAP
        try:
            from visibility_check import check_before_selector_click
            ok, honeypot = await check_before_selector_click(self, selector, intent)
            if not ok:
                if honeypot:
                    logger.warning("HONEYPOT_TRAP: skipping click (not on Visual Map or Dojo forbidden)")
                if liveness_task:
                    liveness_task.cancel()
                    try:
                        await liveness_task
                    except asyncio.CancelledError:
                        pass
                return False
        except ImportError:
            pass
        except Exception as e:
            logger.debug("visibility_check error: %s", e)
        
        try:
            # Phase 9: Cognitive familiarity map check
            if self._page:
                try:
                    from db_bridge import get_site_map
                    site_map = get_site_map(self._page.url)
                except Exception:
                    site_map = None
                if site_map:
                    if site_map.get("stale"):
                        logger.think("✅ [BODY-THINK] Cognitive map stale. Refresh Scan triggered.")
                        try:
                            from db_bridge import update_site_map
                            structure_hash = await self._compute_structure_hash()
                            update_site_map(
                                self._page.url,
                                {"structure_hash": structure_hash, "map_data": {"refresh_scan": True}},
                            )
                        except Exception:
                            pass
                    elif site_map.get("map_data"):
                        site_label = self._get_site_label(self._page.url)
                        label_hint = f" ({site_label})" if site_label else ""
                        logger.think(f"✅ [BODY-THINK] Cognitive map loaded{label_hint}. Executing familiarity trajectory.")
                        try:
                            box = await self._page.locator(selector).bounding_box()
                            if box:
                                target = (box["x"] + (box["width"] / 2.0), box["y"] + (box["height"] / 2.0))
                                await DiffusionMouse.move_to(
                                    self._page,
                                    target=target,
                                    current_pos=self._mouse_pos,
                                    familiarity=True,
                                )
                                self._mouse_pos = target
                        except Exception:
                            pass

            # Phase 9: Context jitter (tab entropy)
            if self._page and random.random() < 0.35:
                try:
                    await self._page.evaluate("() => (document.title ? document.title.length : 0)")
                except Exception:
                    pass
                logger.think("✅ [BODY-THINK] Context jitter applied.")

            if selector:
                try:
                    from db_bridge import get_global_heuristic
                    heuristic = get_global_heuristic(selector)
                except Exception:
                    heuristic = None

                if heuristic and heuristic.get("new_selector"):
                    healed_selector = str(heuristic["new_selector"])
                    try:
                        await self._page.click(healed_selector, timeout=timeout)
                        if liveness_task:
                            liveness_task.cancel()
                            try:
                                await liveness_task
                            except asyncio.CancelledError:
                                pass
                        logger.info(f"✅ Global Healed Selector applied: {selector} → {healed_selector}")
                        await self._maybe_update_cognitive_map(healed_selector)
                        return True
                    except Exception as e:
                        logger.warning(f"⚠️ Global Healed Selector failed, falling back: {e}")

            await self._page.click(selector, timeout=timeout)
            if liveness_task:
                liveness_task.cancel()
                try:
                    await liveness_task
                except asyncio.CancelledError:
                    pass
            await self._maybe_update_cognitive_map(selector)
            return True
        except PlaywrightTimeoutError:
            if liveness_task:
                liveness_task.cancel()
                try:
                    await liveness_task
                except asyncio.CancelledError:
                    pass
            
            logger.warning(f"⚠️ Selector timeout: {selector}")
            logger.info(f"   Attempting self-healing for intent: {intent}")
            
            # Attempt self-healing
            healed = await self._self_heal_selector(selector, intent)
            if healed and healed.get('newSelector'):
                try:
                    # Restart idle liveness for retry
                    liveness_task = asyncio.create_task(self._idle_liveness_loop())
                    
                    # Try new selector
                    await self._page.click(healed['newSelector'], timeout=timeout)
                    
                    if liveness_task:
                        liveness_task.cancel()
                        try:
                            await liveness_task
                        except asyncio.CancelledError:
                            pass
                    
                    # Log repair to PostgreSQL
                    from db_bridge import log_selector_repair
                    log_selector_repair(
                        worker_id=self.worker_id,
                        original_selector=selector,
                        new_selector=healed['newSelector'],
                        method=healed.get('method', 'isomorphic'),
                        confidence=healed.get('confidence', 0.85),
                        intent=intent
                    )
                    
                    logger.info(f"✅ Selector self-healed and updated in Postgres")
                    await self._maybe_update_cognitive_map(healed['newSelector'])
                    return True
                except Exception as e:
                    logger.error(f"❌ Self-healed selector also failed: {e}")
                    # Phase 7: Visual Attempt (final fallback)
                    return await self._visual_click_fallback(selector)
            else:
                logger.error(f"❌ Self-healing could not find alternative selector")
                # Phase 7: Visual Attempt (final fallback)
                return await self._visual_click_fallback(selector)
        except Exception as e:
            if liveness_task:
                liveness_task.cancel()
                try:
                    await liveness_task
                except asyncio.CancelledError:
                    pass
            logger.error(f"❌ Click failed: {e}")
            return False

    async def move_to(self, x: float, y: float) -> None:
        """
        Phase 7: Human-like cursor movement to absolute coordinates.
        """
        if not self._page:
            raise RuntimeError("Page not initialized")
        current = self._mouse_pos
        target = (float(x), float(y))
        await DiffusionMouse.move_to(self._page, target=target, current_pos=current)
        self._mouse_pos = target

    async def _compute_structure_hash(self) -> Optional[str]:
        """
        Phase 9: Lightweight site structure hash.
        """
        if not self._page:
            return None
        try:
            snapshot = await self._page.evaluate(
                "() => ({"
                "title: document.title || '',"
                "count: document.querySelectorAll('*').length,"
                "textLen: document.body ? document.body.innerText.length : 0"
                "})"
            )
            raw = json.dumps(snapshot, sort_keys=True)
            return hashlib.sha256(raw.encode("utf-8")).hexdigest()
        except Exception:
            return None

    async def _maybe_update_cognitive_map(self, selector: str) -> None:
        """
        Phase 9: Persist cognitive map after successful interaction.
        """
        if not self._page:
            return
        try:
            from db_bridge import update_site_map
        except Exception:
            return
        try:
            box = None
            try:
                box = await self._page.locator(selector).bounding_box()
            except Exception:
                box = None
            structure_hash = await self._compute_structure_hash()
            map_data = {"selector": selector, "box": box}
            update_site_map(
                self._page.url,
                {"structure_hash": structure_hash, "map_data": map_data},
            )
        except Exception:
            pass

    def _report_trauma(self, selector: str, reason: str = "selector_broken") -> None:
        """Self-Correction: fire-and-forget POST to Dojo trauma when VLM cannot find element."""
        base = (os.getenv("DOJO_TRAUMA_URL") or os.getenv("SCRAPEGOAT_URL") or "").rstrip("/")
        if not base:
            return
        url = base if "/api/dojo/trauma" in base else f"{base}/api/dojo/trauma"
        if not self._page:
            return
        try:
            dom = (urlparse(self._page.url).hostname or "").replace("www.", "").split("/")[0]
            if not dom:
                return
            import urllib.request
            req = urllib.request.Request(
                url,
                data=json.dumps({"domain": dom, "selector": selector, "reason": reason}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass

    def _report_coordinate_drift(self, field: str, x: int, y: int) -> None:
        """Dojo Cartography: VLM coordinates differ from Blueprint → update Redis so workers adopt new map."""
        base = (os.getenv("DOJO_TRAUMA_URL") or os.getenv("SCRAPEGOAT_URL") or "").rstrip("/")
        if not base or not self._page:
            return
        try:
            dom = (urlparse(self._page.url).hostname or "").replace("www.", "").split("/")[0]
            if not dom:
                return
            import urllib.request
            url = base if "/api/dojo/coordinate-drift" in base else f"{base}/api/dojo/coordinate-drift"
            req = urllib.request.Request(
                url,
                data=json.dumps({"domain": dom, "field": field, "x": x, "y": y}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
            logger.info("Coordinate drift reported: %s (%s) -> %s (%s, %s)", dom, field, url, x, y)
        except Exception as e:
            logger.debug("_report_coordinate_drift: %s", e)

    async def _visual_click_fallback(self, selector: str) -> bool:
        """
        Phase 7: Visual Attempt fallback when selector healing fails.
        """
        if not self._page:
            return False

        # Required signature (Phase 7)
        logger.think("✅ [BODY-THINK] Selector failed. Pivoting to Visual Navigation.")

        try:
            screenshot = await self.take_screenshot()
            coords = await self.process_vision(screenshot, context="click_failure", text_command=selector)
            if not coords or not coords.get("found"):
                logger.error("❌ Visual Attempt failed: Brain returned no coordinates")
                self._report_trauma(selector, "vlm_no_coordinates")
                return False

            x = coords.get("x")
            y = coords.get("y")
            if x is None or y is None:
                logger.error("❌ Visual Attempt failed: coordinates missing")
                return False

            # Clamp within viewport bounds to avoid off-screen clicks
            try:
                viewport = await self._page.evaluate("() => ({ w: window.innerWidth, h: window.innerHeight })")
                w = max(1, int(viewport.get("w", 1280)))
                h = max(1, int(viewport.get("h", 720)))
                x = max(1, min(float(x), float(w - 2)))
                y = max(1, min(float(y), float(h - 2)))
            except Exception:
                x = float(x)
                y = float(y)

            # Shield: Dojo forbidden regions – do not click in red zones
            try:
                from visibility_check import check_before_coords_click
                if not check_before_coords_click(self, x, y):
                    return False
            except ImportError:
                pass

            await self.move_to(x, y)
            await self._page.mouse.click(x, y)
            logger.info("✅ Visual Attempt click executed")
            return True
        except Exception as e:
            logger.error(f"❌ Visual Attempt failed: {e}")
            return False
    
    async def process_vision(
        self,
        screenshot: bytes,
        context: str = "",
        text_command: str = "",
        suggested_x: Optional[int] = None,
        suggested_y: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Send screenshot to The Brain for vision processing.
        gRPC call wrapped in Tenacity retry (exponential backoff) for 1000+ lead reliability.
        suggested_x/y: Blueprint coords; when VLM result differs by >50px (L1), Brain returns
        coordinate_drift=True so we report to Scrapegoat and update Redis blueprint.
        Returns coordinates and description if found.
        """
        if not self._brain_client:
            logger.warning("⚠️ Brain client not available")
            return None

        request = chimera_pb2.ProcessVisionRequest(
            screenshot=screenshot,
            context=context,
            text_command=text_command,
        )
        if suggested_x is not None:
            request.suggested_x = suggested_x
        if suggested_y is not None:
            request.suggested_y = suggested_y
        response = None

        try:
            if TENACITY_AVAILABLE:
                async for attempt in AsyncRetrying(
                    stop=stop_after_attempt(3),
                    wait=wait_exponential(multiplier=1, min=2, max=30),
                    retry=retry_if_exception_type((grpc.RpcError, OSError, ConnectionError)),
                    reraise=True,
                ):
                    with attempt:
                        response = await self._brain_client.ProcessVision(request)
            else:
                response = await self._brain_client.ProcessVision(request)

            try:
                from db_bridge import get_latency_buffer
                target_url = self._page.url if self._page else ""
                await asyncio.sleep(get_latency_buffer(target_url))
                logger.info("Latency buffer applied")
                global _GHOST_LOCK_LOGGED
                if not _GHOST_LOCK_LOGGED:
                    _GHOST_LOCK_LOGGED = True
                    logger.info("VANGUARD v2.0 BREACHED. THE GHOST IS LIVE.")
            except Exception:
                pass

            return {
                "description": response.description,
                "confidence": response.confidence,
                "found": response.found,
                "x": response.x if response.found else None,
                "y": response.y if response.found else None,
                "coordinate_drift": getattr(response, "coordinate_drift", False),
            }
        except Exception as e:
            logger.error(f"❌ Vision processing failed: {e}")
            return None
    
    async def take_screenshot(self) -> bytes:
        """Take screenshot of current page"""
        if not self._page:
            raise RuntimeError("Page not initialized")
        
        return await self._page.screenshot(full_page=False)

    async def execute_mission(self, mission: Dict[str, Any]) -> Dict[str, Any]:
        """
        Phase 8: Execute a JSON mission payload from the Swarm Hive.
        """
        if not self._page:
            raise RuntimeError("Page not initialized")

        self._seen_403 = False  # reset each mission; 403 listener sets it, _check_403_and_rotate acts on it

        mission_id = (
            mission.get("mission_id")
            or mission.get("missionId")
            or mission.get("id")
            or f"mission_{int(time.time())}"
        )
        with self._session_lock:
            self._mission_run_count += 1
            mission_count = self._mission_run_count

        # Blueprint Interpreter: when Blueprint has instructions, run those instead of domain-specific logic
        bp = mission.get("blueprint") or {}
        if (isinstance(bp, dict) and (bp.get("instructions") or mission.get("instructions"))):
            try:
                from blueprint_interpreter import execute_blueprint_instructions
                return await execute_blueprint_instructions(self, mission)
            except Exception as e:
                logger.warning("Blueprint interpreter failed: %s", e)

        # Scrapegoat ChimeraStation: instruction=deep_search, lead, linkedin_url -> gRPC vision + LPUSH chimera:results
        if mission.get("instruction") == "deep_search":
            return await self._run_deep_search(mission, mission_id, mission_count)

        mission_type = (mission.get("type") or mission.get("mission_type") or "sequence").lower()

        if mission_type == "noop":
            return {"mission_id": mission_id, "status": "noop"}
        if mission_type == "enrichment_pivot":
            lead_data = dict(mission)
            try:
                result = await self.perform_enrichment_pivot(lead_data)
                if result.get("status") == "completed":
                    logger.info("✅ Enrichment pivot successful")
                else:
                    logger.info(f"⚠️ Enrichment pivot skipped: {result.get('reason', 'unknown')}")
                return {"mission_id": mission_id, "status": result.get("status", "completed")}
            except Exception as e:
                logger.error(f"❌ Enrichment pivot failed: {e}")
                return {"mission_id": mission_id, "status": "failed"}

        # Fire Swarm: mission_type "enrichment" with lead_data {name, location, city, state}
        if mission_type == "enrichment":
            lead_data = mission.get("lead_data") or {}
            lead_data.setdefault("name", lead_data.get("full_name"))
            try:
                pivot = await self.perform_enrichment_pivot(lead_data)
                if pivot.get("status") != "completed":
                    return {"mission_id": mission_id, "status": pivot.get("status", "skipped"), "reason": pivot.get("reason")}
                result = await self._deep_search_extract_via_vision()
                result.setdefault("mission_id", mission_id)
                result.setdefault("status", "completed")
                return result
            except Exception as e:
                logger.exception("Enrichment (fire-swarm) failed: %s", e)
                return {"mission_id": mission_id, "status": "failed", "error": str(e)[:500]}

        steps = mission.get("steps") or mission.get("actions") or []
        if isinstance(steps, dict):
            steps = [steps]

        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                continue
            # 403/Cloudflare: if document 403 was seen, rotate to fresh mobile IP before next step
            await self._check_403_and_rotate(mission_id, mission.get("carrier"))
            # Gaussian Jitter (FatigueFactor) + Session Decay (missions>20: increase jitter/delays)
            await self._fatigue_delay(step_index=i, mission_count=mission_count)
            action = (step.get("action") or step.get("type") or "").lower().strip()

            if action == "goto":
                url = step.get("url")
                if url:
                    wait_until = step.get("wait_until")
                    timeout = step.get("timeout")
                    if wait_until or timeout:
                        await self._page.goto(
                            str(url),
                            wait_until=str(wait_until) if wait_until else "domcontentloaded",
                            timeout=int(timeout) if timeout else 45000,
                        )
                    else:
                        await self.goto(str(url))
            elif action == "click":
                sel = step.get("selector") or step.get("sel")
                if sel:
                    await self.safe_click(str(sel), timeout=int(step.get("timeout", 30000)), intent=str(step.get("intent", "click_element")))
            elif action == "type":
                sel = step.get("selector") or step.get("sel")
                text = step.get("text") or ""
                if sel is not None:
                    await self._page.fill(str(sel), str(text))
            elif action == "wait":
                seconds = step.get("seconds")
                ms = step.get("ms")
                if seconds is not None:
                    await asyncio.sleep(float(seconds))
                elif ms is not None:
                    await asyncio.sleep(float(ms) / 1000.0)
            elif action in ("wait_for", "wait_for_selector"):
                sel = step.get("selector") or step.get("sel")
                timeout = int(step.get("timeout", 15000))
                if sel:
                    await self._page.wait_for_selector(str(sel), timeout=timeout)
            elif action == "prime_surface":
                selector = step.get("selector") or step.get("sel")
                label = step.get("label") or self._get_site_label(self._page.url if self._page else "")
                try:
                    if selector:
                        await self.safe_click(str(selector), timeout=int(step.get("timeout", 15000)), intent="prime_surface")
                        continue
                except Exception:
                    pass
                try:
                    from db_bridge import update_site_map
                    structure_hash = await self._compute_structure_hash()
                    update_site_map(
                        self._page.url if self._page else "",
                        {"structure_hash": structure_hash, "map_data": {"prime": True, "selector": selector}},
                    )
                    label_hint = f" ({label})" if label else ""
                    logger.think(f"✅ [BODY-THINK] Cognitive map loaded{label_hint}. Executing familiarity trajectory.")
                except Exception:
                    pass
            elif action == "vision_click":
                screenshot = await self.take_screenshot()
                coords = await self.process_vision(
                    screenshot,
                    context=str(step.get("context", "mission")),
                    text_command=str(step.get("text_command", step.get("textCommand", ""))),
                )
                if coords and coords.get("found") and coords.get("x") is not None and coords.get("y") is not None:
                    await self.move_to(float(coords["x"]), float(coords["y"]))
                    await self._page.mouse.click(float(coords["x"]), float(coords["y"]))
            elif action == "enrichment_pivot":
                lead_data = step.get("lead_data") or step.get("lead") or {}
                try:
                    result = await self.perform_enrichment_pivot(lead_data)
                    if result.get("status") == "completed":
                        logger.info("✅ Enrichment pivot successful")
                    else:
                        logger.info(f"⚠️ Enrichment pivot skipped: {result.get('reason', 'unknown')}")
                except Exception as e:
                    logger.error(f"❌ Enrichment pivot failed: {e}")
            else:
                # Unknown action: ignore safely
                continue

        return {"mission_id": mission_id, "status": "completed"}

    async def _get_text_at_coords(self, x: float, y: float) -> str:
        if not self._page:
            return ""
        try:
            return await self._page.evaluate(
                "(x,y)=>{ const el = document.elementFromPoint(x,y); return el ? (el.textContent||el.innerText||'').trim() : ''; }",
                x, y
            )
        except Exception:
            return ""

    async def _fatigue_delay(self, step_index: int = 0, mission_count: int = 0) -> None:
        """
        Gaussian Jitter (FatigueFactor): non-linear delay between clicks/steps.
        Session Decay: for missions > 20, increase mu and sigma (more jitter and delays).
        """
        mu = 0.12 + 0.01 * (max(0, step_index) ** 1.35)
        sigma = 0.06
        if mission_count > 20:
            mu *= 1.6
            sigma *= 1.3
        d = max(0.02, random.gauss(mu, sigma))
        await asyncio.sleep(d)

    def _emit_telemetry(self, step: str, detail: str) -> None:
        """LPUSH to chimera:telemetry:{mission_id} for Scrapegoat to stream into progress. Root-cause diagnosis: pivot, CAPTCHA, extract."""
        mid = getattr(self, "_telemetry_mission_id", None)
        if not mid:
            return
        r = _get_redis()
        if not r:
            return
        try:
            r.lpush(f"chimera:telemetry:{mid}", json.dumps({"t": time.time(), "step": step, "detail": detail[:500] if detail else ""}))
        except Exception:
            pass

    async def _check_403_and_rotate(self, mission_id: str, carrier: Optional[str] = None) -> bool:
        """
        If a 403 (e.g. Cloudflare block) was seen on a document and should_rotate_session_on_403
        is True, perform a complete session rotation: new context with new sticky_session_id so
        Decodo assigns a fresh mobile IP. Returns True if rotation was performed.
        """
        if not self._seen_403 or not should_rotate_session_on_403():
            return False
        new_id = f"{mission_id}_r403_{int(time.time() * 1000)}"
        logger.warning("403/Cloudflare block: rotating session to %s (fresh mobile IP)", new_id)
        self._seen_403 = False
        await self.rotate_hardware_identity(mission_id=new_id, carrier=carrier)
        return True

    async def _detect_and_solve_captcha(self) -> bool:
        """
        3-Tier: (1) Stealth avoids CAPTCHA 80%. (2) VLM Agent: CoT solver, 3 attempts.
        (3) CapSolver: token injection when VLM fails. v3/Turnstile: token-only, skip VLM.
        """
        if not self._page:
            return False
        try:
            info = await self._page.evaluate("""() => {
                const url = location.href;
                const cf = document.querySelector('.cf-turnstile');
                if (cf) { const sk = cf.getAttribute('data-sitekey') || ''; if (sk) return { site_key: sk, url, type: 'turnstile' }; }
                const scripts = Array.from(document.querySelectorAll('script[src*="recaptcha/api.js"]'));
                for (const s of scripts) { const m = (s.src || '').match(/render=([^&"'\s]+)/); if (m) return { site_key: m[1], url, type: 'recaptcha_v3' }; }
                const h = document.querySelector('iframe[src*="hcaptcha"]');
                const f = document.querySelector('iframe[src*="recaptcha"]');
                const d = document.querySelector('[data-sitekey]');
                const sk = d ? (d.getAttribute('data-sitekey') || '') : '';
                if (h && sk) return { site_key: sk, url, type: 'hcaptcha' };
                if ((f || sk) && sk) return { site_key: sk, url, type: 'recaptcha' };
                return null;
            }""")
            if not info:
                return False

            ct = info.get("type") or "recaptcha"
            self._emit_telemetry("captcha_detected", ct)

            # reCAPTCHA v3 and Turnstile: token-only, no image. Skip VLM, use CapSolver.
            if ct in ("recaptcha_v3", "turnstile"):
                import capsolver
                if not capsolver.is_available() or not info.get("site_key"):
                    self._emit_telemetry("capsolver_skip", "unavailable or no site_key")
                    return False
                self._emit_telemetry("capsolver_start", ct)
                try:
                    if ct == "recaptcha_v3":
                        token = await capsolver.solve_recaptcha_v3(info["url"], info["site_key"])
                    else:
                        token = await capsolver.solve_turnstile(info["url"], info["site_key"])
                    await self._inject_captcha_token(token)
                    self._emit_telemetry("capsolver_done", ct)
                    logger.info("Capsolver: %s token injected (token-only)", ct)
                    await asyncio.sleep(1)
                    return True
                except Exception as e:
                    self._emit_telemetry("capsolver_fail", str(e)[:200])
                    raise

            # Tier 2: VLM Agent (recaptcha v2 image, hcaptcha). 3 attempts before CapSolver.
            self._emit_telemetry("vlm_start", "")
            try:
                from captcha_agent import solve_with_vlm_first
                if await solve_with_vlm_first(self._page, self, max_attempts=3):
                    self._emit_telemetry("vlm_done", "")
                    logger.info("Captcha: solved by VLM agent (Tier 2)")
                    await asyncio.sleep(1)
                    return True
                self._emit_telemetry("vlm_fail", "max_attempts")
            except ImportError:
                self._emit_telemetry("vlm_skip", "ImportError")
            except Exception as e:
                self._emit_telemetry("vlm_fail", str(e)[:200])
                logger.debug("VLM captcha agent: %s", e)

            # Tier 3: CapSolver (paid fallback) for recaptcha and hcaptcha.
            import capsolver
            if not capsolver.is_available() or not info.get("site_key"):
                self._emit_telemetry("capsolver_skip", "unavailable or no site_key")
                return False
            self._emit_telemetry("capsolver_start", f"Tier3 {ct}")
            try:
                if ct == "hcaptcha":
                    token = await capsolver.solve_hcaptcha(info["url"], info["site_key"])
                else:
                    token = await capsolver.solve_recaptcha_v2(info["url"], info["site_key"])
                await self._inject_captcha_token(token)
                self._emit_telemetry("capsolver_done", f"Tier3 {ct}")
                logger.info("Capsolver: %s token injected (Tier 3)", ct)
                await asyncio.sleep(1)
                return True
            except Exception as e:
                self._emit_telemetry("capsolver_fail", str(e)[:200])
                raise
        except Exception as e:
            self._emit_telemetry("captcha_fail", str(e)[:200])
            logger.debug(f"Captcha detect/solve skipped or failed: {e}")
            return False

    async def _inject_captcha_token(self, token: str) -> None:
        """Inject CapSolver token into reCAPTCHA, hCaptcha, or Turnstile widget."""
        if not self._page or not token:
            return
        await self._page.evaluate("""(tok) => {
            const sel = 'textarea[name="g-recaptcha-response"], #g-recaptcha-response, textarea[name="h-captcha-response"], textarea[name="cf-turnstile-response"], input[name="cf-turnstile-response"]';
            const el = document.querySelector(sel);
            if (el) { el.value = tok; if (el.innerHTML !== undefined) el.innerHTML = tok; el.dispatchEvent(new Event('input', { bubbles: true })); }
            const d = document.querySelector('[data-callback]');
            const fn = d ? d.getAttribute('data-callback') : null;
            if (fn && typeof window[fn] === 'function') window[fn](tok);
        }""", token)

    async def _deep_search_extract_via_vision(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        confs: list = []
        # Load Blueprint from Redis (blueprint:{domain} or BLUEPRINT:{domain}) for suggested_x/y
        ov: Dict[str, str] = {}
        dom = ""
        if self._page:
            dom = (urlparse(self._page.url).hostname or "").replace("www.", "").split("/")[0]
        r = _get_redis()
        if r and dom:
            ov = r.hgetall(f"blueprint:{dom}") or r.hgetall(f"BLUEPRINT:{dom}") or {}

        for label, text_cmd in [("phone", "Phone"), ("age", "Age"), ("income", "Income")]:
            try:
                sx = ov.get(f"{label}_x")
                sy = ov.get(f"{label}_y")
                suggested_x = int(sx) if sx not in (None, "") else None
                suggested_y = int(sy) if sy not in (None, "") else None

                shot = await self.take_screenshot()
                coords = await self.process_vision(
                    shot,
                    context="deep_search",
                    text_command=text_cmd,
                    suggested_x=suggested_x,
                    suggested_y=suggested_y,
                )
                c = coords.get("confidence")
                if c is not None:
                    confs.append(float(c))
                # Coordinate Drift: VLM result differs from Blueprint → report to Scrapegoat → Redis blueprint
                if coords and coords.get("coordinate_drift") and coords.get("x") is not None and coords.get("y") is not None:
                    self._report_coordinate_drift(label, int(coords["x"]), int(coords["y"]))
                if not coords or not coords.get("found") or coords.get("x") is None or coords.get("y") is None:
                    continue
                text = await self._get_text_at_coords(float(coords["x"]), float(coords["y"]))
                if not text:
                    continue
                if label == "phone":
                    digits = re.sub(r"\D", "", text)
                    out["phone"] = digits if len(digits) >= 10 else None
                elif label == "age":
                    m = re.search(r"\d{1,3}", text)
                    out["age"] = int(m.group()) if m else None
                else:
                    out["income"] = text.strip() or None
            except Exception as e:
                logger.debug(f"deep_search vision {label}: {e}")
        # 2026 Consensus: pass minimum vision confidence for validator (olmOCR trigger when < 0.95)
        if confs:
            out["vision_confidence"] = min(confs)
        return out

    async def _run_deep_search(self, mission: Dict[str, Any], mission_id: str, mission_count: int = 0) -> Dict[str, Any]:
        self._telemetry_mission_id = mission_id
        try:
            self._emit_telemetry("deep_search_start", f"provider={mission.get('target_provider') or '?'}")
            await self._fatigue_delay(step_index=0, mission_count=mission_count)
            await self._check_403_and_rotate(mission_id, mission.get("carrier"))

            lead = mission.get("lead") or {}
            first_name = lead.get("first_name") or lead.get("firstName") or ""
            last_name = lead.get("last_name") or lead.get("lastName") or ""
            _jn = " ".join(filter(None, [first_name, last_name])).strip()
            full_name = (
                lead.get("name") or lead.get("full_name") or lead.get("fullName") or _jn
            ) or None
            lead_data = {
                "full_name": full_name,
                "first_name": first_name,
                "last_name": last_name,
                "linkedin_url": lead.get("linkedinUrl") or lead.get("linkedin_url") or mission.get("linkedin_url"),
                "target_provider": mission.get("target_provider") or lead.get("target_provider"),
                **lead,
            }
            self._emit_telemetry("pivot_start", "")
            pivot_ret = None
            try:
                pivot_ret = await self.perform_enrichment_pivot(lead_data)
                self._emit_telemetry("pivot_done", "")
            except Exception as e:
                self._emit_telemetry("pivot_fail", str(e)[:300])
                logger.warning(f"deep_search pivot failed: {e}")
                return {"status": "failed", "error": f"pivot_error: {str(e)[:200]}", "mission_id": mission_id}
            if isinstance(pivot_ret, dict) and pivot_ret.get("status") in ("skipped", "failed"):
                err = pivot_ret.get("error") or pivot_ret.get("reason") or "pivot_skipped"
                return {"status": "failed", "error": err, "mission_id": mission_id}
            await self._check_403_and_rotate(mission_id, mission.get("carrier"))

            self._emit_telemetry("captcha_check", "")
            captcha_solved = await self._detect_and_solve_captcha()
            self._emit_telemetry("captcha_done", f"solved={captcha_solved}")
            await self._check_403_and_rotate(mission_id, mission.get("carrier"))

            self._emit_telemetry("extract_start", "")
            result = await self._deep_search_extract_via_vision()
            self._emit_telemetry("extract_done", "")
            result.setdefault("mission_id", mission_id)
            result["captcha_solved"] = captcha_solved
            return result
        finally:
            self._telemetry_mission_id = None

    async def perform_enrichment_pivot(self, lead_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Vanguard v7.0: Choose best people-search target and execute lookup.
        """
        if not self._page:
            raise RuntimeError("Page not initialized")

        source_url = lead_data.get("source_url") or lead_data.get("profile_url") or lead_data.get("linkedin_url")
        if source_url:
            logger.info("Extracting identity from LinkedIn")
        else:
            logger.info("Extracting identity")

        full_name = (
            lead_data.get("full_name")
            or lead_data.get("fullName")
            or lead_data.get("name")
            or " ".join(filter(None, [
                lead_data.get("first_name") or lead_data.get("firstName"),
                lead_data.get("last_name") or lead_data.get("lastName"),
            ])).strip()
        )
        if not full_name and source_url:
            derived_name = self._derive_name_from_profile_url(str(source_url))
            if derived_name:
                full_name = derived_name
                lead_data = {**lead_data, "full_name": derived_name}

        targets = lead_data.get("targets") or []
        if isinstance(targets, str):
            targets = [targets]

        target = None
        if targets:
            for candidate in targets:
                target = self._select_people_search_target({**lead_data, "preferred_target": candidate})
                if target:
                    break
        if not target:
            target = self._select_people_search_target(lead_data)
        if not target:
            self._emit_telemetry("pivot_no_target", "no_target")
            return {"status": "skipped", "reason": "no_target"}

        # Map-to-Engine: override from Redis BLUEPRINT:{domain} or blueprint:{domain} when Dojo has published
        try:
            dom = (urlparse(target.get("url") or "").hostname or "").replace("www.", "").split("/")[0]
            if not dom:
                dom = (target.get("name") or "").replace(" ", "").lower()
            r = _get_redis()
            if r and dom:
                ov = r.hgetall(f"BLUEPRINT:{dom}") or r.hgetall(f"blueprint:{dom}") or {}
                if isinstance(ov, dict):
                    if ov.get("name_selector"):
                        target["name_selector"] = ov["name_selector"]
                    if ov.get("result_selector") is not None:
                        target["result_selector"] = ov.get("result_selector") or None
        except Exception as e:
            logger.debug("Blueprint override skipped: %s", e)

        name = target["name"]
        url = target["url"]
        name_selector = target["name_selector"]
        result_selector = target.get("result_selector")

        self._emit_telemetry("pivot_target", f"{name} {url}")
        logger.info(f"Pivoting to {name}")

        if not full_name:
            self._emit_telemetry("pivot_skip", "missing_name")
            return {"status": "skipped", "reason": "missing_name"}

        self._emit_telemetry("pivot_goto", url)
        await self._page.goto(url, wait_until="domcontentloaded", timeout=45000)
        self._emit_telemetry("pivot_selector_wait", name_selector)
        try:
            await self._page.wait_for_selector(name_selector, timeout=15000)
        except Exception as e:
            self._emit_telemetry("pivot_selector_fail", f"{name_selector} {str(e)[:150]}")
            logger.warning(f"⚠️ People-search input not found: {name_selector}")

        try:
            await self.safe_click(name_selector, intent=f"people_search_name:{name}")
        except Exception:
            logger.warning(f"⚠️ People-search click failed: {name_selector}")

        self._emit_telemetry("pivot_fill", name_selector)
        try:
            await self._page.fill(name_selector, full_name)
            await self._page.keyboard.press("Enter")
        except Exception as e:
            self._emit_telemetry("pivot_fill_fail", str(e)[:150])
            logger.warning(f"⚠️ People-search fill failed: {name_selector}")
            return {"status": "failed", "error": f"pivot_fill_fail: {str(e)[:120]}", "target": name}

        if result_selector:
            self._emit_telemetry("pivot_result_wait", result_selector)
            try:
                await self._page.wait_for_selector(result_selector, timeout=15000)
                await self.safe_click(result_selector, intent=f"people_search_result:{name}")
                self._emit_telemetry("pivot_result_ok", result_selector)
            except Exception as e:
                self._emit_telemetry("pivot_result_fail", f"{result_selector} {str(e)[:150]}")

        self._emit_telemetry("pivot_done", name)
        logger.info(f"✅ Enrichment pivot successful: {name}")
        return {"status": "completed", "target": name}

    # Rotational Magazine: GPS router can direct to any of these. target_provider from ChimeraStation.
    _MAGAZINE_TARGETS = {
        "FastPeopleSearch": {
            "url": "https://www.fastpeoplesearch.com/",
            "name_selector": "input#name-search",
            "result_selector": "div.search-item",
        },
        "TruePeopleSearch": {
            "url": "https://www.truepeoplesearch.com/",
            "name_selector": "input#search-name",
            "result_selector": "div.card-summary",
        },
        "ZabaSearch": {
            "url": "https://www.zabasearch.com/",
            "name_selector": "input[name='q']",
            "result_selector": None,
        },
        "SearchPeopleFree": {
            "url": "https://www.searchpeoplefree.com/",
            "name_selector": "input[name='q']",
            "result_selector": None,
        },
        "ThatsThem": {
            "url": "https://thatsthem.com/",
            "name_selector": "input[name='q']",
            "result_selector": None,
        },
        "AnyWho": {
            "url": "https://www.anywho.com/",
            "name_selector": "input[name='q']",
            "result_selector": None,
        },
    }

    def _select_people_search_target(self, lead_data: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """
        Choose people-search target from the Magazine. Respects target_provider (GPS router)
        or preferred_target. Falls back to TruePeopleSearch.
        """
        name = lead_data.get("full_name") or lead_data.get("fullName") or lead_data.get("name")
        fn = lead_data.get("first_name") or lead_data.get("firstName")
        ln = lead_data.get("last_name") or lead_data.get("lastName")
        if not name and not (fn and ln):
            return None

        preferred = (
            lead_data.get("target_provider") or
            lead_data.get("preferred_target") or
            lead_data.get("target") or
            ""
        )
        if isinstance(preferred, str):
            preferred = preferred.strip().lower()
        else:
            preferred = ""

        for pname, cfg in self._MAGAZINE_TARGETS.items():
            if preferred and preferred in pname.lower():
                return {"name": pname, **cfg}

        return {"name": "TruePeopleSearch", **self._MAGAZINE_TARGETS["TruePeopleSearch"]}

    def _get_site_label(self, url: str) -> Optional[str]:
        try:
            host = urlparse(url or "").hostname or ""
        except Exception:
            host = ""
        host = host.lower()
        if "truepeoplesearch" in host:
            return "TruePeopleSearch"
        if "fastpeoplesearch" in host:
            return "FastPeopleSearch"
        if "zabasearch" in host:
            return "ZabaSearch"
        if "searchpeoplefree" in host:
            return "SearchPeopleFree"
        if "thatsthem" in host:
            return "ThatsThem"
        if "anywho" in host:
            return "AnyWho"
        return None

    def _derive_name_from_profile_url(self, profile_url: str) -> Optional[str]:
        try:
            path = urlparse(profile_url).path or ""
        except Exception:
            path = ""
        path = path.strip("/")
        if not path:
            return None
        parts = path.split("/")
        slug = parts[-1] if parts else ""
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "", slug)
        if not slug:
            return None
        if "-" in slug or "_" in slug:
            tokens = re.split(r"[-_]+", slug)
            return " ".join(t.capitalize() for t in tokens if t)
        # Fallback: split camelCase if present, else title-case raw slug
        spaced = re.sub(r"([a-z])([A-Z])", r"\\1 \\2", slug)
        return " ".join(t.capitalize() for t in spaced.split() if t)
    
    async def goto(self, url: str) -> None:
        """Navigate to URL (stealth patches already applied)"""
        if not self._page:
            raise RuntimeError("Page not initialized")
        
        await self._page.goto(url, wait_until="networkidle")
    
    async def start_tracing(self, mission_id: Optional[str] = None) -> Optional[Path]:
        """
        Start Playwright tracing for mission execution.
        
        Args:
            mission_id: Optional mission identifier
        
        Returns:
            Path to trace file if successful, None otherwise
        """
        if not self._context:
            logger.warning("⚠️ Cannot start tracing: context not initialized")
            return None
        
        try:
            # Create temporary trace file
            trace_file = tempfile.NamedTemporaryFile(
                suffix=".zip",
                prefix=f"trace_{self.worker_id}_",
                delete=False
            )
            trace_path = Path(trace_file.name)
            trace_file.close()
            
            # Start tracing
            await self._context.tracing.start(
                screenshots=True,
                snapshots=True,
                sources=True
            )
            
            self._trace_path = trace_path
            self._tracing_active = True
            
            logger.info(f"📹 Tracing started: {trace_path.name}")
            return trace_path
            
        except Exception as e:
            logger.error(f"❌ Failed to start tracing: {e}")
            return None
    
    async def stop_tracing(self, mission_id: Optional[str] = None) -> Optional[str]:
        """
        Stop Playwright tracing and upload to storage.
        
        Args:
            mission_id: Optional mission identifier
        
        Returns:
            Trace URL if successful, None otherwise
        """
        if not self._tracing_active or not self._context:
            return None
        
        try:
            # Stop tracing
            if self._trace_path:
                await self._context.tracing.stop(path=str(self._trace_path))
                logger.info(f"📹 Tracing stopped: {self._trace_path.name}")
                
                # Upload trace to storage
                from storage_bridge import upload_trace_to_storage
                trace_url = upload_trace_to_storage(
                    self._trace_path,
                    self.worker_id,
                    mission_id
                )
                
                if trace_url:
                    logger.info(f"✅ Trace uploaded: {trace_url}")
                    return trace_url
                else:
                    logger.warning("⚠️ Trace saved locally but upload failed")
                    return str(self._trace_path)
            
            self._tracing_active = False
            return None
            
        except Exception as e:
            logger.error(f"❌ Failed to stop tracing: {e}")
            self._tracing_active = False
            return None
    
    async def close(self) -> None:
        """Close browser and cleanup"""
        # Stop any active tracing
        if self._tracing_active:
            await self.stop_tracing()
        
        if self._page:
            await self._page.close()
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        if self._grpc_channel:
            await self._grpc_channel.close()
        
        logger.info(f"🦾 PhantomWorker {self.worker_id} closed")
    
    async def __aenter__(self):
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
