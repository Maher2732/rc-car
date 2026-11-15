// ========================================
// TELEMETRY NODE CONFIGURATION
// ========================================

#pragma once


// ---------- Pins ----------

#define PIN_CAN_TX              21
#define PIN_CAN_RX              22
#define PIN_WHEEL_SENSOR        27      // hall sensor output (open-drain, internal pull-up)
#define PIN_BATTERY_SENSE       34      // ADC1, input-only pin


// ---------- Wheel speed ----------

#define WHEEL_DIAMETER_MM       100     // measure your wheel
#define PULSES_PER_WHEEL_REV    4       // magnets on the wheel/axle
#define SPEED_WINDOW_SAMPLES    5       // speed is averaged over this many samples


// ---------- Battery ----------
//
// Pack -> R_TOP -> ADC pin -> R_BOTTOM -> GND
// 100k / 33k turns a 2S pack's 8.4 V into ~2.1 V at the pin.

#define BATTERY_CELLS           2       // LiPo cells in series
#define DIVIDER_R_TOP_OHMS      100000
#define DIVIDER_R_BOTTOM_OHMS   33000

#define CELL_LOW_MV             3500    // warn
#define CELL_CRITICAL_MV        3300    // limit throttle (latched until reboot)
#define CELL_HYSTERESIS_MV      100

// Below this the node is assumed to be on USB power with no pack attached
#define NO_BATTERY_MV           2000


// ---------- Timing ----------

#define SPEED_PERIOD_MS         50      // 20 Hz
#define BATTERY_PERIOD_MS       200     // 5 Hz
