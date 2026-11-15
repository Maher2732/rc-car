"""Background RPLidar reader that always holds the most recent full scan."""

import logging
import threading
import time
from typing import Optional, Tuple

from rplidar import RPLidar, RPLidarException

log = logging.getLogger(__name__)

RECONNECT_DELAY_S = 2.0


class LidarReader:
    def __init__(self, port: str):
        self.port = port
        self._lock = threading.Lock()
        self._scan = None
        self._scan_time = 0.0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="lidar", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=3)

    def latest(self) -> Tuple[Optional[list], float]:
        """Returns (scan, age in seconds). scan is None until the first one arrives."""
        with self._lock:
            if self._scan is None:
                return None, float("inf")
            return self._scan, time.monotonic() - self._scan_time

    def _run(self) -> None:
        while not self._stop.is_set():
            lidar = None
            try:
                lidar = RPLidar(self.port)
                log.info("Lidar connected on %s: %s", self.port, lidar.get_info())

                for scan in lidar.iter_scans(max_buf_meas=1000):
                    with self._lock:
                        self._scan = scan
                        self._scan_time = time.monotonic()
                    if self._stop.is_set():
                        break

            except (RPLidarException, OSError) as error:
                # Unplugged, garbled serial data, motor stall... retry instead of dying
                log.warning("Lidar error: %s, reconnecting", error)
                self._stop.wait(RECONNECT_DELAY_S)

            finally:
                if lidar is not None:
                    try:
                        lidar.stop()
                        lidar.stop_motor()
                        lidar.disconnect()
                    except Exception:
                        pass
