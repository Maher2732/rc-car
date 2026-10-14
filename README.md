# RC Car

A custom RC car steered by an Xbox controller. A Python script on a PC reads the controller and streams steering angles over USB serial to an ESP32, which drives the steering servo with hardware PWM.

```
Xbox controller ──► PC (controller.py) ──USB serial──► ESP32 (Servo_Main.c) ──PWM──► Steering servo
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
| Xbox controller | Connected to the PC (USB or Bluetooth) |
| PC | Runs the Python controller bridge |

Steering is limited to a safe range of **100° (left) – 135° (center) – 170° (right)**.

## Project Structure

```
ServoMotor/
├── main/
│   ├── Servo_Main.c     # ESP32 firmware: LEDC servo PWM + UART command parser
│   └── controller.py    # PC bridge: Xbox controller → serial angle commands
├── LidarML/             # Work in progress: RPLidar integration
├── CMakeLists.txt
└── sdkconfig
```

## Getting Started

### 1. Flash the ESP32

Requires [ESP-IDF](https://docs.espressif.com/projects/esp-idf/) (developed on v6.1).

```bash
cd ServoMotor
idf.py build
idf.py -p COM4 flash monitor
```

On boot the servo centers at 135° and prints `Xbox steering ready`.

### 2. Run the controller bridge

```bash
pip install pygame pyserial
python ServoMotor/main/controller.py
```

Set `ESP32_PORT` in `controller.py` to your board's serial port (default `COM4`). Close the ESP-IDF monitor first, since only one program can hold the port.

## How It Works

**PC side:** `pygame` reads the left stick (−1.0 to +1.0). Values inside the deadzone snap to center, then each half of the stick maps linearly onto its side of the steering range. The angle is sent as ASCII text over serial at 115200 baud.

**ESP32 side:** UART0 bytes are buffered until a newline, parsed with `atoi`, and range‑checked (0–270°). The angle converts to a pulse width:

```
pulse_us = 500 + angle × (2500 − 500) / 270
duty     = pulse_us × 65535 / 20000
```

The duty is written to the LEDC channel, which outputs the 50 Hz PWM signal to the servo.

## Roadmap

- [ ] Throttle / ESC control on the right trigger
- [ ] RPLidar integration for obstacle detection
- [ ] Wireless control (Bluetooth or Wi‑Fi) to remove the USB tether
