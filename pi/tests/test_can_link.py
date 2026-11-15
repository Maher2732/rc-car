"""End-to-end CAN test on python-can's in-memory virtual bus (no hardware needed)."""

import struct
import time
import unittest

try:
    import can
except ImportError:     # python-can not installed
    can = None

from rc_pi import protocol


@unittest.skipIf(can is None, "python-can not installed")
class CanLinkTests(unittest.TestCase):
    def setUp(self):
        from rc_pi.can_link import CanLink

        self.link = CanLink(interface="virtual", channel="test")
        self.esp32 = can.Bus(interface="virtual", channel="test")     # stands in for both ESP32s

    def tearDown(self):
        self.link.close()
        self.esp32.shutdown()

    def wait_for(self, getter, timeout=1.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = getter()
            if value is not None:
                return value
            time.sleep(0.01)
        return None

    def test_receives_telemetry(self):
        self.esp32.send(can.Message(
            arbitration_id=protocol.ID_SPEED,
            data=struct.pack("<BBHHH", 1, 0, 1500, 300, 12),
            is_extended_id=False,
        ))
        speed = self.wait_for(self.link.speed)
        self.assertIsNotNone(speed)
        self.assertEqual(speed.speed_mm_s, 1500)

    def test_stale_telemetry_expires(self):
        self.esp32.send(can.Message(
            arbitration_id=protocol.ID_BATTERY,
            data=struct.pack("<BBHBB", 1, 0, 7600, 50, 2),
            is_extended_id=False,
        ))
        self.assertIsNotNone(self.wait_for(self.link.battery))
        time.sleep(protocol.TIMEOUT_S + 0.05)
        self.assertIsNone(self.link.battery())

    def test_correction_reaches_drive_node_id(self):
        self.link.send_correction(protocol.Correction(
            flags=protocol.CORR_FLAG_ACTIVE | protocol.CORR_FLAG_BLOCK_FORWARD,
            steer_offset_deg=-12,
            throttle_limit_pct=0,
            nearest_obstacle_mm=310,
        ))
        msg = self.esp32.recv(timeout=1.0)
        self.assertIsNotNone(msg)
        self.assertEqual(msg.arbitration_id, protocol.ID_PI_CORRECTION)
        self.assertFalse(msg.is_extended_id)

        decoded = protocol.Correction.unpack(bytes(msg.data))
        self.assertEqual(decoded.steer_offset_deg, -12)
        self.assertTrue(decoded.flags & protocol.CORR_FLAG_BLOCK_FORWARD)

    def test_counter_increments(self):
        for _ in range(3):
            self.link.send_correction(protocol.Correction())
        counters = [protocol.Correction.unpack(bytes(self.esp32.recv(timeout=1.0).data)).counter for _ in range(3)]
        self.assertEqual(counters, [0, 1, 2])


if __name__ == "__main__":
    unittest.main()
