#include "speed_sensor.h"

#include "driver/gpio.h"
#include "driver/pulse_cnt.h"
#include "esp_err.h"

#include "config.h"


#define PCNT_HIGH_LIMIT     30000
#define WHEEL_CIRCUM_MM     (WHEEL_DIAMETER_MM * 3.14159265f)

static pcnt_unit_handle_t s_unit;

// Pulse counts for the last few periods; speed is their average
static int      s_window[SPEED_WINDOW_SAMPLES];
static int      s_window_index;
static int      s_last_total;
static uint32_t s_speed_mm_s;
static uint32_t s_rpm;


void speed_sensor_init(void)
{
    pcnt_unit_config_t unit_config = {
        .low_limit = -1,
        .high_limit = PCNT_HIGH_LIMIT,
        .flags.accum_count = 1,         // keep counting past the hardware limit
    };
    ESP_ERROR_CHECK(pcnt_new_unit(&unit_config, &s_unit));

    // Hall sensors bounce at the edge of the magnet field
    pcnt_glitch_filter_config_t filter = {
        .max_glitch_ns = 1000,
    };
    ESP_ERROR_CHECK(pcnt_unit_set_glitch_filter(s_unit, &filter));

    pcnt_chan_config_t channel_config = {
        .edge_gpio_num = PIN_WHEEL_SENSOR,
        .level_gpio_num = -1,
    };
    pcnt_channel_handle_t channel;
    ESP_ERROR_CHECK(pcnt_new_channel(s_unit, &channel_config, &channel));

    // Count each magnet once: falling edge as it arrives, ignore rising edge
    ESP_ERROR_CHECK(pcnt_channel_set_edge_action(
        channel,
        PCNT_CHANNEL_EDGE_ACTION_HOLD,
        PCNT_CHANNEL_EDGE_ACTION_INCREASE));

    // accum_count needs a watch point at the limit to know when it overflowed
    ESP_ERROR_CHECK(pcnt_unit_add_watch_point(s_unit, PCNT_HIGH_LIMIT));

    ESP_ERROR_CHECK(gpio_pullup_en(PIN_WHEEL_SENSOR));

    ESP_ERROR_CHECK(pcnt_unit_enable(s_unit));
    ESP_ERROR_CHECK(pcnt_unit_clear_count(s_unit));
    ESP_ERROR_CHECK(pcnt_unit_start(s_unit));
}


void speed_sensor_update(void)
{
    int total = 0;
    pcnt_unit_get_count(s_unit, &total);

    // Reading a running total (instead of read + clear) never loses pulses
    s_window[s_window_index] = total - s_last_total;
    s_window_index = (s_window_index + 1) % SPEED_WINDOW_SAMPLES;
    s_last_total = total;

    int pulses = 0;
    for (int i = 0; i < SPEED_WINDOW_SAMPLES; i++)
    {
        pulses += s_window[i];
    }

    float window_s = SPEED_WINDOW_SAMPLES * SPEED_PERIOD_MS / 1000.0f;
    float revs_per_s = (pulses / (float)PULSES_PER_WHEEL_REV) / window_s;

    s_speed_mm_s = (uint32_t)(revs_per_s * WHEEL_CIRCUM_MM);
    s_rpm = (uint32_t)(revs_per_s * 60.0f);
}


uint32_t speed_sensor_mm_per_s(void)
{
    return s_speed_mm_s;
}

uint32_t speed_sensor_wheel_rpm(void)
{
    return s_rpm;
}

uint32_t speed_sensor_distance_m(void)
{
    float revs = s_last_total / (float)PULSES_PER_WHEEL_REV;
    return (uint32_t)(revs * WHEEL_CIRCUM_MM / 1000.0f);
}
