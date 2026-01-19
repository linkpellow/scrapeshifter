"""
Scraper-Based Enrichment Module
Replaces skip-tracing APIs with direct scraping using Dojo blueprints

Targets: phone, age, income from people search sites
Sites: That's Them, FastPeopleSearch, etc.

Supports both:
- JSON API responses (extracted via JSON paths)
- HTML responses (extracted via CSS selectors)
"""
import json
import os
import re
import asyncio
from typing import Dict, Any, Optional, List
from pathlib import Path
from urllib.parse import quote_plus

from loguru import logger

from app.scraping.base import BaseScraper, BROWSER_MODE_AVAILABLE

# HTML parsing (for people search sites that return HTML)
try:
    from bs4 import BeautifulSoup
    HTML_PARSING_AVAILABLE = True
except ImportError:
    HTML_PARSING_AVAILABLE = False
    logger.warning("BeautifulSoup not available - HTML parsing disabled")


def slugify(text: str, lowercase: bool = True) -> str:
    """Convert text to URL-friendly slug (john-doe format)"""
    if not text:
        return ""
    slug = text.strip()
    slug = re.sub(r'[^\w\s-]', '', slug)  # Remove special chars
    slug = re.sub(r'[\s_]+', '-', slug)   # Replace spaces/underscores with hyphens
    slug = re.sub(r'-+', '-', slug)       # Collapse multiple hyphens
    slug = slug.strip('-')
    return slug.lower() if lowercase else slug


def titleize_slug(text: str) -> str:
    """Convert text to Title-Case slug (Link-Pellow format)"""
    if not text:
        return ""
    slug = text.strip()
    slug = re.sub(r'[^\w\s-]', '', slug)  # Remove special chars
    slug = re.sub(r'[\s_]+', '-', slug)   # Replace spaces/underscores with hyphens
    slug = re.sub(r'-+', '-', slug)       # Collapse multiple hyphens
    slug = slug.strip('-')
    # Title case each part: link-pellow -> Link-Pellow
    return '-'.join(word.capitalize() for word in slug.split('-'))

# Blueprint storage locations (check multiple paths)
# Priority: Railway /data volume > local ./data > bundled in repo
def get_blueprint_dir() -> Path:
    """Get blueprint directory, checking multiple locations"""
    # Railway persistent volume: if /data exists, use /data/dojo-blueprints (create if needed)
    if Path("/data").exists():
        d = Path("/data/dojo-blueprints")
        d.mkdir(parents=True, exist_ok=True)
        return d

    # Local data directory (development)
    local_data = Path("./data/dojo-blueprints")
    if local_data.exists():
        return local_data
    
    # Bundled in scrapegoat repo (fallback - committed blueprints)
    bundled = Path(__file__).parent.parent.parent / "data" / "dojo-blueprints"
    if bundled.exists():
        return bundled
    
    # Create local if nothing exists
    local_data.mkdir(parents=True, exist_ok=True)
    return local_data

BLUEPRINT_DIR = get_blueprint_dir()
logger.info("Blueprint directory: {}", BLUEPRINT_DIR)

# Priority order for sites (best to worst)
SITE_PRIORITY = [
    "fastpeoplesearch.com",
    "thatsthem.com",
    "truepeoplesearch.com",
    "whitepages.com",
]

# Direct people-search URL templates: /name/{name_slug}_{city_slug}-{state_lower} etc.
# Used by auto_map and ScraperEnrichment. Keys must match SITE_PRIORITY domain.
URL_TEMPLATES = {
    "fastpeoplesearch.com": "https://www.fastpeoplesearch.com/name/{name_slug}_{city_slug}-{state_lower}",
    "thatsthem.com": "https://thatsthem.com/name/{name_title}/{city_title}-{state_lower}",
    # truepeoplesearch, whitepages: no single direct-detail template; Chimera uses homepage+search.
}

class BlueprintExtractor(BaseScraper):
    """
    Generic extractor using Dojo blueprints
    Supports both JSON API responses and HTML page scraping
    
    Blueprint format:
    {
        "targetUrl": "https://example.com/search?name={name}&city={city}",
        "method": "GET",
        "responseType": "html" | "json",  # default: "json"
        "extraction": {
            "phone": "$.data.phone" (for JSON) OR "div.phone-number::text" (for CSS),
            "age": "$.data.age" OR "span.age::text",
            ...
        }
    }
    """
    def __init__(self, blueprint: Dict[str, Any], **kwargs):
        super().__init__(**kwargs)
        self.blueprint = blueprint
        self.target_url = blueprint.get('targetUrl', '')
        self.method = blueprint.get('method', 'GET')
        self.headers = blueprint.get('headers', {})
        self.body = blueprint.get('body')
        self.extraction_paths = blueprint.get('extraction', {})
        self.response_type = blueprint.get('responseType', 'json')  # 'json' or 'html'
    
    async def extract(self, **params) -> Dict[str, Any]:
        """
        Extract data using blueprint patterns
        
        Args:
            **params: Search parameters (name, city, state, etc.)
            
        Returns:
            Dictionary with extracted fields (phone, age, income, etc.)
        """
        # Build request URL with params
        url = self._build_url(params)
        
        # Make request
        if self.method == 'POST':
            response_data = await self.post(url, json=self._build_body(params), headers=self.headers)
        else:
            response_data = await self.get(url, params=self._build_params(params), headers=self.headers)
        
        # Extract based on response type
        if self.response_type == 'html':
            return self._extract_from_html(response_data)
        else:
            return self._extract_from_json(response_data)

    def apply_to_html(self, html: str) -> Dict[str, Any]:
        """Apply extraction selectors to an HTML string without making an HTTP request."""
        return self._extract_from_html({"text": html})
    
    def _extract_from_json(self, data: Any) -> Dict[str, Any]:
        """Extract fields from JSON response using JSON paths"""
        extracted = {}
        for field_name, json_path in self.extraction_paths.items():
            if json_path.startswith('$.'):
                value = self._extract_by_json_path(data, json_path)
                if value:
                    extracted[field_name] = value
        return extracted
    
    def _extract_from_html(self, data: Any) -> Dict[str, Any]:
        """Extract fields from HTML response using CSS selectors"""
        if not HTML_PARSING_AVAILABLE:
            logger.error("BeautifulSoup not available for HTML parsing")
            return {}
        
        # Get HTML text from response
        html_text = data.get('text', '') if isinstance(data, dict) else str(data)
        if not html_text:
            return {}
        
        # Check for CAPTCHA in HTML (can return 200 but still be blocked)
        captcha_indicators = [
            'captcha', 'challenge', 'cf-browser-verification', 
            'hcaptcha', 'recaptcha', 'please verify', 'robot',
            'access denied', 'blocked', 'unusual traffic'
        ]
        html_lower = html_text.lower()
        if any(indicator in html_lower for indicator in captcha_indicators):
            if len(html_text) < 50000:
                logger.warning("CAPTCHA/block detected in HTML response")
                return {'_captcha_detected': True}
        soup = BeautifulSoup(html_text, 'lxml')
        extracted = {}
        
        for field_name, selector in self.extraction_paths.items():
            if selector.startswith('$.'):
                continue  # Skip JSON paths
            
            value = self._extract_by_css(soup, selector)
            if value:
                extracted[field_name] = value
        
        return extracted
    
    def _extract_by_css(self, soup: BeautifulSoup, selector: str) -> Optional[str]:
        """
        Extract value using CSS selector
        
        Supports:
        - "div.class::text" -> get text content
        - "div.class::attr(href)" -> get attribute
        - "div.class" -> get text content (default)
        """
        try:
            # Parse pseudo-elements
            attr_match = re.match(r'^(.+?)::attr\((\w+)\)$', selector)
            text_match = re.match(r'^(.+?)::text$', selector)
            
            if attr_match:
                css_selector = attr_match.group(1)
                attr_name = attr_match.group(2)
                element = soup.select_one(css_selector)
                return element.get(attr_name) if element else None
            
            if text_match:
                css_selector = text_match.group(1)
            else:
                css_selector = selector
            
            element = soup.select_one(css_selector)
            if element:
                return element.get_text(strip=True)
            
            return None
        except Exception as e:
            logger.error("CSS extraction error: {}", e)
            return None
    
    def _build_url(self, params: Dict[str, Any]) -> str:
        """Build request URL, replacing placeholders with URL-encoded params"""
        url = self.target_url
        for key, value in params.items():
            # URL encode the value
            encoded_value = quote_plus(str(value))
            url = url.replace(f"{{{key}}}", encoded_value)
        return url
    
    def _build_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Build GET query parameters"""
        blueprint_params = self.blueprint.get('dynamicParams', [])
        return {k: v for k, v in params.items() if k in blueprint_params}
    
    def _build_body(self, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Build POST request body"""
        if not self.body:
            return params
        
        body = json.loads(json.dumps(self.body))  # Deep copy
        self._merge_params_into_body(body, params)
        return body
    
    def _merge_params_into_body(self, body: Any, params: Dict[str, Any]) -> None:
        """Recursively merge params into body template"""
        if isinstance(body, dict):
            for key, value in body.items():
                if isinstance(value, str) and value.startswith('{') and value.endswith('}'):
                    param_key = value[1:-1]
                    if param_key in params:
                        body[key] = params[param_key]
                else:
                    self._merge_params_into_body(value, params)
        elif isinstance(body, list):
            for item in body:
                self._merge_params_into_body(item, params)
    
    def _extract_by_json_path(self, data: Any, json_path: str) -> Optional[str]:
        """
        Extract value using JSON path (e.g., "$.data.person.phones[0].number")
        """
        if not json_path or not json_path.startswith('$.'):
            return None
        
        try:
            path_parts = json_path[2:].split('.')
            current = data
            
            for part in path_parts:
                if '[' in part:
                    key, index_str = part.split('[')
                    index = int(index_str.rstrip(']'))
                    if isinstance(current, dict) and key in current:
                        array = current[key]
                        if isinstance(array, list) and 0 <= index < len(array):
                            current = array[index]
                        else:
                            return None
                    else:
                        return None
                else:
                    if isinstance(current, dict) and part in current:
                        current = current[part]
                    else:
                        return None
            
            return str(current) if current is not None else None
        except Exception:
            return None


def load_blueprint(site_domain: str) -> Optional[Dict[str, Any]]:
    """Load blueprint for a site"""
    blueprint_file = BLUEPRINT_DIR / f"{site_domain}.json"
    
    if not blueprint_file.exists():
        return None
    
    try:
        with open(blueprint_file, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error("Failed to load blueprint for {}: {}", site_domain, e)
        return None


def save_blueprint(site_domain: str, blueprint: Dict[str, Any]) -> bool:
    """Save blueprint for a site"""
    blueprint_file = BLUEPRINT_DIR / f"{site_domain}.json"
    
    try:
        with open(blueprint_file, 'w') as f:
            json.dump(blueprint, f, indent=2)
        return True
    except Exception as e:
        logger.error("Failed to save blueprint for {}: {}", site_domain, e)
        return False


def find_available_site(identity: Dict[str, Any]) -> Optional[str]:
    """
    Find first available site with blueprint
    
    Returns:
        Site domain if found, None otherwise
    """
    for site in SITE_PRIORITY:
        blueprint = load_blueprint(site)
        if blueprint:
            return site
    return None


async def scrape_enrich(identity: Dict[str, Any]) -> Dict[str, Any]:
    """
    Scrape enrichment data using Dojo blueprints
    
    FULL UTILIZATION OF BASESCRAPER:
    - ✅ Stealth mode (curl_cffi, Chrome TLS fingerprint)
    - ✅ Proxy rotation (Decodo residential proxies)
    - ✅ Rate limit awareness (reads X-RateLimit headers)
    - ✅ Circuit breaking (per-site health tracking)
    - ✅ Flight recorder (logs failed requests)
    - ✅ Parallel site attempts (try multiple sites at once)
    - ✅ Response validation (structure checks)
    
    Priority: phone > age > income
    
    Args:
        identity: Resolved identity (firstName, lastName, city, state, zipcode)
        
    Returns:
        Dictionary with phone, age, income (if found)
    """
    # Find all available sites
    available_sites = [s for s in SITE_PRIORITY if load_blueprint(s)]
    
    if not available_sites:
        logger.warning("No blueprint available for any enrichment site")
        return {}
    
    # Build search parameters with ALL URL format variations
    full_name = f"{identity.get('firstName', '')} {identity.get('lastName', '')}".strip()
    city = identity.get('city', '')
    state = identity.get('state', '')
    
    params = {
        # Raw values
        'name': full_name,
        'city': city,
        'state': state.upper() if state else '',
        'state_lower': state.lower() if state else '',
        'zipcode': identity.get('zipcode', ''),
        
        # Lowercase slugs (for FastPeopleSearch: link-pellow_wesley-chapel-fl)
        'name_slug': slugify(full_name, lowercase=True),
        'city_slug': slugify(city, lowercase=True),
        
        # Title-case slugs (for ThatsThem: Link-Pellow/Wesley-Chapel-FL)
        'name_title': titleize_slug(full_name),
        'city_title': titleize_slug(city),
    }
    
    logger.info("Searching for: {} in {}, {}", full_name, city, state)
    logger.debug("URL params: name_slug={}, city_slug={}", params['name_slug'], params['city_slug'])
    
    # Try sites in parallel (up to 3 at once for speed)
    # If first succeeds, cancel others
    import asyncio
    
    async def try_site(site: str, use_browser: bool = False) -> Optional[Dict[str, Any]]:
        """Try a single site with full BaseScraper capabilities"""
        blueprint = load_blueprint(site)
        if not blueprint:
            return None
        
        # Check if blueprint requires browser mode
        requires_browser = blueprint.get('requiresBrowser', False) or use_browser
        
        extractor = None
        try:
            mode_str = "BROWSER" if requires_browser else "STEALTH HTTP"
            logger.info("Attempting: {} ({} + proxy)", site, mode_str)
            
            # FULL BaseScraper power: stealth + proxy + rate limiting + circuit breaking
            # Browser mode for sites with heavy JS protection
            extractor = BlueprintExtractor(
                blueprint,
                stealth=True,  # curl_cffi with Chrome fingerprint
                proxy=None,    # Auto-detect from DECODO_API_KEY (BaseScraper handles it)
                rate_limit_delay=1.0,  # Base delay
                randomize_delay=True,  # Jitter for human-like behavior
                max_retries=3,  # Retry failed requests
                circuit_failure_threshold=5,  # Open circuit after 5 failures
                timeout=30,
                browser_mode=requires_browser and BROWSER_MODE_AVAILABLE,  # Use Playwright if needed
            )
            
            # Execute with full BaseScraper capabilities
            result = await extractor.run(**params)
            
            # Validate response structure
            if not isinstance(result, dict):
                logger.warning("{}: Invalid response structure", site)
                return None
            
            # Check for CAPTCHA detected during extraction
            if result.get('_captcha_detected'):
                logger.warning("{}: CAPTCHA detected in response", site)
                if not use_browser and BROWSER_MODE_AVAILABLE:
                    logger.info("{}: Retrying with Browser Mode + CAPTCHA solving...", site)
                    return await try_site(site, use_browser=True)
                else:
                    logger.error("{}: Cannot bypass CAPTCHA (browser mode unavailable or already tried)", site)
                    return None
            
            # Extract and normalize
            normalized = {}
            
            # Phone (CRITICAL)
            phone = result.get('phone') or result.get('phoneNumber') or result.get('phone_number')
            if phone:
                phone_normalized = normalize_phone(phone)
                if phone_normalized:
                    normalized['phone'] = phone_normalized
            
            # Age
            age = result.get('age')
            if age:
                try:
                    age_int = int(age)
                    if 18 <= age_int <= 120:  # Validate age range
                        normalized['age'] = age_int
                except (ValueError, TypeError):
                    pass
            
            # Income
            income = result.get('income') or result.get('householdIncome') or result.get('household_income')
            if income:
                income_normalized = normalize_income(income)
                if income_normalized:
                    normalized['income'] = income_normalized
            
            # Email (bonus)
            email = result.get('email') or result.get('emailAddress') or result.get('email_address')
            if email and '@' in str(email):
                normalized['email'] = str(email).strip()
            
            if normalized:
                logger.info("{}: Extracted {}", site, list(normalized.keys()))
                stats = extractor.get_stats()
                logger.debug("Stats: {}/{} requests, {} retries", stats['successful_requests'], stats['total_requests'], stats['retried_requests'])
                return normalized
            else:
                logger.warning("{}: No extractable data found", site)
                return None
            
        except Exception as e:
            error_msg = str(e)
            logger.error("{}: {}", site, error_msg[:100])
            if not use_browser and BROWSER_MODE_AVAILABLE:
                if any(x in error_msg.lower() for x in ['403', '503', 'cloudflare', 'captcha', 'blocked', 'access denied']):
                    logger.info("{}: Detected protection, retrying with Browser Mode...", site)
                    return await try_site(site, use_browser=True)
            
            return None
        finally:
            if extractor:
                try:
                    await extractor.__aexit__(None, None, None)
                except Exception:
                    pass
    
    # Try sites in parallel (faster than sequential)
    # Limit to 3 concurrent to avoid overwhelming
    tasks = [try_site(site) for site in available_sites[:3]]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Find first successful result
    for i, result in enumerate(results):
        if isinstance(result, dict) and result.get('phone'):
            successful_site = available_sites[i]
            logger.info("Success with: {}", successful_site)
            return result
    
    # If parallel attempts failed, try remaining sites sequentially
    for site in available_sites[3:]:
        result = await try_site(site)
        if result and result.get('phone'):
            return result
    
    logger.warning("All scraping attempts failed")
    return {}


def normalize_phone(phone: str) -> str:
    """Normalize phone to +1XXXXXXXXXX format"""
    if not phone:
        return ''
    
    # Remove non-digits
    digits = ''.join(filter(str.isdigit, str(phone)))
    
    # Handle 10-digit numbers
    if len(digits) == 10:
        return f"+1{digits}"
    
    # Handle 11-digit (with country code)
    if len(digits) == 11 and digits[0] == '1':
        return f"+{digits}"
    
    # Already has + prefix
    if str(phone).startswith('+'):
        return str(phone)
    
    # Default: add +1 if 10+ digits
    if len(digits) >= 10:
        return f"+1{digits[-10:]}"
    
    return ''


def normalize_income(income: str) -> str:
    """Normalize income format"""
    if not income:
        return ''
    
    income_str = str(income).strip()
    
    # Remove $ and commas
    income_str = income_str.replace('$', '').replace(',', '')
    
    # Handle "50k" format
    if income_str.lower().endswith('k'):
        try:
            value = int(income_str[:-1]) * 1000
            return f"${value:,}"
        except ValueError:
            pass
    
    # Try to parse as number
    try:
        value = int(float(income_str))
        return f"${value:,}"
    except ValueError:
        return income_str


# Synchronous wrapper for async enrichment (for worker integration)
def enrich_with_scraper(identity: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main enrichment function - uses scrapers instead of APIs
    
    This replaces skip_trace() in the enrichment pipeline
    
    Args:
        identity: Resolved identity (firstName, lastName, city, state, zipcode)
        
    Returns:
        Dictionary with phone, age, income (if found)
    """
    try:
        # Run async function in new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(scrape_enrich(identity))
            return result
        finally:
            loop.close()
    except Exception as e:
        logger.error("Error in scraper enrichment: {}", e)
        return {}
