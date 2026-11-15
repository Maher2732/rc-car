"""Tunable settings for obstacle avoidance. Distances in metres."""

from dataclasses import dataclass


@dataclass
class AvoidanceConfig:
    # ---------- Car geometry ----------
    car_half_width: float = 0.10        # half the car's width
    path_margin: float = 0.08           # extra clearance on each side of the path
    min_range: float = 0.12             # ignore returns closer than this (the car itself)

    # Lidar angle that points straight ahead. RPLidar angles run clockwise
    # from the arrow on the sensor; set this if the lidar is mounted rotated.
    lidar_forward_deg: float = 0.0

    # ---------- Stopping distance ----------
    #   stop = buffer + speed * reaction + speed^2 / (2 * decel)
    stop_buffer: float = 0.25
    reaction_time: float = 0.15         # CAN + control loop + ESC latency
    braking_decel: float = 3.0          # m/s^2, measure on your surface
    release_hysteresis: float = 0.10    # must back off this far before unblocking

    slow_zone: float = 1.0              # start slowing this far beyond the stop distance
    min_slow_limit_pct: int = 20        # throttle limit at the edge of the stop zone

    # Assumed speed when the telemetry node is silent (be pessimistic)
    fallback_speed: float = 1.5

    # ---------- Steering ----------
    max_steer_offset_deg: int = 30      # drive node still clamps to the mechanical limits
    side_sector_deg: tuple = (10.0, 80.0)
    lookahead: float = 2.5
    steer_smoothing: float = 0.5        # 0 = frozen, 1 = no smoothing

    # ---------- Sensor health ----------
    lidar_timeout_s: float = 0.5
    lidar_lost_limit_pct: int = 30
