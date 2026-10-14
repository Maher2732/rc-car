# RC Car

A custom RC car built around ESP32 boards, with steering from an Xbox controller and a CAN bus link between boards.

All ESP32 firmware is one ESP-IDF project in `firmware/`. Pick what the board does in `idf.py menuconfig` → **RC Car Configuration → Board role**:

| Role | What it does |
|------|--------------|
| Steering servo | Drives the steering servo from angles received over USB serial (from `tools/controller.py`) |
| CAN sender | Transmits a test frame every second over CAN (TWAI) |
| CAN receiver | Listens on the CAN bus (listen-only) and prints received frames |

## Steering (servo role)

A custom RC car steered by an Xbox controller. A Python script on a PC reads the controller and streams steering angles over USB serial to an ESP32, which drives the steering servo with hardware PWM.

```
Xbox controller ──► PC (controller.py) ──USB serial──► ESP32 (servo.c) ──PWM──► Steering servo
```

## Features

- **Analog steering** – left stick X axis maps proportionally to the servo angle, with a deadzone around center
- **Hardware PWM** – ESP32 LEDC peripheral generates a 50 Hz, 16‑bit resolution servo signal
- **Simple serial protocol** – newline‑terminated angle values (`135\n`), validated and clamped on the device
- **Bandwidth friendly** – the PC only sends a command when the angle changes, polling at ~50 Hz
- **Custom 3D‑printed parts** – drivetrain components such as the differential case and bearing

## Hardware

| Part | Notes |
|------|-------|
| ESP32 dev board | Running ESP-IDF firmware |
| 270° servo | 500–2500 µs pulse range, signal on **GPIO 18** |
| Xbox controller | Currently connected to the PC; moving to a direct Bluetooth link to the ESP32 |
| PC | Runs the Python controller bridge |

Steering is limited to a safe range of **100° (left) – 135° (center) – 170° (right)**.

## Project Structure

```
firmware/                  # single ESP-IDF project (one CMakeLists, one sdkconfig.defaults)
├── CMakeLists.txt
├── sdkconfig.defaults
└── main/
    ├── main.c             # app_main: runs the role chosen in menuconfig
    ├── servo.c            # LEDC servo PWM + UART command parser
    ├── can_sender.c       # TWAI transmitter
    ├── can_receiver.c     # TWAI listen-only receiver
    ├── can.h
    └── Kconfig.projbuild  # Board role + CAN pins
tools/
├── controller.py          # PC bridge: Xbox controller → serial angle commands
└── LidarML/               # Work in progress: RPLidar integration
```

## Getting Started

### 1. Flash the ESP32

Requires [ESP-IDF](https://docs.espressif.com/projects/esp-idf/) (developed on v6.1).

```bash
cd firmware
idf.py set-target esp32
idf.py menuconfig   # RC Car Configuration → Board role: Steering servo
idf.py build
idf.py -p COM4 flash monitor
```

On boot the servo centers at 135° and prints `Xbox steering ready`.

### 2. Run the controller bridge

```bash
pip install pygame pyserial
python tools/controller.py
```

Set `ESP32_PORT` in `controller.py` to your board's serial port (default `COM4`). Close the ESP-IDF monitor first, since only one program can hold the port.

## CAN Bus (sender / receiver roles)

Two ESP32 boards talk over a CAN bus using the ESP-IDF on-chip TWAI driver (`esp_twai`). Each board needs a CAN transceiver (e.g. SN65HVD230) between the GPIOs and the bus.

| Setting | Value |
|---------|-------|
| Bitrate | 500 kbit/s |
| Pins (default) | TX **GPIO 4**, RX **GPIO 5**; the receiver doesn't use TX (listen-only) |
| Test frame | ID `0x1`, standard 11-bit, 8 bytes `00 01 02 03 04 05 06 07`, sent every 1 s |

The receiver pushes frames from the RX interrupt into a FreeRTOS queue and prints the ID, DLC and data bytes. Because it is listen-only it never ACKs, so at least one other transmitting-capable node (the sender) must be on the bus along with proper 120 Ω termination at both ends.

Select **CAN sender** or **CAN receiver** as the board role in menuconfig, then build and flash as above.

## How It Works

**PC side:** `pygame` reads the left stick (−1.0 to +1.0). Values inside the deadzone snap to center, then each half of the stick maps linearly onto its side of the steering range. The angle is sent as ASCII text over serial at 115200 baud.

**ESP32 side:** UART0 bytes are buffered until a newline, parsed with `atoi`, and range‑checked (0–270°). The angle converts to a pulse width:

```
pulse_us = 500 + angle × (2500 − 500) / 270
duty     = pulse_us × 65535 / 20000
```

The duty is written to the LEDC channel, which outputs the 50 Hz PWM signal to the servo.

## Roadmap

- [ ] Send steering/throttle commands between boards over the CAN bus
- [ ] Throttle / ESC control on the right trigger
- [ ] RPLidar integration for obstacle detection
- [ ] Pair the Xbox controller directly to the ESP32 over Bluetooth using [Bluepad32](https://github.com/ricardoquesada/bluepad32), removing the PC bridge and USB tether
