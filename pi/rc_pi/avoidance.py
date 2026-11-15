"""Obstacle avoidance: lidar scan + wheel speed -> correction for the drive node.

Pure logic with no hardware access, so it can be unit tested.

Coordinate frame (car body):
    x  forward, metres
    y  right, metres
    angle 0 = straight ahead, positive = clockwise (to the right), like the RPLidar
"""

import math
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence, Tuple

from .config import AvoidanceConfig
from .protocol import (
    CORR_FLAG_ACTIVE,
    CORR_FLAG_BLOCK_FORWARD,
    CORR_FLAG_LIDAR_OK,
    NO_OBSTACLE_MM,
    Correction,
)

# One lidar return: (quality, angle_deg, distance_mm), as produced by rplidar.iter_scans()
Measurement = Tuple[int, float, float]


@dataclass
class Point:
    angle_deg: float    # relative to the car's nose, -180 .. 180, positive = right
    x: float
    y: float
    distance: float


def to_car_frame(scan: Iterable[Measurement], cfg: AvoidanceConfig) -> list:
    """Converts raw lidar measurements into car-frame points, dropping bad returns."""
    points = []

    for quality, angle_deg, distance_mm in scan:
        distance = distance_mm / 1000.0
        if quality == 0 or distance < cfg.min_range:
            continue

        rel = (angle_deg - cfg.lidar_forward_deg + 180.0) % 360.0 - 180.0
        rad = math.radians(rel)
        points.append(Point(rel, distance * math.cos(rad), distance * math.sin(rad), distance))

    return points


def nearest_in_path(points: Sequence[Point], cfg: AvoidanceConfig) -> Optional[float]:
    """Distance ahead to the closest point inside the corridor the car will drive through."""
    half = cfg.car_half_width + cfg.path_margin
    ahead = [p.x for p in points if p.x > 0 and abs(p.y) <= half]
    return min(ahead) if ahead else None


def side_clearance(points: Sequence[Point], cfg: AvoidanceConfig, right: bool) -> float:
    """Closest return in the forward-left or forward-right sector, capped at the lookahead."""
    low, high = cfg.side_sector_deg
    closest = cfg.lookahead

    for p in points:
        angle = p.angle_deg if right else -p.angle_deg
        if low <= angle <= high and p.distance < closest:
            closest = p.distance

    return closest


def stopping_distance(speed: float, cfg: AvoidanceConfig) -> float:
    return cfg.stop_buffer + speed * cfg.reaction_time + speed * speed / (2.0 * cfg.braking_decel)


class AvoidanceController:
    """Turns each new scan into a Correction. Keeps a little state for hysteresis and smoothing."""

    def __init__(self, cfg: Optional[AvoidanceConfig] = None):
        self.cfg = cfg or AvoidanceConfig()
        self.blocked = False
        self._offset = 0.0

    def update(self, scan: Optional[Sequence[Measurement]], scan_age_s: float,
               speed_m_s: Optional[float]) -> Correction:
        cfg = self.cfg

        # ---------- Lidar unavailable: no avoidance possible, so slow the car ----------
        if scan is None or scan_age_s > cfg.lidar_timeout_s:
            self.blocked = False
            self._offset = 0.0
            return Correction(flags=CORR_FLAG_ACTIVE, throttle_limit_pct=cfg.lidar_lost_limit_pct)

        speed = cfg.fallback_speed if speed_m_s is None else speed_m_s
        points = to_car_frame(scan, cfg)
        nearest = nearest_in_path(points, cfg)

        stop = stopping_distance(speed, cfg)
        slow = stop + cfg.slow_zone

        # ---------- Throttle ----------
        if nearest is None:
            self.blocked = False
        elif nearest <= stop:
            self.blocked = True
        elif self.blocked and nearest > stop + cfg.release_hysteresis:
            self.blocked = False

        flags = CORR_FLAG_LIDAR_OK
        limit = 100
        closeness = 0.0

        if self.blocked:
            flags |= CORR_FLAG_ACTIVE | CORR_FLAG_BLOCK_FORWARD
            limit = 0
            closeness = 1.0
        elif nearest is not None and nearest < slow:
            # 0 at the edge of the slow zone, 1 at the stop distance
            closeness = (slow - nearest) / (slow - stop)
            limit = round(100 - closeness * (100 - cfg.min_slow_limit_pct))
            flags |= CORR_FLAG_ACTIVE

        # ---------- Steering: lean toward the side with more room ----------
        target = 0.0
        if closeness > 0:
            left = side_clearance(points, cfg, right=False)
            right = side_clearance(points, cfg, right=True)
            direction = 1.0 if right > left else -1.0
            target = direction * closeness * cfg.max_steer_offset_deg

        self._offset += cfg.steer_smoothing * (target - self._offset)
        if abs(self._offset) < 0.5:
            self._offset = 0.0

        nearest_mm = NO_OBSTACLE_MM if nearest is None else min(int(nearest * 1000), NO_OBSTACLE_MM)
        any_m = min((p.distance for p in points), default=None)
        any_mm = NO_OBSTACLE_MM if any_m is None else min(int(any_m * 1000), NO_OBSTACLE_MM)

        return Correction(
            flags=flags,
            steer_offset_deg=int(round(self._offset)),
            throttle_limit_pct=limit,
            nearest_obstacle_mm=nearest_mm,
            nearest_any_mm=any_mm,
        )
