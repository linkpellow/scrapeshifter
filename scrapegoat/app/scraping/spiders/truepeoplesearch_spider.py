"""
Smart TruePeopleSearch Spider - 2026 Cognitive Edition

Uses "2026 Tech" (LLM Parsing + Smart Mutation + Vision Verification) 
to ensure high match rates and resilience to site changes.

Features:
- 🧠 Universal LLM Parser: No fragile CSS selectors
- 🔄 Smart Query Mutation: Handles nicknames and location variations
- 👁️ Vision-Based Verification: Detects soft blocks
- 🍪 Session Manager Integration: Uses Cloudflare cookies from Auth Worker
- 🌐 Browser Mode: Full Playwright automation for Cloudflare-heavy sites

This is the "Full Potential" enrichment tool that saves $0.15 per lead.

Usage:
    spider = TruePeopleSearchSpider()
    result = await spider.run("John", "Doe", "Naples", "FL")
    # Returns: {"phones": ["+1234567890"], "age": 45, "address": "123 Main St"} or None
"""
import os
import asyncio
import tempfile
from typing import Dict, Any, Optional, List
from pathlib import Path

from loguru import logger

# Redis for Cloudflare cookie
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

from app.scraping.base import BaseScraper

# Browser mode for Cloudflare-heavy sites
try:
    from app.scraping.browser_mode import BrowserModeScraper
    BROWSER_MODE_AVAILABLE = True
except ImportError:
    BROWSER_MODE_AVAILABLE = False
    logger.warning("⚠️ Browser mode not available - Cloudflare may block requests")


class TruePeopleSearchSpider(BaseScraper):
    """
    Smart TruePeopleSearch spider with 2026 cognitive capabilities.
    
    Uses LLM parsing instead of fragile selectors, smart query mutations,
    and vision verification to handle obfuscated HTML and soft blocks.
    """
    
    def __init__(self, **kwargs):
        """Initialize spider with cognitive features enabled"""
        super().__init__(stealth=True, **kwargs)
        
        # Browser mode for Cloudflare-heavy sites
        self._browser_scraper: Optional[BrowserModeScraper] = None
        self.use_browser_mode = BROWSER_MODE_AVAILABLE
        
        # Inject Cloudflare cookie from Redis
        self._inject_cloudflare_cookie()
    
    def _inject_cloudflare_cookie(self) -> None:
        """Load Cloudflare clearance cookie from Session Manager (Redis)"""
        if not REDIS_AVAILABLE:
            logger.warning("⚠️ Redis not available - cannot load Cloudflare cookie")
            return
        
        try:
            redis_url = os.getenv("REDIS_URL") or os.getenv("APP_REDIS_URL", "redis://localhost:6379")
            r = redis.from_url(redis_url, decode_responses=True)
            
            cf_cookie = r.get("auth:tps:cookie")
            user_agent = r.get("auth:tps:ua")
            
            if cf_cookie:
                # Set cookie header for HTTP requests
                self._headers["Cookie"] = f"cf_clearance={cf_cookie}"
                
                # Set matching user agent (Cloudflare requires this)
                if user_agent:
                    self._headers["User-Agent"] = user_agent
                
                logger.info("🍪 Injected Cloudflare Cookie from Session Manager")
            else:
                logger.warning("⚠️ No Cloudflare cookie in Redis - request may fail")
                logger.info("   Session Manager should harvest cookie automatically")
                
        except Exception as e:
            logger.warning(f"⚠️ Failed to load Cloudflare cookie: {e}")
    
    async def _get_browser_scraper(self) -> BrowserModeScraper:
        """Get or create browser scraper with Cloudflare cookie"""
        if not self.use_browser_mode:
            raise RuntimeError("Browser mode not available")
        
        if self._browser_scraper is None:
            # Load Cloudflare cookie for browser
            cookies = []
            if REDIS_AVAILABLE:
                try:
                    redis_url = os.getenv("REDIS_URL") or os.getenv("APP_REDIS_URL", "redis://localhost:6379")
                    r = redis.from_url(redis_url, decode_responses=True)
                    cf_cookie = r.get("auth:tps:cookie")
                    
                    if cf_cookie:
                        cookies.append({
                            "name": "cf_clearance",
                            "value": cf_cookie,
                            "domain": ".truepeoplesearch.com",
                            "path": "/",
                        })
                except Exception as e:
                    logger.warning(f"⚠️ Failed to load cookie for browser: {e}")
            
            self._browser_scraper = BrowserModeScraper(
                headless=True,
                stealth=True,
                proxy=self.proxy,
            )
            await self._browser_scraper.start()
            
            # Set cookies in browser
            if cookies:
                await self._browser_scraper.set_cookies(cookies)
                logger.info("🍪 Set Cloudflare cookie in browser")
        
        return self._browser_scraper
    
    async def extract(
        self, 
        first_name: str, 
        last_name: str, 
        city: str, 
        state: str
    ) -> Optional[Dict[str, Any]]:
        """
        Search for phone number by name and location with smart mutations.
        
        Uses 2026 Tech:
        1. Smart Query Mutation - tries variations (John -> Jonathan, etc.)
        2. Browser Mode - handles Cloudflare challenges
        3. LLM Parsing - extracts data from obfuscated HTML
        4. Vision Verification - detects soft blocks
        
        Args:
            first_name: First name
            last_name: Last name
            city: City name
            state: State abbreviation (e.g., "FL")
            
        Returns:
            Dict with phones, age, address if found, None otherwise
        """
        logger.info(f"🔎 [Free] Searching {first_name} {last_name} in {city}, {state}")
        
        # Step 1: Generate query mutations (2026 Tech)
        queries = self.generate_query_mutations(first_name, last_name, city, state)
        
        # Step 2: Try each mutation until we find results
        for attempt, (fname, lname, cty, st) in enumerate(queries, 1):
            if attempt > 1:
                logger.info(f"🔄 Attempt {attempt}: Trying mutation ({fname}, {lname}, {cty or 'no city'}, {st})")
            
            result = await self._search_single(fname, lname, cty, st)
            if result:
                return result
        
        logger.warning(f"❌ No results found for {first_name} {last_name} after {len(queries)} mutations")
        return None
    
    async def _search_single(
        self, 
        first: str, 
        last: str, 
        city: str, 
        state: str
    ) -> Optional[Dict[str, Any]]:
        """
        Perform a single search attempt.
        
        Uses browser mode for Cloudflare-heavy sites and LLM parsing for extraction.
        """
        # Build URL slug (TruePeopleSearch format)
        if city:
            slug = f"{first}-{last}/{state}/{city}".replace(" ", "-").lower()
        else:
            slug = f"{first}-{last}/{state}".replace(" ", "-").lower()
        
        url = f"https://www.truepeoplesearch.com/find/{slug}"
        logger.info(f"🌐 Navigating to: {url}")
        
        try:
            # Use browser mode for Cloudflare-heavy sites
            if self.use_browser_mode:
                return await self._search_with_browser(url, first, last)
            else:
                # Fallback to HTTP request
                return await self._search_with_http(url, first, last)
                
        except Exception as e:
            logger.error(f"❌ Search failed: {e}")
            return None
    
    async def _search_with_browser(
        self, 
        url: str, 
        first_name: str, 
        last_name: str
    ) -> Optional[Dict[str, Any]]:
        """Search using browser mode (handles Cloudflare better)"""
        browser = await self._get_browser_scraper()
        
        try:
            # Navigate with human-like behavior
            await browser.goto(url, wait_until="networkidle")
            await asyncio.sleep(2)  # Wait for content to load
            
            # Get page content
            html = await browser.get_html()

            # --- Capture Screenshot: before verification, temp path + screenshot ---
            ss_path = os.path.join(tempfile.gettempdir(), f"tps_vision_{os.getpid()}.png")
            await browser.screenshot(path=ss_path)

            # --- Vision Verify: use_vision + screenshot_path into verify_page_content ---
            success_kw = ["phone", "address", "age", "relatives", "current address"]
            is_valid = await self.verify_page_content(
                html, success_keywords=success_kw, use_vision=True, screenshot_path=ss_path
            )

            # --- Solver Trigger: if verification fails, detect CAPTCHA and solve (CapSolver/OpenAI) ---
            if not is_valid:
                try:
                    from app.scraping.captcha_solver import detect_captcha_in_html, get_captcha_solver
                    cap = detect_captcha_in_html(html)
                    if cap and (
                        get_captcha_solver().is_available()
                        or (self.use_cognitive_features and os.getenv("OPENAI_API_KEY"))
                    ):
                        if await self._try_solve_captcha_in_browser(browser, url):
                            # --- Re-Verify: sleep, re-fetch HTML and screenshot, verify_page_content again ---
                            await asyncio.sleep(3)
                            html = await browser.get_html()
                            await browser.screenshot(path=ss_path)
                            is_valid = await self.verify_page_content(
                                html, success_keywords=success_kw, use_vision=True, screenshot_path=ss_path
                            )
                except Exception as e:
                    logger.debug("Browser CAPTCHA/vision verify: %s", e)
                if not is_valid:
                    logger.warning("🛡️ Page appears to be blocked or empty")
                    return None
            
            # Step 2: Extract result card HTML
            # Try to find the first result card (TruePeopleSearch structure)
            # We'll use LLM to parse, so we just need a reasonable HTML snippet
            try:
                # Try to get first result card via Playwright
                card_element = await browser.page.query_selector(".card-summary, .result-card, .person-card")
                
                if card_element:
                    card_html = await card_element.inner_html()
                    logger.info("📄 Extracted result card HTML")
                else:
                    # Fallback: Get a chunk of HTML around likely result area
                    # Look for common patterns in the HTML
                    card_html = html
                    # Truncate to first 8000 chars (usually contains first result)
                    card_html = card_html[:8000]
                    logger.info("📄 Using page HTML snippet (no card selector found)")
            except Exception as e:
                logger.warning(f"⚠️ Could not extract card HTML: {e}")
                # Fallback to full HTML (truncated)
                card_html = html[:8000]
            
            # Step 3: 2026 TECH - LLM Parsing (no fragile selectors!)
            data = await self.parse_with_llm(
                card_html,
                "Phone Numbers (list of strings in E.164 format like +1234567890), "
                "Age (integer), "
                "Current Address (string), "
                "Relatives (list of strings with full names)"
            )
            
            if data and data.get("Phone Numbers"):
                phones = data.get("Phone Numbers", [])
                # Ensure phones are in list format
                if isinstance(phones, str):
                    phones = [phones]
                
                logger.success(f"✅ Enriched: {len(phones)} phone(s) found")
                return {
                    "phones": phones,
                    "age": data.get("Age"),
                    "address": data.get("Current Address"),
                    "relatives": data.get("Relatives", []),
                    "source": "TruePeopleSearch"
                }
            else:
                logger.info("ℹ️ No phone numbers extracted by LLM")
                return None
                
        except Exception as e:
            logger.error(f"⚠️ Browser search error: {e}")
            return None
    
    async def _search_with_http(
        self, 
        url: str, 
        first_name: str, 
        last_name: str
    ) -> Optional[Dict[str, Any]]:
        """Fallback: Search using HTTP request (less reliable for Cloudflare)"""
        try:
            response = await self.get(url)
            
            if "text" not in response:
                return None
            
            html = response["text"]
            status = response.get("status", 200)
            
            # Check for Cloudflare challenge
            if "cf-browser-verification" in html.lower() or "checking your browser" in html.lower():
                logger.warning("⚠️ Cloudflare challenge detected - cookie may be expired")
                logger.info("   Session Manager will refresh cookie automatically")
                return None
            
            # Check for rate limiting
            if status == 429 or "too many requests" in html.lower():
                logger.warning("⚠️ Rate limited by TruePeopleSearch")
                return None
            
            # Verify page content
            is_valid = await self.verify_page_content(
                html,
                success_keywords=["phone", "address", "age"]
            )
            
            if not is_valid:
                return None
            
            # Use LLM parsing
            data = await self.parse_with_llm(
                html[:8000],  # Truncate to save tokens
                "Phone Numbers (list), Age (int), Current Address (string)"
            )
            
            if data and data.get("Phone Numbers"):
                phones = data.get("Phone Numbers", [])
                if isinstance(phones, str):
                    phones = [phones]
                
                logger.success(f"✅ Found {len(phones)} phone(s)")
                return {
                    "phones": phones,
                    "age": data.get("Age"),
                    "address": data.get("Current Address"),
                    "source": "TruePeopleSearch"
                }
            
            return None
            
        except Exception as e:
            logger.error(f"❌ HTTP search failed: {e}")
            return None
    
    async def close(self) -> None:
        """Clean up browser scraper"""
        if self._browser_scraper:
            await self._browser_scraper.close()
            self._browser_scraper = None
        await super().close()
    
    async def run(
        self, 
        first_name: str, 
        last_name: str, 
        city: str, 
        state: str
    ) -> Optional[Dict[str, Any]]:
        """
        Run the spider with proper setup/teardown.
        
        Args:
            first_name: First name
            last_name: Last name
            city: City name
            state: State abbreviation
            
        Returns:
            Dict with phones, age, address if found, None otherwise
        """
        return await super().run(
            first_name=first_name,
            last_name=last_name,
            city=city,
            state=state
        )
