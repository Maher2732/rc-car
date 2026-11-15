"""CAN bus connection: tracks telemetry from the ESP32s and sends corrections."""

import logging
import threading
import time
from typing import Optional

import can

from .protocol import (
    ID_BATTERY,
    ID_DRIVE_STATUS,
    ID_PI_CORRECTION,
    ID_SPEED,
    TIMEOUT_S,
    Battery,
    Correction,
    DriveStatus,
    Speed,
)

log = logging.getLogger(__name__)

DECODERS = {
    ID_DRIVE_STATUS: DriveStatus,
    ID_SPEED: Speed,
    ID_BATTERY: Battery,
}


class CanLink(can.Listener):
    def __init__(self, interface: str = "socketcan", channel: str = "can0"):
        self.bus = can.Bus(interface=interface, channel=channel)
        self._lock = threading.Lock()
        self._latest = {}           # message id -> (decoded, monotonic time)
        self._counter = 0
        self._notifier = can.Notifier(self.bus, [self])

    # ---------- Receiving (python-can calls this from its own thread) ----------

    def on_message_received(self, msg: can.Message) -> None:
        decoder = DECODERS.get(msg.arbitration_id)
        if decoder is None or msg.is_extended_id:
            return
        try:
            decoded = decoder.unpack(bytes(msg.data))
        except Exception:
            log.debug("Bad frame 0x%03x: %s", msg.arbitration_id, msg.data.hex())
            return
        with self._lock:
            self._latest[msg.arbitration_id] = (decoded, time.monotonic())

    def _fresh(self, msg_id: int):
        with self._lock:
            entry = self._latest.get(msg_id)
        if entry is None or time.monotonic() - entry[1] > TIMEOUT_S:
            return None
        return entry[0]

    def speed(self) -> Optional[Speed]:
        return self._fresh(ID_SPEED)

    def battery(self) -> Optional[Battery]:
        return self._fresh(ID_BATTERY)

    def drive_status(self) -> Optional[DriveStatus]:
        return self._fresh(ID_DRIVE_STATUS)

    # ---------- Sending ----------

    def send_correction(self, correction: Correction) -> None:
        correction.counter = self._counter
        self._counter = (self._counter + 1) & 0xFF

        msg = can.Message(arbitration_id=ID_PI_CORRECTION, data=correction.pack(), is_extended_id=False)
        try:
            self.bus.send(msg, timeout=0.01)
        except can.CanError as error:
            # Bus off or TX buffer full; the drive node treats silence as "Pi lost"
            log.warning("CAN send failed: %s", error)

    def close(self) -> None:
        self._notifier.stop()
        self.bus.shutdown()
