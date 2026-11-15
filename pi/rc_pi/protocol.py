"""CAN protocol shared with the ESP32 nodes.

Mirrors firmware/components/rc_common/include/rc_can_protocol.h.
tests/test_protocol.py checks that the two stay in sync.
"""

import struct
from dataclasses import dataclass

CAN_BITRATE = 500_000

ID_PI_CORRECTION = 0x100
ID_DRIVE_STATUS = 0x200
ID_SPEED = 0x300
ID_BATTERY = 0x301

TIMEOUT_S = 0.300

# Correction flags
CORR_FLAG_ACTIVE = 1 << 0
CORR_FLAG_BLOCK_FORWARD = 1 << 1
CORR_FLAG_LIDAR_OK = 1 << 2

NO_OBSTACLE_MM = 0xFFFF

# Drive status flags
DRIVE_FLAG_CONTROLLER = 1 << 0
DRIVE_FLAG_PI_ALIVE = 1 << 1
DRIVE_FLAG_CORRECTING = 1 << 2
DRIVE_FLAG_FAILSAFE = 1 << 3
DRIVE_FLAG_BATTERY_LIMIT = 1 << 4
DRIVE_FLAG_TELEMETRY = 1 << 5

# Battery flags
BATT_FLAG_LOW = 1 << 0
BATT_FLAG_CRITICAL = 1 << 1


@dataclass
class Correction:
    """0x100  Pi -> drive node."""

    FORMAT = "<BBbBH"

    counter: int = 0
    flags: int = 0
    steer_offset_deg: int = 0
    throttle_limit_pct: int = 100
    nearest_obstacle_mm: int = NO_OBSTACLE_MM

    def pack(self) -> bytes:
        return struct.pack(
            self.FORMAT,
            self.counter & 0xFF,
            self.flags,
            max(-128, min(127, self.steer_offset_deg)),
            max(0, min(100, self.throttle_limit_pct)),
            max(0, min(NO_OBSTACLE_MM, self.nearest_obstacle_mm)),
        )

    @classmethod
    def unpack(cls, data: bytes) -> "Correction":
        return cls(*struct.unpack(cls.FORMAT, data))


@dataclass
class DriveStatus:
    """0x200  drive node -> all."""

    FORMAT = "<BBHh"

    counter: int
    flags: int
    steering_deg: int
    throttle_permille: int

    @classmethod
    def unpack(cls, data: bytes) -> "DriveStatus":
        return cls(*struct.unpack(cls.FORMAT, data))


@dataclass
class Speed:
    """0x300  telemetry -> all."""

    FORMAT = "<BBHHH"

    counter: int
    reserved: int
    speed_mm_s: int
    wheel_rpm: int
    odometer_m: int

    @classmethod
    def unpack(cls, data: bytes) -> "Speed":
        return cls(*struct.unpack(cls.FORMAT, data))


@dataclass
class Battery:
    """0x301  telemetry -> all."""

    FORMAT = "<BBHBB"

    counter: int
    flags: int
    voltage_mv: int
    percent: int
    cells: int

    @classmethod
    def unpack(cls, data: bytes) -> "Battery":
        return cls(*struct.unpack(cls.FORMAT, data))
