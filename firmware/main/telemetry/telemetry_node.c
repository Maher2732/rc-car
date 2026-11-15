// ========================================
// TELEMETRY NODE
// ========================================
//
// Measures wheel speed and battery state and broadcasts them on CAN:
//   0x300  wheel speed   20 Hz   (used by the Pi for stopping distance)
//   0x301  battery        5 Hz   (used by the drive node to limit throttle)

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"

#include "rc_can.h"
#include "rc_can_protocol.h"

#include "battery.h"
#include "config.h"
#include "speed_sensor.h"
#include "can.h"

static const char *TAG = "telemetry";


static uint16_t clamp_u16(uint32_t value)
{
    return value > 0xFFFF ? 0xFFFF : (uint16_t)value;
}


static void telemetry_task(void *arg)
{
    uint8_t speed_counter = 0;
    uint8_t battery_counter = 0;
    uint32_t last_battery_ms = 0;

    TickType_t wake = xTaskGetTickCount();

    while (1)
    {
        vTaskDelayUntil(&wake, pdMS_TO_TICKS(SPEED_PERIOD_MS));

        uint32_t now = rc_millis();


        // ---------- Speed ----------

        speed_sensor_update();

        rc_speed_t speed = {
            .counter = speed_counter++,
            .speed_mm_s = clamp_u16(speed_sensor_mm_per_s()),
            .wheel_rpm = clamp_u16(speed_sensor_wheel_rpm()),
            .odometer_m = clamp_u16(speed_sensor_distance_m()),
        };
        rc_can_send(RC_CAN_ID_SPEED, &speed, sizeof(speed));


        // ---------- Battery ----------

        if (now - last_battery_ms >= BATTERY_PERIOD_MS)
        {
            battery_update();

            rc_battery_t battery = {
                .counter = battery_counter++,
                .flags = battery_flags(),
                .voltage_mv = clamp_u16(battery_voltage_mv()),
                .percent = battery_percent(),
                .cells = BATTERY_CELLS,
            };
            rc_can_send(RC_CAN_ID_BATTERY, &battery, sizeof(battery));

            last_battery_ms = now;
        }


        // Human-readable summary once a second
        if (speed.counter % 20 == 0)
        {
            ESP_LOGI(TAG, "speed %u mm/s | %u rpm | %u m | battery %lu mV %u%%",
                     speed.speed_mm_s, speed.wheel_rpm, speed.odometer_m,
                     (unsigned long)battery_voltage_mv(), battery_percent());
        }
    }
}


void telemetry_node_run(void)
{
    speed_sensor_init();
    battery_init();
    ESP_ERROR_CHECK(rc_can_start(PIN_CAN_TX, PIN_CAN_RX));

    xTaskCreate(telemetry_task, "telemetry", 4096, NULL, 10, NULL);

    ESP_LOGI(TAG, "Telemetry node ready");
}
