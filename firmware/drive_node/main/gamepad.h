// ========================================
// XBOX CONTROLLER OVER BLUETOOTH (BLUEPAD32)
// ========================================
//
// The controller pairs directly with this ESP32 -- no PC, no USB cable.
//
//   Left stick X     steering
//   Right trigger    throttle
//   Left trigger     brake / reverse
//   Y                toggle slow / fast speed mode
//   D-pad left/right steering trim
//
// Only one controller is accepted at a time.

#pragma once

#include <stdbool.h>

typedef struct {
    bool  connected;
    float steer;            // -1 .. 1, deadzone applied
    float throttle;         // 0 .. 1
    float brake;            // 0 .. 1
    bool  fast_mode;
    int   trim_deg;
} gamepad_state_t;

// Copies the latest controller state (safe from any task).
void gamepad_get(gamepad_state_t *state);

// Short rumble on the connected controller (safe from any task).
void gamepad_rumble(void);

// Starts Bluetooth and runs the Bluepad32 event loop. Never returns,
// so call it last from app_main.
void gamepad_run(void);
