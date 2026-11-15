#include "actuators.h"

#include <stdbool.h>
#include <stdint.h>

#include "driver/gpio.h"
#include "driver/ledc.h"
#include "esp_err.h"
#include "esp_timer.h"

#include "config.h"


// ========================================
// LEDC SETTINGS
// ========================================
//
// Servo: 50 Hz, 16-bit (fine pulse-width steps).
// Motor: 20 kHz, 10-bit, one channel per BTS7960 input.

#define PWM_MODE            LEDC_LOW_SPEED_MODE

#define SERVO_TIMER         LEDC_TIMER_0
#define SERVO_CHANNEL       LEDC_CHANNEL_0
#define SERVO_FREQ_HZ       50
#define SERVO_PERIOD_US     20000
#define SERVO_RESOLUTION    LEDC_TIMER_16_BIT
#define SERVO_TICKS         (1 << 16)

#define MOTOR_TIMER         LEDC_TIMER_1
#define MOTOR_FWD_CHANNEL   LEDC_CHANNEL_1      // RPWM
#define MOTOR_REV_CHANNEL   LEDC_CHANNEL_2      // LPWM
#define MOTOR_RESOLUTION    LEDC_TIMER_10_BIT
#define MOTOR_MAX_DUTY      ((1 << 10) - 1)


static void set_duty(ledc_channel_t channel, uint32_t duty)
{
    ESP_ERROR_CHECK(ledc_set_duty(PWM_MODE, channel, duty));
    ESP_ERROR_CHECK(ledc_update_duty(PWM_MODE, channel));
}

static void timer_init(ledc_timer_t timer, uint32_t freq_hz, ledc_timer_bit_t resolution)
{
    ledc_timer_config_t config = {
        .speed_mode = PWM_MODE,
        .duty_resolution = resolution,
        .timer_num = timer,
        .freq_hz = freq_hz,
        .clk_cfg = LEDC_AUTO_CLK,
    };

    ESP_ERROR_CHECK(ledc_timer_config(&config));
}

static void channel_init(ledc_channel_t channel, ledc_timer_t timer, int gpio)
{
    ledc_channel_config_t config = {
        .gpio_num = gpio,
        .speed_mode = PWM_MODE,
        .channel = channel,
        .intr_type = LEDC_INTR_DISABLE,
        .timer_sel = timer,
        .duty = 0,
        .hpoint = 0,
    };

    ESP_ERROR_CHECK(ledc_channel_config(&config));
}


// ========================================
// INIT
// ========================================

void actuators_init(void)
{
    // Keep the H-bridge disabled until both PWM inputs are known to be low
    gpio_config_t enable_pin = {
        .pin_bit_mask = 1ULL << PIN_MOTOR_EN,
        .mode = GPIO_MODE_OUTPUT,
    };
    ESP_ERROR_CHECK(gpio_config(&enable_pin));
    ESP_ERROR_CHECK(gpio_set_level(PIN_MOTOR_EN, 0));

    timer_init(SERVO_TIMER, SERVO_FREQ_HZ, SERVO_RESOLUTION);
    timer_init(MOTOR_TIMER, MOTOR_PWM_FREQ_HZ, MOTOR_RESOLUTION);

    channel_init(SERVO_CHANNEL, SERVO_TIMER, PIN_SERVO);
    channel_init(MOTOR_FWD_CHANNEL, MOTOR_TIMER, PIN_MOTOR_RPWM);
    channel_init(MOTOR_REV_CHANNEL, MOTOR_TIMER, PIN_MOTOR_LPWM);

    actuators_set_steering(STEER_CENTER_DEG);
    actuators_set_throttle(0.0f);

    ESP_ERROR_CHECK(gpio_set_level(PIN_MOTOR_EN, 1));
}


// ========================================
// STEERING
// ========================================

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

    set_duty(SERVO_CHANNEL, (pulse_us * SERVO_TICKS) / SERVO_PERIOD_US);
}


// ========================================
// MOTOR
// ========================================
//
//   RPWM    LPWM    Motor
//   duty    0       forward
//   0       duty    reverse
//   0       0       coast
//   full    full    brake (both terminals tied together)

typedef enum {
    DIR_STOPPED,
    DIR_FORWARD,
    DIR_REVERSE,
} motor_dir_t;

static motor_dir_t s_dir = DIR_STOPPED;
static motor_dir_t s_last_moving = DIR_STOPPED;
static int64_t     s_stopped_since_us;

static void motor_coast(void)
{
    set_duty(MOTOR_FWD_CHANNEL, 0);
    set_duty(MOTOR_REV_CHANNEL, 0);
}

static void motor_brake(void)
{
    set_duty(MOTOR_FWD_CHANNEL, MOTOR_MAX_DUTY);
    set_duty(MOTOR_REV_CHANNEL, MOTOR_MAX_DUTY);
}

static void motor_stop(void)
{
    if (s_dir != DIR_STOPPED)
    {
        s_last_moving = s_dir;
        s_dir = DIR_STOPPED;
        s_stopped_since_us = esp_timer_get_time();
    }

    if (MOTOR_DRAG_BRAKE)
    {
        motor_brake();
    }
    else
    {
        motor_coast();
    }
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

    motor_dir_t wanted = throttle > 0 ? DIR_FORWARD : throttle < 0 ? DIR_REVERSE : DIR_STOPPED;

    if (wanted == DIR_STOPPED)
    {
        motor_stop();
        return;
    }

    // Asked to flip direction: brake first, and only switch once the motor
    // has been stopped for MOTOR_REVERSE_DELAY_MS
    if (s_dir != DIR_STOPPED && s_dir != wanted)
    {
        motor_stop();
    }

    if (s_dir == DIR_STOPPED && s_last_moving != DIR_STOPPED && s_last_moving != wanted)
    {
        int64_t stopped_ms = (esp_timer_get_time() - s_stopped_since_us) / 1000;

        if (stopped_ms < MOTOR_REVERSE_DELAY_MS)
        {
            motor_brake();
            return;
        }
    }

    s_dir = wanted;

    uint32_t duty = (uint32_t)((throttle < 0 ? -throttle : throttle) * MOTOR_MAX_DUTY);

    if (wanted == DIR_FORWARD)
    {
        set_duty(MOTOR_REV_CHANNEL, 0);
        set_duty(MOTOR_FWD_CHANNEL, duty);
    }
    else
    {
        set_duty(MOTOR_FWD_CHANNEL, 0);
        set_duty(MOTOR_REV_CHANNEL, duty);
    }
}
