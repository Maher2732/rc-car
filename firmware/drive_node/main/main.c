// ========================================
// DRIVE NODE
// ========================================
//
// Owns steering and the motor. Inputs:
//   - Xbox controller over Bluetooth (Bluepad32)
//   - Obstacle corrections from the Raspberry Pi   (CAN 0x100)
//   - Battery state from the telemetry node        (CAN 0x301)
// Outputs:
//   - Steering servo + ESC PWM
//   - Drive status for the rest of the car         (CAN 0x200)

#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"

#include "rc_can.h"
#include "rc_can_protocol.h"

#include "actuators.h"
#include "config.h"
#include "drive_logic.h"
#include "gamepad.h"

static const char *TAG = "drive";


// ========================================
// LATEST CAN DATA
// ========================================

typedef struct {
    rc_pi_correction_t correction;
    uint32_t           correction_ms;
    bool               correction_seen;

    rc_battery_t       battery;
    uint32_t           battery_ms;
    bool               battery_seen;
} bus_state_t;

static bool is_fresh(bool seen, uint32_t stamp_ms, uint32_t now_ms)
{
    return seen && (now_ms - stamp_ms) < RC_CAN_TIMEOUT_MS;
}

static void read_can(bus_state_t *bus)
{
    rc_can_msg_t msg;

    while (rc_can_receive(&msg, 0))
    {
        switch (msg.id)
        {
            case RC_CAN_ID_PI_CORRECTION:
                if (msg.len == sizeof(rc_pi_correction_t))
                {
                    memcpy(&bus->correction, msg.data, sizeof(rc_pi_correction_t));
                    bus->correction_ms = rc_millis();
                    bus->correction_seen = true;
                }
                break;

            case RC_CAN_ID_BATTERY:
                if (msg.len == sizeof(rc_battery_t))
                {
                    memcpy(&bus->battery, msg.data, sizeof(rc_battery_t));
                    bus->battery_ms = rc_millis();
                    bus->battery_seen = true;
                }
                break;

            default:
                break;      // not addressed to this node
        }
    }
}


// ========================================
// THROTTLE RAMP
// ========================================
//
// Limits how fast throttle can increase; decreases (letting off, braking)
// are always immediate.

static float ramp_throttle(float current, float target, float dt_s)
{
    float step = THROTTLE_RAMP_PER_S * dt_s;
    bool speeding_up = (target > 0 && target > current) || (target < 0 && target < current);

    if (!speeding_up)
    {
        return target;
    }
    if (target > current)
    {
        return (target - current > step) ? current + step : target;
    }
    return (current - target > step) ? current - step : target;
}


// ========================================
// CONTROL LOOP (50 Hz)
// ========================================

static void control_task(void *arg)
{
    bus_state_t bus = {0};
    float applied_throttle = 0.0f;
    uint8_t status_counter = 0;
    uint32_t last_status_ms = 0;
    uint32_t start_ms = rc_millis();
    bool was_blocked = false;
    uint8_t last_flags = 0;

    TickType_t wake = xTaskGetTickCount();

    while (1)
    {
        vTaskDelayUntil(&wake, pdMS_TO_TICKS(CONTROL_PERIOD_MS));

        uint32_t now = rc_millis();
        read_can(&bus);

        gamepad_state_t pad;
        gamepad_get(&pad);

        drive_inputs_t in = {
            .controller_connected = pad.connected,
            .steer = pad.steer,
            .throttle = pad.throttle,
            .brake = pad.brake,
            .speed_limit = pad.fast_mode ? SPEED_MODE_FAST : SPEED_MODE_SLOW,
            .trim_deg = pad.trim_deg,
            .pi_alive = is_fresh(bus.correction_seen, bus.correction_ms, now),
            .correction = bus.correction,
            .telemetry_alive = is_fresh(bus.battery_seen, bus.battery_ms, now),
            .battery_flags = bus.battery.flags,
        };

        // Ignore stale battery flags if telemetry went quiet
        if (!in.telemetry_alive)
        {
            in.battery_flags = 0;
        }

        drive_output_t out;
        drive_compute(&in, &out);

        // ESC must see neutral for a while after power-up to arm
        if (now - start_ms < ESC_ARM_MS)
        {
            out.throttle = 0.0f;
            out.flags |= RC_DRIVE_FLAG_FAILSAFE;
        }

        applied_throttle = ramp_throttle(applied_throttle, out.throttle, CONTROL_PERIOD_MS / 1000.0f);

        actuators_set_steering(out.steering_deg);
        actuators_set_throttle(applied_throttle);


        // Buzz the controller when the Pi blocks forward motion
        bool blocked = in.pi_alive && (in.correction.flags & RC_CORR_FLAG_BLOCK_FORWARD) && pad.throttle > 0;
        if (blocked && !was_blocked)
        {
            gamepad_rumble();
        }
        was_blocked = blocked;


        // Log only when something changes, not every frame
        if (out.flags != last_flags)
        {
            ESP_LOGI(TAG, "flags 0x%02x: controller=%d pi=%d correcting=%d failsafe=%d battery_limit=%d",
                     out.flags,
                     !!(out.flags & RC_DRIVE_FLAG_CONTROLLER),
                     !!(out.flags & RC_DRIVE_FLAG_PI_ALIVE),
                     !!(out.flags & RC_DRIVE_FLAG_CORRECTING),
                     !!(out.flags & RC_DRIVE_FLAG_FAILSAFE),
                     !!(out.flags & RC_DRIVE_FLAG_BATTERY_LIMIT));
            last_flags = out.flags;
        }


        if (now - last_status_ms >= STATUS_PERIOD_MS)
        {
            rc_drive_status_t status = {
                .counter = status_counter++,
                .flags = out.flags,
                .steering_deg = (uint16_t)out.steering_deg,
                .throttle_permille = (int16_t)(applied_throttle * 1000.0f),
            };

            rc_can_send(RC_CAN_ID_DRIVE_STATUS, &status, sizeof(status));
            last_status_ms = now;
        }
    }
}


// ========================================
// MAIN
// ========================================

void app_main(void)
{
    actuators_init();
    ESP_ERROR_CHECK(rc_can_start(PIN_CAN_TX, PIN_CAN_RX));

    // Bluetooth runs on core 0, keep the control loop on core 1
    xTaskCreatePinnedToCore(control_task, "control", 4096, NULL, 10, NULL, 1);

    ESP_LOGI(TAG, "Drive node ready");

    gamepad_run();      // Bluetooth event loop, never returns
}
