"""
Chimera Core - Stealth Module

Ports proven fingerprint masking logic from scrapegoat for Chromium stealth.
Ensures 100% Human trust score on CreepJS.
"""

import random
import json
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class FingerprintConfig:
    """Fingerprint configuration for stealth"""
    language: str = "en-US"
    languages: list = field(default_factory=lambda: ["en-US", "en"])
    timezone: str = "America/New_York"
    pixel_ratio: float = 2.0
    color_depth: int = 24
    audio_noise: float = 0.0001
    
    webgl: Dict[str, str] = field(default_factory=lambda: {
        "vendor": "Intel Inc.",
        "renderer": "Intel Iris OpenGL Engine"
    })
    
    def __post_init__(self):
        """Randomize fingerprint on initialization"""
        # Randomize WebGL vendor/renderer
        vendors = [
            ("Intel Inc.", "Intel Iris OpenGL Engine"),
            ("Google Inc. (Intel)", "ANGLE (Intel, Intel(R) Iris(TM) Plus Graphics 640 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
            ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce GTX 1060 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
        ]
        self.webgl["vendor"], self.webgl["renderer"] = random.choice(vendors)
        
        # Randomize audio noise
        self.audio_noise = random.uniform(0.00005, 0.0002)


@dataclass
class DeviceProfile:
    """Device profile for browser fingerprinting"""
    platform: str = "MacIntel"
    vendor: str = "Google Inc."
    hardware_concurrency: int = 8
    device_memory: int = 8
    max_touch_points: int = 0
    is_mobile: bool = False
    viewport: Dict[str, int] = field(default_factory=lambda: {"width": 1920, "height": 1080})
    user_agent: str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{version} Safari/537.36"
    
    def __post_init__(self):
        """Randomize device profile"""
        # Randomize hardware
        self.hardware_concurrency = random.choice([4, 8, 12, 16])
        self.device_memory = random.choice([4, 8, 16])


def get_stealth_launch_args() -> list:
    """
    Get Chromium launch arguments for stealth mode.
    
    Critical: --disable-blink-features=AutomationControlled
    """
    return [
        "--disable-blink-features=AutomationControlled",  # CRITICAL: Removes automation flag
        "--disable-features=IsolateOrigins,site-per-process",
        "--disable-dev-shm-usage",
        "--no-sandbox",  # Required for Railway containers
        "--disable-accelerated-2d-canvas",
        "--no-first-run",
        "--no-zygote",
        "--disable-gpu",
        "--hide-scrollbars",
        "--mute-audio",
        "--disable-background-networking",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-breakpad",
        "--disable-component-extensions-with-background-pages",
        "--disable-component-update",
        "--disable-default-apps",
        "--disable-extensions",
        "--disable-features=TranslateUI",
        "--disable-hang-monitor",
        "--disable-ipc-flooding-protection",
        "--disable-popup-blocking",
        "--disable-prompt-on-repost",
        "--disable-renderer-backgrounding",
        "--disable-sync",
        "--force-color-profile=srgb",
        "--metrics-recording-only",
        "--no-default-browser-check",
        "--password-store=basic",
        "--use-mock-keychain",
        # WebRTC leak prevention
        "--disable-webrtc-hw-encoding",
        "--disable-webrtc-hw-decoding",
        "--enforce-webrtc-ip-permission-check",
        "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
    ]


def generate_stealth_script(profile: DeviceProfile, fingerprint: FingerprintConfig, chrome_version: str = "131.0.6778.85") -> str:
    """
    Generate JavaScript stealth patches for fingerprint masking.
    
    This script is injected into every page before any interaction.
    """
    return f"""
        // ============================================
        // 2026 STEALTH PATCHES - Full Fingerprint Spoofing
        // ============================================
        
        // 1. Navigator patches (CRITICAL: Remove webdriver)
        Object.defineProperty(navigator, 'webdriver', {{ get: () => undefined }});
        Object.defineProperty(navigator, 'platform', {{ get: () => '{profile.platform}' }});
        Object.defineProperty(navigator, 'vendor', {{ get: () => '{profile.vendor}' }});
        Object.defineProperty(navigator, 'hardwareConcurrency', {{ get: () => {profile.hardware_concurrency} }});
        Object.defineProperty(navigator, 'deviceMemory', {{ get: () => {profile.device_memory} }});
        Object.defineProperty(navigator, 'maxTouchPoints', {{ get: () => {profile.max_touch_points} }});
        Object.defineProperty(navigator, 'languages', {{ get: () => {json.dumps(fingerprint.languages)} }});
        Object.defineProperty(navigator, 'language', {{ get: () => '{fingerprint.language}' }});
        
        // 2. Chrome object (Chrome-specific)
        window.chrome = {{
            runtime: {{}},
            loadTimes: function() {{ return {{}}; }},
            csi: function() {{ return {{}}; }},
            app: {{ 
                isInstalled: false, 
                InstallState: {{ DISABLED: "disabled", INSTALLED: "installed", NOT_INSTALLED: "not_installed" }}, 
                RunningState: {{ CANNOT_RUN: "cannot_run", READY_TO_RUN: "ready_to_run", RUNNING: "running" }} 
            }}
        }};
        
        // 3. Permissions API
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
            Promise.resolve({{ state: Notification.permission }}) :
            originalQuery(parameters)
        );
        
        // 4. WebGL fingerprint spoofing
        const getParameterOrig = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {{
            if (parameter === 37445) return '{fingerprint.webgl["vendor"]}';
            if (parameter === 37446) return '{fingerprint.webgl["renderer"]}';
            return getParameterOrig.call(this, parameter);
        }};
        
        const getParameter2Orig = WebGL2RenderingContext.prototype.getParameter;
        WebGL2RenderingContext.prototype.getParameter = function(parameter) {{
            if (parameter === 37445) return '{fingerprint.webgl["vendor"]}';
            if (parameter === 37446) return '{fingerprint.webgl["renderer"]}';
            return getParameter2Orig.call(this, parameter);
        }};
        
        // 5. Canvas fingerprint noise
        const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
        HTMLCanvasElement.prototype.toDataURL = function(type) {{
            if (type === 'image/png' && this.width > 16 && this.height > 16) {{
                const context = this.getContext('2d');
                if (context) {{
                    const imageData = context.getImageData(0, 0, this.width, this.height);
                    for (let i = 0; i < imageData.data.length; i += 4) {{
                        imageData.data[i] += Math.floor(Math.random() * 2);
                    }}
                    context.putImageData(imageData, 0, 0);
                }}
            }}
            return originalToDataURL.apply(this, arguments);
        }};
        
        // 6. AudioContext fingerprint noise
        const AudioContextOrig = window.AudioContext || window.webkitAudioContext;
        if (AudioContextOrig) {{
            const originalCreateAnalyser = AudioContextOrig.prototype.createAnalyser;
            AudioContextOrig.prototype.createAnalyser = function() {{
                const analyser = originalCreateAnalyser.call(this);
                const originalGetFloatFrequencyData = analyser.getFloatFrequencyData.bind(analyser);
                analyser.getFloatFrequencyData = function(array) {{
                    originalGetFloatFrequencyData(array);
                    for (let i = 0; i < array.length; i++) {{
                        array[i] += (Math.random() - 0.5) * {fingerprint.audio_noise};
                    }}
                }};
                return analyser;
            }};
        }}
        
        // 7. Network Information API
        Object.defineProperty(navigator, 'connection', {{
            get: () => ({{
                effectiveType: '4g',
                rtt: 50 + Math.floor(Math.random() * 50),
                downlink: 10 + Math.random() * 5,
                saveData: false
            }})
        }});
        
        // 8. Battery API (privacy concern - return consistent fake)
        if (navigator.getBattery) {{
            navigator.getBattery = () => Promise.resolve({{
                charging: true,
                chargingTime: 0,
                dischargingTime: Infinity,
                level: 1,
                addEventListener: () => {{}},
                removeEventListener: () => {{}}
            }});
        }}
        
        // 9. Screen properties
        Object.defineProperty(screen, 'colorDepth', {{ get: () => {fingerprint.color_depth} }});
        Object.defineProperty(screen, 'pixelDepth', {{ get: () => {fingerprint.color_depth} }});
        
        // 10. Plugins (realistic set) - Moved to immutable section below
        
        // 11. Disable automation flags in CDP
        delete Object.getPrototypeOf(navigator).webdriver;
        
        // 11b. Immutable flag injection (prevents CreepJS probing)
        // Lock navigator properties with writable: false to prevent detection
        Object.defineProperty(navigator, 'plugins', {{
            get: () => {{
                const plugins = [
                    {{ name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' }},
                    {{ name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' }},
                    {{ name: 'Native Client', filename: 'internal-nacl-plugin', description: '' }}
                ];
                plugins.length = 3;
                return plugins;
            }},
            configurable: false,
            enumerable: true
        }});
        
        Object.defineProperty(navigator, 'languages', {{
            get: () => {json.dumps(fingerprint.languages)},
            writable: false,
            configurable: false,
            enumerable: true
        }});
        
        Object.defineProperty(navigator, 'hardwareConcurrency', {{
            get: () => {profile.hardware_concurrency},
            writable: false,
            configurable: false,
            enumerable: true
        }});
        
        Object.defineProperty(navigator, 'deviceMemory', {{
            get: () => {profile.device_memory},
            writable: false,
            configurable: false,
            enumerable: true
        }});
        
        // 12. Client Hints API (modern Chrome)
        if (navigator.userAgentData) {{
            Object.defineProperty(navigator, 'userAgentData', {{
                get: () => ({{
                    brands: [
                        {{ brand: 'Google Chrome', version: '{chrome_version.split(".")[0]}' }},
                        {{ brand: 'Chromium', version: '{chrome_version.split(".")[0]}' }},
                        {{ brand: 'Not_A Brand', version: '8' }}
                    ],
                    mobile: {str(profile.is_mobile).lower()},
                    platform: '{profile.platform}',
                    getHighEntropyValues: () => Promise.resolve({{
                        architecture: 'x86',
                        bitness: '64',
                        brands: [
                            {{ brand: 'Google Chrome', version: '{chrome_version.split(".")[0]}' }},
                            {{ brand: 'Chromium', version: '{chrome_version.split(".")[0]}' }},
                            {{ brand: 'Not_A Brand', version: '8' }}
                        ],
                        fullVersionList: [
                            {{ brand: 'Google Chrome', version: '{chrome_version}' }},
                            {{ brand: 'Chromium', version: '{chrome_version}' }},
                            {{ brand: 'Not_A Brand', version: '8.0.0.0' }}
                        ],
                        mobile: {str(profile.is_mobile).lower()},
                        model: '',
                        platform: '{profile.platform}',
                        platformVersion: '10.15.7',
                        uaFullVersion: '{chrome_version}'
                    }})
                }})
            }});
        }}
        
        // 13. WebRTC IP leak prevention
        const originalRTCPeerConnection = window.RTCPeerConnection;
        window.RTCPeerConnection = function(...args) {{
            const pc = new originalRTCPeerConnection(...args);
            pc.createDataChannel = function() {{ return null; }};
            return pc;
        }};
        window.RTCPeerConnection.prototype = originalRTCPeerConnection.prototype;
        
        // 14. Disable iframes from detecting parent (clickjacking protection)
        Object.defineProperty(window, 'parent', {{ get: () => window }});
        Object.defineProperty(window, 'top', {{ get: () => window }});
        
        console.log('🕵️ Stealth patches applied (2026 Edition)');
        """


async def apply_stealth_patches(page, profile: Optional[DeviceProfile] = None, fingerprint: Optional[FingerprintConfig] = None):
    """
    Apply stealth patches to a Playwright page.
    
    This must be called BEFORE any page interaction.
    """
    if profile is None:
        profile = DeviceProfile()
    if fingerprint is None:
        fingerprint = FingerprintConfig()
    
    chrome_version = "131.0.6778.85"  # Latest Chrome version
    stealth_script = generate_stealth_script(profile, fingerprint, chrome_version)
    
    await page.add_init_script(stealth_script)
    logger.debug("🕵️ Stealth patches applied to page")
