// ========================================
// RC CAR CAN PROTOCOL
// ========================================
//
// Shared by every node on the bus. The Raspberry Pi mirrors these
// definitions in pi/rc_pi/protocol.py -- keep both in sync
// (pi/tests/test_protocol.py checks the IDs and sizes).
//
// Bus: classic CAN, 500 kbit/s, 11-bit standard IDs, little-endian payloads.
// Lower ID = higher priority on the bus.
//
//   ID     Sender      Receiver(s)   Rate    Message
//   0x100  Pi          Drive node    20 Hz   Obstacle correction
//   0x200  Drive node  all           20 Hz   Drive status
//   0x300  Telemetry   all           20 Hz   Wheel speed
//   0x301  Telemetry   all           5 Hz    Battery

#pragma once

#include <stdint.h>

#define RC_CAN_BITRATE              500000

#define RC_CAN_ID_PI_CORRECTION     0x100
#define RC_CAN_ID_DRIVE_STATUS      0x200
#define RC_CAN_ID_SPEED             0x300
#define RC_CAN_ID_BATTERY           0x301

// A node is considered offline when its messages stop for this long
#define RC_CAN_TIMEOUT_MS           300


// ========================================
// 0x100  PI -> DRIVE NODE: OBSTACLE CORRECTION
// ========================================

#define RC_CORR_FLAG_ACTIVE         (1 << 0)    // apply steer offset / throttle limit
#define RC_CORR_FLAG_BLOCK_FORWARD  (1 << 1)    // obstacle too close: no forward throttle
#define RC_CORR_FLAG_LIDAR_OK       (1 << 2)    // lidar is producing fresh scans

#define RC_NO_OBSTACLE_MM           0xFFFF

typedef struct __attribute__((packed)) {
    uint8_t  counter;               // increments every frame (heartbeat)
    uint8_t  flags;                 // RC_CORR_FLAG_*
    int8_t   steer_offset_deg;      // added to steering, positive = right
    uint8_t  throttle_limit_pct;    // max forward throttle, 0-100
    uint16_t nearest_obstacle_mm;   // closest object in the car's path
} rc_pi_correction_t;


// ========================================
// 0x200  DRIVE NODE -> ALL: STATUS
// ========================================

#define RC_DRIVE_FLAG_CONTROLLER    (1 << 0)    // Xbox controller connected
#define RC_DRIVE_FLAG_PI_ALIVE      (1 << 1)    // corrections arriving from the Pi
#define RC_DRIVE_FLAG_CORRECTING    (1 << 2)    // a Pi correction changed the output
#define RC_DRIVE_FLAG_FAILSAFE      (1 << 3)    // outputs forced to neutral
#define RC_DRIVE_FLAG_BATTERY_LIMIT (1 << 4)    // throttle reduced for low battery
#define RC_DRIVE_FLAG_TELEMETRY     (1 << 5)    // telemetry node alive

typedef struct __attribute__((packed)) {
    uint8_t  counter;
    uint8_t  flags;                 // RC_DRIVE_FLAG_*
    uint16_t steering_deg;          // servo angle actually commanded
    int16_t  throttle_permille;     // ESC command, -1000 (reverse) .. 1000
} rc_drive_status_t;


// ========================================
// 0x300  TELEMETRY -> ALL: WHEEL SPEED
// ========================================

typedef struct __attribute__((packed)) {
    uint8_t  counter;
    uint8_t  reserved;
    uint16_t speed_mm_s;
    uint16_t wheel_rpm;
    uint16_t odometer_m;            // distance since power-on
} rc_speed_t;


// ========================================
// 0x301  TELEMETRY -> ALL: BATTERY
// ========================================

#define RC_BATT_FLAG_LOW            (1 << 0)
#define RC_BATT_FLAG_CRITICAL       (1 << 1)

typedef struct __attribute__((packed)) {
    uint8_t  counter;
    uint8_t  flags;                 // RC_BATT_FLAG_*
    uint16_t voltage_mv;            // pack voltage
    uint8_t  percent;               // estimated state of charge
    uint8_t  cells;                 // configured series cell count
} rc_battery_t;


_Static_assert(sizeof(rc_pi_correction_t) == 6, "correction must be 6 bytes");
_Static_assert(sizeof(rc_drive_status_t) == 6, "drive status must be 6 bytes");
_Static_assert(sizeof(rc_speed_t) == 8, "speed must be 8 bytes");
_Static_assert(sizeof(rc_battery_t) == 6, "battery must be 6 bytes");
