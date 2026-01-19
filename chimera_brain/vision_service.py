"""
Vision Service - The Brain of Project Chimera

2026 Hybrid-Tiered Vision Layer (Multimodal Document Intelligence):
- Tier Speed/Body: deepseek-ai/deepseek-vl2-tiny — real-time coordinate grounding, 896px.
- Tier Accuracy/Cortex: allenai/olmOCR-2-7B-1025 — Golden Record Markdown linearization, 1024px.
- Consensus: when DeepSeek confidence < 0.95, run olmOCR-2 to verify.

Legacy: USE_LOCAL_VLM=1, VLM_MODEL=blip2 (Salesforce/blip2-opt-2.7b).

10s Latency Guard: if VLM inference > 10s, sets SYSTEM_STATE:PAUSED and alerts WEBHOOK_URL.
"""

import io
import json
import logging
import os
import re
import time
import urllib.request
from datetime import datetime
from typing import Tuple, Optional, Dict, Any
import torch
from PIL import Image
import numpy as np

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

VLM_LATENCY_GUARD_SEC = 10
PAUSED_KEY = "SYSTEM_STATE:PAUSED"

# 2026 Consensus: below this, trigger olmOCR-2 verification (in-Brain or flagged for Spine)
CONFIDENCE_OLMOCR_THRESHOLD = 0.95

# Dynamic resolution (VRAM vs accuracy)
DEEPSEEK_TARGET_SIZE = 896   # DeepSeek-VL2 sweet spot
OLMOCR_TARGET_SIZE = 1024   # olmOCR-2 sweet spot

# Env: USE_2026_VISION=1 or VLM_TIER=speed|accuracy|hybrid to enable 2026 stack
USE_2026_VISION = os.getenv("USE_2026_VISION", "").lower() in ("1", "true", "yes")
VLM_TIER_2026 = (os.getenv("VLM_TIER", "hybrid") or "hybrid").lower()
if VLM_TIER_2026 not in ("speed", "accuracy", "hybrid"):
    VLM_TIER_2026 = "hybrid"

_redis_client = None


def _get_redis():
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


def _set_paused_and_webhook(reason: str, latency_sec: float) -> None:
    r = _get_redis()
    if r:
        try:
            r.set(PAUSED_KEY, reason)
        except Exception:
            pass
    url = os.getenv("WEBHOOK_URL")
    if url:
        try:
            body = json.dumps({"reason": reason, "latency_sec": latency_sec, "event": "vlm_latency_guard"})
            req = urllib.request.Request(url, data=body.encode(), headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=10)
        except Exception as e:
            logger.warning(f"WEBHOOK_URL alert failed: {e}")

USE_LOCAL_VLM = os.getenv("USE_LOCAL_VLM", "").lower() in ("1", "true", "yes")
VLM_MODEL = os.getenv("VLM_MODEL", "blip2").lower()


def _resize_for_tier(image: Image.Image, tier: str) -> Image.Image:
    """Dynamic Resolution Scaling: 896px for DeepSeek, 1024px for olmOCR."""
    w, h = image.size
    target = DEEPSEEK_TARGET_SIZE if tier == "speed" else OLMOCR_TARGET_SIZE
    if max(w, h) <= target:
        return image
    if w >= h:
        nw, nh = target, max(1, int(h * target / w))
    else:
        nh, nw = target, max(1, int(w * target / h))
    return image.resize((nw, nh), Image.Resampling.LANCZOS)


def _load_deepseek_vl2(device: str) -> Tuple[Any, Any]:
    """Load deepseek-ai/deepseek-vl2-tiny for speed-tier coordinate grounding. Returns (processor, model) or (None, None)."""
    try:
        from vram_manager import set_fraction_for_speed_tier
        set_fraction_for_speed_tier()
    except Exception:
        pass
    try:
        from transformers import AutoProcessor, AutoModelForCausalLM
        name = "deepseek-ai/deepseek-vl2-tiny"
        dtype = torch.bfloat16 if device == "cuda" else torch.float32
        proc = AutoProcessor.from_pretrained(name, trust_remote_code=True)
        model = AutoModelForCausalLM.from_pretrained(name, trust_remote_code=True, torch_dtype=dtype)
        model = model.to(device).eval()
        return proc, model
    except Exception as e:
        logger.warning(f"DeepSeek-VL2 load failed: {e}")
        return None, None


def _load_olmocr(device: str) -> Tuple[Any, Any]:
    """Load allenai/olmOCR-2-7B-1025 for accuracy-tier Markdown linearization. Returns (processor, model) or (None, None)."""
    try:
        from vram_manager import set_fraction_for_accuracy_tier
        set_fraction_for_accuracy_tier()
    except Exception:
        pass
    try:
        from transformers import AutoProcessor, AutoModelForCausalLM
        name = "allenai/olmOCR-2-7B-1025"
        dtype = torch.bfloat16 if device == "cuda" else torch.float32
        proc = AutoProcessor.from_pretrained(name, trust_remote_code=True)
        model = AutoModelForCausalLM.from_pretrained(name, trust_remote_code=True, torch_dtype=dtype)
        model = model.to(device).eval()
        return proc, model
    except Exception as e:
        logger.warning(f"olmOCR-2 load failed: {e}")
        return None, None


def _load_blip2(device: str):
    """Load BLIP-2 for VQA. Returns (processor, model) or (None, None) on failure."""
    try:
        from transformers import Blip2ForConditionalGeneration, Blip2Processor
        name = "Salesforce/blip2-opt-2.7b"
        dtype = torch.float16 if device == "cuda" else torch.float32
        proc = Blip2Processor.from_pretrained(name)
        model = Blip2ForConditionalGeneration.from_pretrained(name, torch_dtype=dtype)
        model = model.to(device)
        return proc, model
    except Exception as e:
        logger.warning(f"BLIP-2 load failed: {e}")
        return None, None


class VisualIntentProcessor:
    """
    Visual grounding: screenshot + "Find the area containing X" -> (x, y).
    2026: DeepSeek-VL2 (speed) + olmOCR-2 (accuracy when conf < 0.95). Legacy: BLIP-2.
    """

    def __init__(self, model_name: Optional[str] = None, device: Optional[str] = None):
        self.model_name = model_name or "microsoft/git-base"
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = None
        self.processor = None
        self._deepseek_proc: Any = None
        self._deepseek_model: Any = None
        self._olmocr_proc: Any = None
        self._olmocr_model: Any = None

        if USE_2026_VISION:
            self._deepseek_proc, self._deepseek_model = _load_deepseek_vl2(self.device)
            if self._deepseek_model is not None:
                logger.info(f"2026 Speed tier: DeepSeek-VL2-tiny on {self.device} (resize {DEEPSEEK_TARGET_SIZE}px)")
            # olmOCR lazy-loaded on first conf < 0.95
            if self._deepseek_model is None:
                logger.info("DeepSeek-VL2 failed; falling back to BLIP-2 or heuristic")
        need_blip = (USE_LOCAL_VLM or VLM_MODEL in ("blip2", "blip2-opt") or
                     (USE_2026_VISION and self._deepseek_model is None))
        if need_blip:
            self.processor, self.model = _load_blip2(self.device)
            if self.model is not None:
                logger.info(f"Local VLM loaded: blip2 on {self.device}")
            else:
                logger.info("Local VLM load failed; using heuristic fallback")
        elif not USE_2026_VISION and VLM_MODEL in ("llava", "moondream"):
            logger.info(f"VLM_MODEL={VLM_MODEL} not implemented yet; using heuristic fallback")
        elif not USE_2026_VISION:
            logger.info("USE_LOCAL_VLM not set; using heuristic fallback. Set USE_LOCAL_VLM=1 or USE_2026_VISION=1.")
    
    def get_click_coordinates(
        self,
        image_bytes: bytes,
        text_command: str,
        suggested_x: Optional[int] = None,
        suggested_y: Optional[int] = None,
    ) -> Tuple[int, int, float, bool]:
        """
        Get click coordinates for a visual intent. COORDINATE_DRIFT: when suggested_x/y
        are provided and VLM result differs by >50px (L1), returns coordinate_drift=True
        so Dojo can auto-update the map.
        Returns: (x, y, confidence, coordinate_drift).
        """
        def _drift(x: int, y: int) -> bool:
            if suggested_x is None or suggested_y is None:
                return False
            return (abs(x - suggested_x) + abs(y - suggested_y)) > 50

        # Normalize Phone/Age/Income for VLM extraction (Sovereign Lead Engine)
        t = (text_command or "").strip().lower()
        if t in ("phone", "mobile", "mobile phone", "phone number", "primary phone"):
            text_command = "the primary mobile phone number"
        elif t in ("age", "dob", "date of birth", "birth date"):
            text_command = "the age or date of birth"
        elif t in ("income", "salary", "household income", "median income"):
            text_command = "the income or salary"

        try:
            if not image_bytes or len(image_bytes) < 8:
                logger.warning(f"Invalid image bytes: empty or too small ({len(image_bytes) if image_bytes else 0} bytes)")
                return (0, 0, 0.0, False)

            is_png = image_bytes[:4] == b'\x89PNG'
            is_jpeg = image_bytes[:3] == b'\xff\xd8\xff'
            if not (is_png or is_jpeg):
                logger.warning(f"Image bytes don't have valid PNG/JPEG header. First 8 bytes: {image_bytes[:8].hex()}")

            image_stream = io.BytesIO(image_bytes)
            image = Image.open(image_stream)
            image = image.convert("RGB")

            # ---- 2026 path: DeepSeek-VL2 (speed) + optional olmOCR-2 (consensus when conf < 0.95) ----
            if USE_2026_VISION and self._deepseek_model is not None and self._deepseek_proc is not None:
                im = _resize_for_tier(image, "speed")
                prompt = f"Find the area of the screen containing: {text_command}. Reply with the center as two integers: x y. Answer:"
                coords, conf = self._infer_deepseek(im, prompt)
                # Consensus: if conf < 0.95, run olmOCR-2 for Markdown linearization and verify intent.
                # (olmOCR-2 produces Markdown; we use it only to verify. Coordinates stay from DeepSeek.)
                # Only when VLM_TIER_2026 == "hybrid"; "speed" skips olmOCR. Scrapegoat still sets
                # NEEDS_OLMOCR_VERIFICATION when conf < 0.95 (indicates low confidence; olmOCR did not run here).
                if VLM_TIER_2026 == "hybrid" and conf is not None and conf < CONFIDENCE_OLMOCR_THRESHOLD:
                    md = self._linearize_to_markdown(_resize_for_tier(image, "accuracy"))
                    if md and self._olmocr_finds_intent(md, text_command):
                        conf = 0.96
                        logger.info("Consensus: olmOCR-2 verified intent, confidence set to 0.96")
                if coords is not None:
                    # Scale coords from resized (im) back to original image
                    iw, ih = image.size
                    mw, mh = im.size
                    if mw and mh:
                        x = int(coords[0] * iw / mw) if mw else coords[0]
                        y = int(coords[1] * ih / mh) if mh else coords[1]
                        x, y = max(0, min(x, iw - 1)), max(0, min(y, ih - 1))
                    else:
                        x, y = coords[0], coords[1]
                    return (x, y, conf if conf is not None else 0.9, _drift(x, y))
                r = self._fallback_coordinate_detection(image, text_command)
                return (r[0], r[1], r[2], False)

            # ---- Legacy: BLIP-2 or heuristic ----
            if self.model is None or self.processor is None:
                r = self._fallback_coordinate_detection(image, text_command)
                return (r[0], r[1], r[2], False)

            prompt = (
                f"Question: Find the area of the screen containing: {text_command}. "
                "Reply with the approximate center as two integers: x y. Answer:"
            )
            coords = None
            t0 = time.perf_counter()
            try:
                inputs = self.processor(images=image, text=prompt, return_tensors="pt")
                inputs = {k: v.to(self.device) for k, v in inputs.items()}
                with torch.no_grad():
                    out = self.model.generate(**inputs, max_new_tokens=50, do_sample=False)
                answer = self.processor.decode(out[0], skip_special_tokens=True).strip()
                coords = self._parse_coords_from_vlm_answer(answer, image.size)
            except Exception as e:
                logger.warning(f"VLM inference failed: {e}")
            elapsed = time.perf_counter() - t0
            if elapsed > VLM_LATENCY_GUARD_SEC:
                _set_paused_and_webhook("vlm_latency_guard", elapsed)
                logger.warning(f"VLM Latency Guard: inference took {elapsed:.1f}s > {VLM_LATENCY_GUARD_SEC}s; SYSTEM_STATE:PAUSED set")
            if coords is not None:
                return (coords[0], coords[1], coords[2], _drift(coords[0], coords[1]))
            r = self._fallback_coordinate_detection(image, text_command)
            return (r[0], r[1], r[2], False)

        except Exception as e:
            logger.error(f"Error processing vision request: {e}")
            return (0, 0, 0.0, False)
    
    def _infer_deepseek(self, image: Image.Image, prompt: str) -> Tuple[Optional[Tuple[int, int]], Optional[float]]:
        """Run DeepSeek-VL2; return ((x,y), confidence) or (None, None)."""
        try:
            proc, model = self._deepseek_proc, self._deepseek_model
            if proc is None or model is None:
                return None, None
            t0 = time.perf_counter()
            # Try common VLM input shapes (processor varies by model)
            try:
                inputs = proc(images=[image], text=prompt, return_tensors="pt")
            except Exception:
                try:
                    inputs = proc(images=image, text=prompt, return_tensors="pt")
                except Exception:
                    inputs = proc([{"role": "user", "content": f"<image>\n{prompt}"}], images=[image], return_tensors="pt")
            if hasattr(inputs, "to") and callable(getattr(inputs, "to", None)):
                inputs = inputs.to(self.device)
            elif hasattr(inputs, "items"):
                inputs = {k: (v.to(self.device) if hasattr(v, "to") and callable(getattr(v, "to", None)) else v) for k, v in inputs.items()}
            with torch.no_grad():
                out = model.generate(**inputs, max_new_tokens=64, do_sample=False)
            raw = proc.decode(out[0], skip_special_tokens=True) if hasattr(proc, "decode") else str(out[0].tolist())
            c = self._parse_coords_from_vlm_answer(raw, image.size)
            elapsed = time.perf_counter() - t0
            if elapsed > VLM_LATENCY_GUARD_SEC:
                _set_paused_and_webhook("vlm_latency_guard", elapsed)
            if c is not None:
                return (c[0], c[1]), c[2]
            return None, None
        except Exception as e:
            logger.debug("DeepSeek infer: %s", e)
            return None, None

    def _linearize_to_markdown(self, image: Image.Image) -> Optional[str]:
        """olmOCR-2: linearize image to Markdown. Lazy-loads model. Returns None on failure."""
        if self._olmocr_model is None and self._olmocr_proc is None:
            self._olmocr_proc, self._olmocr_model = _load_olmocr(self.device)
        if self._olmocr_model is None or self._olmocr_proc is None:
            return None
        try:
            prompt = "Convert this document or UI screenshot to Markdown. Preserve structure and all text. Output:"
            inputs = self._olmocr_proc(images=[image], text=prompt, return_tensors="pt")
            inputs = {k: v.to(self.device) if hasattr(v, "to") else v for k, v in inputs.items()}
            with torch.no_grad():
                out = self._olmocr_model.generate(**inputs, max_new_tokens=512, do_sample=False)
            raw = self._olmocr_proc.decode(out[0], skip_special_tokens=True) if hasattr(self._olmocr_proc, "decode") else str(out[0].tolist())
            return raw or None
        except Exception as e:
            logger.debug("olmOCR linearize: %s", e)
            return None

    def _olmocr_finds_intent(self, markdown: str, text_command: str) -> bool:
        """True if the Markdown likely contains the requested intent (phone/age/income)."""
        t = (text_command or "").strip().lower()
        md = (markdown or "").lower()
        if "phone" in t or "mobile" in t:
            return bool(re.search(r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}", md)) or "phone" in md or "mobile" in md
        if "age" in t or "dob" in t or "birth" in t:
            return bool(re.search(r"\b(age|dob|birth|years?)\s*:?\s*\d{1,3}\b", md)) or "age" in md
        if "income" in t or "salary" in t:
            return "$" in md or "income" in md or "salary" in md or "k" in md
        return "phone" in md or "age" in md or "income" in md

    def _parse_coords_from_vlm_answer(self, answer: str, image_size: Tuple[int, int]) -> Optional[Tuple[int, int, float]]:
        """Parse 'x y' or 'CENTER' from VLM answer. Returns (x, y, confidence) or None."""
        w, h = image_size
        # Two integers: "100 200" or "100, 200" or "(100, 200)"
        m = re.search(r"(\d+)\s*[,]\s*(\d+)|(\d+)\s+(\d+)|\(\s*(\d+)\s*,\s*(\d+)\s*\)", answer)
        if m:
            g = m.groups()
            x = int(g[0] or g[2] or g[4])
            y = int(g[1] or g[3] or g[5])
            x = max(0, min(x, w))
            y = max(0, min(y, h))
            return (x, y, 0.85)
        # Region fallback
        a = answer.upper()
        if "CENTER" in a:
            return (w // 2, h // 2, 0.7)
        if "TOP_LEFT" in a or "TOP LEFT" in a:
            return (w // 4, h // 4, 0.6)
        if "TOP_RIGHT" in a or "TOP RIGHT" in a:
            return (3 * w // 4, h // 4, 0.6)
        if "BOTTOM_LEFT" in a or "BOTTOM LEFT" in a:
            return (w // 4, 3 * h // 4, 0.6)
        if "BOTTOM_RIGHT" in a or "BOTTOM RIGHT" in a:
            return (3 * w // 4, 3 * h // 4, 0.6)
        return None

    def _fallback_coordinate_detection(
        self, 
        image: Image.Image, 
        text_command: str
    ) -> Tuple[int, int, float]:
        """
        Fallback coordinate detection using simple heuristics.
        
        This is a placeholder - in production, you'd always use a proper VLM.
        """
        width, height = image.size
        
        # Simple keyword-based heuristics
        text_lower = text_command.lower()
        
        # Look for common UI elements based on keywords
        if "button" in text_lower or "click" in text_lower:
            # Try to find button-like regions (simplified)
            # In reality, you'd use edge detection, color analysis, etc.
            if "green" in text_lower or "submit" in text_lower:
                # Typically submit buttons are in the bottom-right area
                x = int(width * 0.85)
                y = int(height * 0.90)
            elif "login" in text_lower or "sign in" in text_lower:
                # Login buttons often in top-right
                x = int(width * 0.85)
                y = int(height * 0.15)
            else:
                # Default: center of screen
                x = width // 2
                y = height // 2
        elif "input" in text_lower or "field" in text_lower or "type" in text_lower:
            # Input fields often in center-top area
            x = width // 2
            y = int(height * 0.35)
        else:
            # Default: center
            x = width // 2
            y = height // 2
        
        # Low confidence for fallback
        confidence = 0.5
        
        logger.info(f"Fallback detection: ({x}, {y}) for '{text_command}'")
        return (x, y, confidence)
    
    def find_new_selector(
        self,
        screenshot: bytes,
        intent_description: str,
        domain: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Find a new CSS/XPath selector for a UI element using VLM.
        
        This is the "Trauma Center" method - when a selector fails,
        this method uses the VLM to autonomously re-map the selector.
        
        Args:
            screenshot: PNG image bytes
            intent_description: Natural language description (e.g., "the search input field")
            domain: Optional domain/URL for context
        
        Returns:
            Dict with:
                - selector: CSS or XPath selector string
                - selector_type: "css" or "xpath"
                - confidence: Confidence score (0.0 to 1.0)
                - coordinates: (x, y) tuple
                - metadata: Additional metadata (attributes, etc.)
        """
        try:
            logger.info(f"🔧 Trauma Center: Finding new selector for '{intent_description}'")
            
            # Validate image
            if not screenshot or len(screenshot) < 8:
                logger.warning("Invalid screenshot for selector recovery")
                return {
                    'selector': None,
                    'selector_type': 'css',
                    'confidence': 0.0,
                    'coordinates': (0, 0),
                    'metadata': {}
                }
            
            # Load image
            image_stream = io.BytesIO(screenshot)
            image = Image.open(image_stream)
            image = image.convert("RGB")
            width, height = image.size
            
            # Get coordinates using existing coordinate detection
            x, y, coord_confidence = self.get_click_coordinates(screenshot, intent_description)
            
            # Generate selector based on intent and coordinates
            # In production, this would use a specialized VLM that outputs selectors
            # For now, we use heuristics and coordinate-based generation
            selector = self._generate_selector_from_intent(intent_description, x, y, width, height)
            
            # Calculate confidence based on coordinate confidence and selector quality
            confidence = coord_confidence * 0.8  # Slightly lower for selector generation
            
            logger.info(f"✅ Trauma Center: Generated selector '{selector}' with confidence {confidence:.2f}")
            
            return {
                'selector': selector,
                'selector_type': 'css',
                'confidence': confidence,
                'coordinates': (x, y),
                'metadata': {
                    'intent': intent_description,
                    'domain': domain,
                    'generated_at': datetime.utcnow().isoformat(),
                    'image_size': {'width': width, 'height': height}
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Trauma Center: Failed to find new selector: {e}", exc_info=True)
            return {
                'selector': None,
                'selector_type': 'css',
                'confidence': 0.0,
                'coordinates': (0, 0),
                'metadata': {'error': str(e)}
            }
    
    def _generate_selector_from_intent(
        self,
        intent: str,
        x: int,
        y: int,
        image_width: int,
        image_height: int
    ) -> str:
        """
        Generate a CSS selector from intent description and coordinates.
        
        This is a heuristic-based approach. In production, you'd use a
        VLM that can analyze the screenshot and generate accurate selectors.
        
        Args:
            intent: Intent description
            x, y: Coordinates
            image_width, image_height: Image dimensions
        
        Returns:
            CSS selector string
        """
        intent_lower = intent.lower()
        
        # Intent-based selectors
        if "button" in intent_lower or "click" in intent_lower:
            if "login" in intent_lower or "sign in" in intent_lower:
                # Try common login button selectors
                return "button[type='submit'], .login-button, #login-button, button:contains('Login'), button:contains('Sign In')"
            elif "submit" in intent_lower:
                return "button[type='submit']"
            else:
                return "button"
        
        elif "input" in intent_lower or "field" in intent_lower or "search" in intent_lower:
            if "search" in intent_lower:
                return "input[type='search'], input[name='search'], #search, .search-input, input[placeholder*='search' i]"
            else:
                return "input"
        
        elif "link" in intent_lower or "anchor" in intent_lower:
            return "a"
        
        # Fallback: Use coordinate-based selector (not ideal, but works)
        # In production, VLM would generate proper selector
        logger.warning(f"Using fallback selector generation for intent: {intent}")
        return f"*"  # Generic fallback - would need DOM access for precise selector


class SimpleCoordinateDetector:
    """
    A simpler, faster coordinate detector for development/testing.
    
    This uses basic image processing to find UI elements.
    """
    
    def __init__(self):
        logger.info("Initializing simple coordinate detector")
    
    def get_click_coordinates(
        self, 
        image_bytes: bytes, 
        text_command: str
    ) -> Tuple[int, int, float]:
        """
        Simple coordinate detection using keyword matching and heuristics.
        """
        # Validate image bytes before processing
        if not image_bytes or len(image_bytes) < 8:
            logger.warning(f"Invalid image bytes: empty or too small ({len(image_bytes) if image_bytes else 0} bytes)")
            return (0, 0, 0.0)
        
        try:
            image_stream = io.BytesIO(image_bytes)
            image = Image.open(image_stream)
            image = image.convert("RGB")
            width, height = image.size
        except Exception as e:
            logger.error(f"Failed to open image: {e}")
            return (0, 0, 0.0)
        
        width, height = image.size
        
        # Convert to numpy for analysis
        img_array = np.array(image)
        
        # Simple keyword-based detection
        text_lower = text_command.lower()
        
        # Look for bright/colored regions (potential buttons)
        if "button" in text_lower:
            # Find regions with high saturation or brightness
            # This is very simplified - real implementation would be more sophisticated
            if "green" in text_lower:
                # Look for green regions
                green_mask = (img_array[:, :, 1] > img_array[:, :, 0]) & \
                            (img_array[:, :, 1] > img_array[:, :, 2])
                if green_mask.any():
                    y_coords, x_coords = np.where(green_mask)
                    x = int(np.mean(x_coords))
                    y = int(np.mean(y_coords))
                    confidence = 0.6
                    return (x, y, confidence)
        
        # Default: intelligent center based on common UI patterns
        if "top" in text_lower or "header" in text_lower:
            y = int(height * 0.15)
        elif "bottom" in text_lower or "footer" in text_lower:
            y = int(height * 0.85)
        else:
            y = height // 2
        
        if "left" in text_lower:
            x = int(width * 0.15)
        elif "right" in text_lower:
            x = int(width * 0.85)
        else:
            x = width // 2
        
        confidence = 0.5
        return (x, y, confidence)
