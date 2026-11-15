# RC Car

An autonomous-assist RC car built on three networked computers. You drive it with an Xbox controller paired straight to an ESP32 over Bluetooth. A Raspberry Pi watches the road with a 360° lidar and steps in when you're about to hit something. A second ESP32 measures wheel speed and battery health. All three talk over a CAN bus, the same kind of network real cars use.

```
                    Bluetooth (Bluepad32)
  Xbox controller  ─────────────────────►  ┌──────────────────────┐ ──PWM──► Steering servo
                                           │  DRIVE NODE (ESP32)  │
                                           │  steering + motor    │ ──PWM──► ESC ──► Motor
                                           └──────────┬───────────┘
                                                      │
  ════════════════════════════ CAN bus, 500 kbit/s ═══╪══════════════════════════════
            │                                         │
  ┌─────────┴──────────────┐            ┌─────────────┴─────────┐
  │  RASPBERRY PI          │            │  TELEMETRY NODE       │ ◄── Hall sensor (wheel)
  │  lidar obstacle        │            │  (ESP32)              │ ◄── Battery voltage divider
  │  avoidance             │            │  speed + battery      │
  └─────────┬──────────────┘            └───────────────────────┘
            ▲
         RPLidar
```

## How It Works

1. **You drive.** The drive node reads the controller over Bluetooth and drives the steering servo and the ESC. No PC and no cables.
2. **The telemetry node measures.** It counts wheel pulses for speed and reads the battery voltage, then broadcasts both on the CAN bus.
3. **The Pi watches.** Every lidar scan, it looks for anything inside the corridor the car is about to drive through. It works out a stopping distance from the *current speed*, so a faster car reacts earlier.
4. **The Pi corrects.** It sends a correction addressed to the drive node (CAN ID `0x100`) at 20 Hz: a throttle limit, a steering nudge toward the side with more room, or a full forward block. The drive node merges this with your input. You stay in control, and the car just won't let you drive into a wall.

## Engineering Highlights

- **Fail-safe by default.** Every link has a timeout, and losing one makes the car *more* cautious, never less:

  | Fault | Response |
  |-------|----------|
  | Controller disconnects | Neutral throttle, centered steering |
  | Pi stops sending (crash, unplugged, booting) | Forward throttle capped at 50% |
  | Lidar stops producing scans | Pi caps throttle at 30% |
  | Telemetry silent | Pi assumes a pessimistic speed for braking distance |
  | Battery critically low | Throttle capped at 30%, latched until reboot |
  | CAN controller goes bus-off | Automatic recovery |

- **Speed-aware braking.** Stop distance = buffer + speed × reaction time + speed² / (2 × deceleration), with hysteresis so the block doesn't chatter at the threshold.
- **Shared protocol, checked in CI.** The CAN message layout lives in one C header. A Python test parses that header and fails if the Pi's copy drifts.
- **Pure, testable logic.** The rules for merging driver input with corrections (`drive_logic.c`) and the avoidance algorithm (`avoidance.py`) contain no hardware calls. The avoidance code has unit tests.
- **Drivetrain protection.** Throttle can only rise at a limited rate, which protects the 3D-printed differential from shock loads. Letting off and braking still take effect instantly.
- **Haptic feedback.** The controller rumbles when the Pi blocks forward motion.
- **Real-time structure.** On the drive node, Bluetooth runs on core 0 and the 50 Hz control loop is pinned to core 1.

## Controls

| Input | Action |
|-------|--------|
| Left stick X | Steering |
| Right trigger | Throttle |
| Left trigger | Brake / reverse |
| Y | Toggle slow (40%) / fast (100%) mode |
| D-pad left / right | Steering trim (±1° per press) |

**Pairing:** power on the drive node, then hold the pair button on top of the Xbox controller until the logo flashes quickly. After the first pairing, the controller reconnects automatically. Only one controller can connect at a time. To forget the pairing, run `idf.py erase-flash` and reflash.

## Hardware

| Part | Notes |
|------|-------|
| 2× ESP32 dev board | Classic ESP32 (needs Bluetooth Classic + BLE for Xbox controllers) |
| Raspberry Pi | Any model with SPI; runs Raspberry Pi OS |
| 3× CAN transceiver | SN65HVD230 for each ESP32; MCP2515 CAN HAT for the Pi |
| Slamtec RPLIDAR A1M8 | 360°, 12 m range, USB to the Pi |
| 270° steering servo | 500–2500 µs pulse range |
| INJORA 540 35T brushed motor | Driven by a brushed RC ESC (1000–2000 µs, forward/reverse) |
| Hall sensor + magnets | On a wheel or axle, for speed |
| Zeee 2S 7.4 V 2200 mAh LiPo | Voltage measured through a 100k / 33k divider |
| Xbox Wireless Controller | Paired over Bluetooth |

### Wiring

**Drive node**

| ESP32 pin | Connects to |
|-----------|-------------|
| GPIO 18 | Steering servo signal |
| GPIO 19 | ESC signal |
| GPIO 4 | CAN transceiver TX |
| GPIO 5 | CAN transceiver RX |

**Telemetry node**

| ESP32 pin | Connects to |
|-----------|-------------|
| GPIO 27 | Hall sensor output (internal pull-up) |
| GPIO 34 | Battery divider midpoint |
| GPIO 4 | CAN transceiver TX |
| GPIO 5 | CAN transceiver RX |

CAN pins default to GPIO 4 / 5 and can be changed in menuconfig.

**CAN bus:** connect CANH to CANH and CANL to CANL on all three transceivers, put a **120 Ω terminator at each end** of the bus, and share a common ground. Power the servo from the ESC's BEC or a separate 5–6 V supply, not from the ESP32.

## CAN Protocol

Classic CAN at 500 kbit/s, 11-bit IDs, little-endian. Full definition: [`rc_can_protocol.h`](firmware/components/rc_common/include/rc_can_protocol.h).

| ID | From → To | Rate | Contents |
|----|-----------|------|----------|
| `0x100` | Pi → Drive | 20 Hz | Steering offset, throttle limit, block-forward flag, nearest obstacle |
| `0x200` | Drive → all | 20 Hz | Steering angle, throttle, status flags |
| `0x300` | Telemetry → all | 20 Hz | Speed (mm/s), wheel RPM, odometer |
| `0x301` | Telemetry → all | 5 Hz | Pack voltage, % charge, low/critical flags |

Each message carries a rolling counter, and receivers treat a message older than 300 ms as "node offline".

## Getting Started

### 1. Clone with submodules

Bluepad32 and BTstack are git submodules:

```bash
git clone --recursive https://github.com/Maher2732/rc-car.git
```

If you already cloned without `--recursive`:

```bash
git submodule update --init --recursive
```

### 2. Flash the ESP32s

Requires [ESP-IDF](https://docs.espressif.com/projects/esp-idf/) v6.1. Every ESP32 runs the same firmware project; you pick what each board does in menuconfig:

```bash
cd firmware
idf.py menuconfig
```

Go to **RC Car Configuration → Board role** and choose one:

| Role | What it does |
|------|--------------|
| Drive node *(default)* | Xbox controller over Bluetooth, steering servo, ESC, applies Pi corrections |
| Telemetry node | Wheel speed and battery monitoring |
| CAN sender | Test tool: sends a frame every second |
| CAN receiver | Test tool: listen-only, prints every frame on the bus |

Then build and flash:

```bash
idf.py build flash monitor
```

Changing role rewrites `sdkconfig`, so flash one board, change the role, and flash the next. The CAN sender/receiver roles are handy for checking the wiring and termination before running the real nodes.

Tune pins, steering limits, speed modes and battery settings in `main/drive/config.h` and `main/telemetry/config.h`.

### 3. Set up the Raspberry Pi

Enable the CAN HAT in `/boot/firmware/config.txt`. Match `oscillator` to the crystal on your HAT:

```
dtparam=spi=on
dtoverlay=mcp2515-can0,oscillator=8000000,interrupt=25
```

Bring `can0` up at boot and install the code:

```bash
sudo cp pi/deploy/can0.network /etc/systemd/network/80-can0.network
sudo systemctl enable --now systemd-networkd
cd pi && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Run it by hand:

```bash
.venv/bin/python -m rc_pi.main --lidar-port /dev/ttyUSB0 --verbose
```

Or install it as a service that starts at boot:

```bash
sudo cp deploy/rc-pi.service /etc/systemd/system/ && sudo systemctl enable --now rc-pi
```

Tune car width, braking deceleration and lidar mounting angle in [`pi/rc_pi/config.py`](pi/rc_pi/config.py).

### 4. Run the tests

```bash
cd pi && python -m unittest discover -s tests -t . -v
```

GitHub Actions runs these tests and builds the firmware in every board role on every push.

## Project Structure

```
firmware/                      # One ESP-IDF project, board role chosen in menuconfig
├── main/
│   ├── main.c                 #   Runs the selected role
│   ├── Kconfig.projbuild      #   Board role + CAN pins
│   ├── drive/                 #   Role: drive node
│   │   ├── gamepad.c          #     Bluepad32 platform: Xbox controller input
│   │   ├── drive_logic.c      #     Merges driver input with Pi corrections and limits
│   │   ├── actuators.c        #     Servo + ESC PWM
│   │   └── config.h           #     Pins and tuning
│   ├── telemetry/             #   Role: telemetry node
│   │   ├── speed_sensor.c     #     Hall sensor via hardware pulse counter
│   │   ├── battery.c          #     Calibrated ADC, LiPo charge estimate, low/critical flags
│   │   └── config.h
│   ├── can_sender.c           #   Role: CAN test sender
│   └── can_receiver.c         #   Role: CAN test receiver
├── components/rc_common/      # Shared CAN driver + protocol header
└── external/bluepad32/        # Submodule
pi/
├── rc_pi/
│   ├── avoidance.py           # Obstacle detection + correction logic
│   ├── lidar.py               # Background RPLidar reader with auto-reconnect
│   ├── can_link.py            # CAN send/receive
│   ├── protocol.py            # Python mirror of the CAN protocol
│   └── main.py                # 20 Hz main loop
├── tests/                     # Unit tests (avoidance, protocol sync, CAN link)
└── deploy/                    # systemd service + CAN interface config
```

## Roadmap

- [ ] Block reverse when the lidar sees something behind the car
- [ ] Log CAN traffic on the Pi for replay and tuning
- [ ] Live dashboard (speed, battery, lidar view) served from the Pi
