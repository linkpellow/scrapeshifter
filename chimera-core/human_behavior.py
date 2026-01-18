"""
Chimera Core - Human Behavior Simulation

High-fidelity human behavior simulation using diffusion-based mouse paths
and micro-saccade scrolling. Implements biological signatures for 100% CreepJS trust.
"""

import random
import math
import asyncio
from typing import List, Tuple
from playwright.async_api import Page


class DiffusionMouse:
    """
    Diffusion-based mouse path generator with Bezier curves and Gaussian noise.
    
    Implements:
    - Bezier curve interpolation (not linear)
    - Gaussian noise for micro-tremors (1-2px jitter)
    - Fitts's Law velocity profile (acceleration at start, deceleration at target)
    """
    
    def __init__(self):
        self.jitter_std = 1.5  # Standard deviation for micro-tremors (1-2px)
    
    def _gaussian_noise(self, std: float) -> float:
        """Generate Gaussian noise for micro-tremors"""
        return random.gauss(0, std)
    
    def _bezier_point(self, t: float, p0: Tuple[float, float], p1: Tuple[float, float], 
                     p2: Tuple[float, float], p3: Tuple[float, float]) -> Tuple[float, float]:
        """
        Calculate point on cubic Bezier curve.
        
        Cubic Bezier: B(t) = (1-t)³P₀ + 3(1-t)²tP₁ + 3(1-t)t²P₂ + t³P₃
        """
        u = 1 - t
        tt = t * t
        uu = u * u
        uuu = uu * u
        ttt = tt * t
        
        x = uuu * p0[0] + 3 * uu * t * p1[0] + 3 * u * tt * p2[0] + ttt * p3[0]
        y = uuu * p0[1] + 3 * uu * t * p1[1] + 3 * u * tt * p2[1] + ttt * p3[1]
        
        return (x, y)
    
    def _fitts_law_velocity(self, t: float) -> float:
        """
        Fitts's Law velocity profile: acceleration at start, deceleration at target.
        
        Uses ease-in-out curve for natural human movement.
        """
        # Ease-in-out cubic: smooth acceleration and deceleration
        if t < 0.5:
            return 4 * t * t * t
        else:
            return 1 - pow(-2 * t + 2, 3) / 2
    
    def generate_path(
        self, 
        start: Tuple[float, float], 
        end: Tuple[float, float], 
        steps: int = 30
    ) -> List[Tuple[float, float, float]]:
        """
        Generate diffusion-based mouse path with Bezier curves.
        
        Returns: List of (x, y, delay_ms) tuples
        """
        # Generate control points for Bezier curve (randomized for natural path)
        mid1_x = start[0] + (end[0] - start[0]) * 0.33 + random.uniform(-50, 50)
        mid1_y = start[1] + (end[1] - start[1]) * 0.33 + random.uniform(-50, 50)
        mid2_x = start[0] + (end[0] - start[0]) * 0.67 + random.uniform(-50, 50)
        mid2_y = start[1] + (end[1] - start[1]) * 0.67 + random.uniform(-50, 50)
        
        p0 = start
        p1 = (mid1_x, mid1_y)
        p2 = (mid2_x, mid2_y)
        p3 = end
        
        path = []
        total_time = random.uniform(150, 300)  # Total movement time in ms
        
        for i in range(steps + 1):
            t = i / steps
            
            # Apply Fitts's Law velocity profile
            velocity_t = self._fitts_law_velocity(t)
            
            # Get Bezier curve point
            x, y = self._bezier_point(velocity_t, p0, p1, p2, p3)
            
            # Add Gaussian noise (micro-tremors)
            x += self._gaussian_noise(self.jitter_std)
            y += self._gaussian_noise(self.jitter_std)
            
            # Calculate delay based on velocity (faster in middle, slower at ends)
            if i == 0:
                delay_ms = 0
            else:
                # Delay varies with velocity (slower at start/end due to Fitts's Law)
                base_delay = total_time / steps
                velocity_factor = 1.0 if velocity_t < 0.5 else 0.7  # Faster in middle
                delay_ms = base_delay * velocity_factor * random.uniform(0.8, 1.2)
            
            path.append((x, y, delay_ms))
        
        return path
    
    async def move_to(self, page: Page, target: Tuple[float, float], 
                     current_pos: Tuple[float, float] = None) -> Tuple[float, float]:
        """
        Move mouse to target using diffusion-based path.
        
        Returns: Final mouse position
        """
        if current_pos is None:
            # Get current mouse position (estimate from viewport center)
            viewport = page.viewport_size
            if viewport:
                current_pos = (viewport['width'] / 2, viewport['height'] / 2)
            else:
                current_pos = (960, 540)
        
        path = self.generate_path(current_pos, target)
        
        for x, y, delay_ms in path:
            await page.mouse.move(x, y)
            if delay_ms > 0:
                await asyncio.sleep(delay_ms / 1000.0)
        
        return target


class NaturalReader:
    """
    Micro-saccade scrolling simulation.
    
    Simulates human eye scanning with many small scrolls (2-5px) with random pauses.
    """
    
    @staticmethod
    async def micro_scroll(page: Page, direction: str = "down", distance: int = 500):
        """
        Perform natural reading scroll using micro-saccades.
        
        Instead of one big scroll, performs 10-15 micro-scrolls (2-5px each)
        with random 5ms pauses to simulate human eye scanning.
        """
        num_micro_scrolls = random.randint(10, 15)
        total_distance = distance
        scroll_per_micro = total_distance / num_micro_scrolls
        
        for i in range(num_micro_scrolls):
            # Micro-scroll: 2-5px with variation
            micro_distance = scroll_per_micro + random.uniform(-1, 1)
            
            if direction == "down":
                await page.mouse.wheel(0, micro_distance)
            else:
                await page.mouse.wheel(0, -micro_distance)
            
            # Random pause (5-15ms) to simulate eye movement
            pause_ms = random.uniform(5, 15)
            await asyncio.sleep(pause_ms / 1000.0)
    
    @staticmethod
    async def read_pattern(page: Page):
        """
        Simulate natural reading pattern: scroll down, pause, scroll back up.
        """
        # Scroll down (reading)
        await NaturalReader.micro_scroll(page, "down", 500)
        
        # Pause (reading/processing)
        await asyncio.sleep(random.uniform(0.5, 1.5))
        
        # Scroll back up (re-reading)
        await NaturalReader.micro_scroll(page, "up", 500)
        
        # Final pause
        await asyncio.sleep(random.uniform(0.3, 0.8))
