// ========================================
// DRIVE LOGIC
// ========================================
//
// Pure function: driver input + Pi correction + battery state -> servo/ESC command.
// No hardware access, so the rules are easy to read and reason about in one place.

#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "rc_can_protocol.h"

typedef struct {
    bool  controller_connected;
    float steer;                    // -1 full left .. +1 full right (deadzone applied)
    float throttle;                 // 0 .. 1, right trigger
    float brake;                    // 0 .. 1, left trigger (brake / reverse)
    float speed_limit;              // current speed mode, 0 .. 1
    int   trim_deg;

    bool  pi_alive;
    rc_pi_correction_t correction;

    bool  telemetry_alive;
    uint8_t battery_flags;          // RC_BATT_FLAG_*
} drive_inputs_t;

typedef struct {
    int     steering_deg;
    float   throttle;               // -1 .. 1, before ramping
    uint8_t flags;                  // RC_DRIVE_FLAG_*
} drive_output_t;

void drive_compute(const drive_inputs_t *in, drive_output_t *out);
