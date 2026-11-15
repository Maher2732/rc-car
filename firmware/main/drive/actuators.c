#include "actuators.h"

#include <stdint.h>

#include "driver/ledc.h"
#include "esp_err.h"

#include "config.h"


// ========================================
// LEDC SETTINGS
// ========================================
//
// Servo and ESC share one 50 Hz timer, each on its own channel.

#define PWM_MODE            LEDC_LOW_SPEED_MODE
#define PWM_TIMER           LEDC_TIMER_0
#define PWM_RESOLUTION      LEDC_TIMER_16_BIT
#define PWM_FREQ_HZ         50
#define PWM_PERIOD_US       20000
#define PWM_TICKS           (1 << 16)

#define SERVO_CHANNEL       LEDC_CHANNEL_0
#define ESC_CHANNEL         LEDC_CHANNEL_1


static void set_pulse(ledc_channel_t channel, uint32_t pulse_us)
{
    uint32_t duty = (pulse_us * PWM_TICKS) / PWM_PERIOD_US;

    ESP_ERROR_CHECK(ledc_set_duty(PWM_MODE, channel, duty));
    ESP_ERROR_CHECK(ledc_update_duty(PWM_MODE, channel));
}

static void channel_init(ledc_channel_t channel, int gpio)
{
    ledc_channel_config_t config = {
        .gpio_num = gpio,
        .speed_mode = PWM_MODE,
        .channel = channel,
        .intr_type = LEDC_INTR_DISABLE,
        .timer_sel = PWM_TIMER,
        .duty = 0,
        .hpoint = 0,
    };

    ESP_ERROR_CHECK(ledc_channel_config(&config));
}


void actuators_init(void)
{
    ledc_timer_config_t timer = {
        .speed_mode = PWM_MODE,
        .duty_resolution = PWM_RESOLUTION,
        .timer_num = PWM_TIMER,
        .freq_hz = PWM_FREQ_HZ,
        .clk_cfg = LEDC_AUTO_CLK,
    };

    ESP_ERROR_CHECK(ledc_timer_config(&timer));

    channel_init(SERVO_CHANNEL, PIN_SERVO);
    channel_init(ESC_CHANNEL, PIN_ESC);

    // Safe outputs before anything else runs
    actuators_set_steering(STEER_CENTER_DEG);
    actuators_set_throttle(0.0f);
}


void actuators_set_steering(int angle_deg)
{
    if (angle_deg < STEER_LEFT_DEG)
    {
        angle_deg = STEER_LEFT_DEG;
    }
    if (angle_deg > STEER_RIGHT_DEG)
    {
        angle_deg = STEER_RIGHT_DEG;
    }

    uint32_t pulse_us =
        SERVO_MIN_PULSE_US +
        (angle_deg * (SERVO_MAX_PULSE_US - SERVO_MIN_PULSE_US)) / SERVO_MAX_ANGLE;

    set_pulse(SERVO_CHANNEL, pulse_us);
}


void actuators_set_throttle(float throttle)
{
    if (throttle > 1.0f)
    {
        throttle = 1.0f;
    }
    if (throttle < -1.0f)
    {
        throttle = -1.0f;
    }

    float half_range = throttle >= 0
        ? (float)(ESC_MAX_PULSE_US - ESC_NEUTRAL_PULSE_US)
        : (float)(ESC_NEUTRAL_PULSE_US - ESC_MIN_PULSE_US);

    uint32_t pulse_us = (uint32_t)(ESC_NEUTRAL_PULSE_US + throttle * half_range);

    set_pulse(ESC_CHANNEL, pulse_us);
}
