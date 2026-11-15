"""Keeps the Python protocol in sync with the C header the ESP32s use."""

import re
import struct
import unittest
from pathlib import Path

from rc_pi import protocol

HEADER = Path(__file__).resolve().parents[2] / "firmware/components/rc_common/include/rc_can_protocol.h"


def header_defines():
    defines = {}
    for name, value in re.findall(r"#define\s+(RC_\w+)\s+(.+?)\s*(?://.*)?$", HEADER.read_text(), re.M):
        defines[name] = eval(value.replace("(", "").replace(")", ""))
    return defines


def header_struct_sizes():
    sizes = {}
    for struct_name, size in re.findall(r"sizeof\((rc_\w+_t)\) == (\d+)", HEADER.read_text()):
        sizes[struct_name] = int(size)
    return sizes


class ProtocolSyncTests(unittest.TestCase):
    def setUp(self):
        self.defines = header_defines()

    def test_ids_match(self):
        self.assertEqual(protocol.ID_PI_CORRECTION, self.defines["RC_CAN_ID_PI_CORRECTION"])
        self.assertEqual(protocol.ID_DRIVE_STATUS, self.defines["RC_CAN_ID_DRIVE_STATUS"])
        self.assertEqual(protocol.ID_SPEED, self.defines["RC_CAN_ID_SPEED"])
        self.assertEqual(protocol.ID_BATTERY, self.defines["RC_CAN_ID_BATTERY"])
        self.assertEqual(protocol.CAN_BITRATE, self.defines["RC_CAN_BITRATE"])
        self.assertAlmostEqual(protocol.TIMEOUT_S * 1000, self.defines["RC_CAN_TIMEOUT_MS"])

    def test_flags_match(self):
        pairs = {
            "CORR_FLAG_ACTIVE": "RC_CORR_FLAG_ACTIVE",
            "CORR_FLAG_BLOCK_FORWARD": "RC_CORR_FLAG_BLOCK_FORWARD",
            "CORR_FLAG_LIDAR_OK": "RC_CORR_FLAG_LIDAR_OK",
            "DRIVE_FLAG_CONTROLLER": "RC_DRIVE_FLAG_CONTROLLER",
            "DRIVE_FLAG_PI_ALIVE": "RC_DRIVE_FLAG_PI_ALIVE",
            "DRIVE_FLAG_CORRECTING": "RC_DRIVE_FLAG_CORRECTING",
            "DRIVE_FLAG_FAILSAFE": "RC_DRIVE_FLAG_FAILSAFE",
            "DRIVE_FLAG_BATTERY_LIMIT": "RC_DRIVE_FLAG_BATTERY_LIMIT",
            "DRIVE_FLAG_TELEMETRY": "RC_DRIVE_FLAG_TELEMETRY",
            "BATT_FLAG_LOW": "RC_BATT_FLAG_LOW",
            "BATT_FLAG_CRITICAL": "RC_BATT_FLAG_CRITICAL",
            "NO_OBSTACLE_MM": "RC_NO_OBSTACLE_MM",
        }
        for py_name, c_name in pairs.items():
            self.assertEqual(getattr(protocol, py_name), self.defines[c_name], py_name)

    def test_struct_sizes_match(self):
        sizes = header_struct_sizes()
        self.assertEqual(struct.calcsize(protocol.Correction.FORMAT), sizes["rc_pi_correction_t"])
        self.assertEqual(struct.calcsize(protocol.DriveStatus.FORMAT), sizes["rc_drive_status_t"])
        self.assertEqual(struct.calcsize(protocol.Speed.FORMAT), sizes["rc_speed_t"])
        self.assertEqual(struct.calcsize(protocol.Battery.FORMAT), sizes["rc_battery_t"])


class PackingTests(unittest.TestCase):
    def test_correction_round_trip(self):
        original = protocol.Correction(7, protocol.CORR_FLAG_ACTIVE, -25, 40, 850)
        self.assertEqual(protocol.Correction.unpack(original.pack()), original)

    def test_correction_values_are_clamped(self):
        packed = protocol.Correction(300, 0, -500, 250, 99999).pack()
        decoded = protocol.Correction.unpack(packed)
        self.assertEqual(decoded.counter, 300 & 0xFF)
        self.assertEqual(decoded.steer_offset_deg, -128)
        self.assertEqual(decoded.throttle_limit_pct, 100)
        self.assertEqual(decoded.nearest_obstacle_mm, protocol.NO_OBSTACLE_MM)

    def test_battery_decode(self):
        data = struct.pack("<BBHBB", 1, protocol.BATT_FLAG_LOW, 7400, 35, 2)
        battery = protocol.Battery.unpack(data)
        self.assertEqual(battery.voltage_mv, 7400)
        self.assertEqual(battery.cells, 2)


if __name__ == "__main__":
    unittest.main()
