"""Raspberry Pi obstacle avoidance node.

Reads the lidar, looks for obstacles in the car's path, and sends steering /
throttle corrections to the drive ESP32 over CAN (ID 0x100) at 20 Hz.

    python -m rc_pi.main --lidar-port /dev/ttyUSB0 --can-channel can0
"""

import argparse
import logging
import signal
import time

from .avoidance import AvoidanceController
from .can_link import CanLink
from .config import AvoidanceConfig
from .lidar import LidarReader
from .protocol import BATT_FLAG_LOW, CORR_FLAG_BLOCK_FORWARD

PERIOD_S = 0.05     # 20 Hz

log = logging.getLogger("rc_pi")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lidar-port", default="/dev/ttyUSB0")
    parser.add_argument("--can-interface", default="socketcan")
    parser.add_argument("--can-channel", default="can0")
    parser.add_argument("--lidar-forward-deg", type=float, default=0.0,
                        help="lidar angle that points straight ahead")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    cfg = AvoidanceConfig(lidar_forward_deg=args.lidar_forward_deg)
    controller = AvoidanceController(cfg)
    link = CanLink(args.can_interface, args.can_channel)
    lidar = LidarReader(args.lidar_port)

    running = True

    def stop(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    lidar.start()
    log.info("Obstacle avoidance running")

    was_blocked = False
    battery_warned = False
    next_tick = time.monotonic()
    last_report = 0.0

    try:
        while running:
            scan, age = lidar.latest()
            speed = link.speed()
            speed_m_s = speed.speed_mm_s / 1000.0 if speed else None

            correction = controller.update(scan, age, speed_m_s)
            link.send_correction(correction)

            blocked = bool(correction.flags & CORR_FLAG_BLOCK_FORWARD)
            if blocked != was_blocked:
                if blocked:
                    log.warning("Obstacle at %d mm: forward blocked", correction.nearest_obstacle_mm)
                else:
                    log.info("Path clear")
                was_blocked = blocked

            battery = link.battery()
            if battery and battery.flags & BATT_FLAG_LOW and not battery_warned:
                log.warning("Battery low: %d mV (%d%%)", battery.voltage_mv, battery.percent)
                battery_warned = True

            now = time.monotonic()
            if now - last_report >= 1.0:
                drive = link.drive_status()
                log.debug(
                    "lidar_age=%.2fs speed=%s limit=%d%% offset=%+d nearest=%d drive=%s",
                    age, speed_m_s, correction.throttle_limit_pct, correction.steer_offset_deg,
                    correction.nearest_obstacle_mm, drive,
                )
                last_report = now

            # Fixed-rate loop that doesn't drift
            next_tick += PERIOD_S
            delay = next_tick - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            else:
                next_tick = time.monotonic()

    finally:
        log.info("Shutting down")
        lidar.stop()
        link.close()


if __name__ == "__main__":
    main()
