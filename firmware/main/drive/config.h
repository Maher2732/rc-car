// ========================================
// DRIVE NODE CONFIGURATION
// ========================================
//
// Everything you might need to tune for your car lives here.

#pragma once

#include "sdkconfig.h"


// ---------- Pins ----------

#define PIN_SERVO               18
#define PIN_MOTOR_RPWM          25      // BTS7960 RPWM: forward
#define PIN_MOTOR_LPWM          26      // BTS7960 LPWM: reverse
#define PIN_MOTOR_EN            33      // BTS7960 R_EN + L_EN tied together
#define PIN_CAN_TX              CONFIG_CAN_TWAI_TX_GPIO     // set in menuconfig
#define PIN_CAN_RX              CONFIG_CAN_TWAI_RX_GPIO


// ---------- Steering servo (270 degree) ----------

#define SERVO_MIN_PULSE_US      500
#define SERVO_MAX_PULSE_US      2500
#define SERVO_MAX_ANGLE         270

// Mechanical steering limits -- never command past these
#define STEER_LEFT_DEG          100
#define STEER_CENTER_DEG        135
#define STEER_RIGHT_DEG         170

#define STEER_TRIM_LIMIT_DEG    10      // max D-pad trim either way


// ---------- Motor (BTS7960 H-bridge, brushed 540) ----------

#define MOTOR_PWM_FREQ_HZ       20000   // above hearing range, no motor whine

// Changing direction while the motor still spins makes a big current spike
// (plugging). Brake for this long before reversing.
#define MOTOR_REVERSE_DELAY_MS  250

// What the motor does at zero throttle: 1 = brake (crawler style, holds on
// slopes and stops quickly when the Pi cuts throttle), 0 = coast
#define MOTOR_DRAG_BRAKE        1


// ---------- Controller ----------

#define STICK_DEADZONE          0.08f
#define TRIGGER_DEADZONE        0.05f


// ---------- Speed limits (fraction of full throttle) ----------

#define SPEED_MODE_SLOW         0.40f   // default after boot; Y toggles
#define SPEED_MODE_FAST         1.00f
#define MAX_REVERSE             0.50f

// Throttle may rise this much per second; drops are instant.
// Protects the 3D-printed drivetrain from shock loads.
#define THROTTLE_RAMP_PER_S     3.0f

// Applied when the Pi stops sending corrections (crashed, unplugged, booting)
#define PI_LOST_LIMIT           0.50f

// Applied when the telemetry node reports a critically low battery
#define BATTERY_CRITICAL_LIMIT  0.30f


// ---------- Timing ----------

#define CONTROL_PERIOD_MS       20      // 50 Hz, matches the servo frame rate
#define STATUS_PERIOD_MS        50      // 20 Hz drive status on CAN
