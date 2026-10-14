#include <stdio.h>
#include <stdint.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <stdlib.h>
#include "driver/ledc.h"
#include "driver/uart.h"

#include "esp_err.h"


// ========================================
// SERVO SETTINGS
// ========================================

#define SERVO_GPIO         18

#define SERVO_FREQ_HZ      50
#define SERVO_PERIOD_US    20000

// Your servo is 270 degrees
#define SERVO_MIN_PULSE_US 500
#define SERVO_MAX_PULSE_US 2500

#define SERVO_MIN_ANGLE    0
#define SERVO_MAX_ANGLE    270

// Safe steering positions for testing
#define LEFT_ANGLE         100
#define CENTER_ANGLE       135
#define RIGHT_ANGLE        170


// ========================================
// LEDC SETTINGS
// ========================================

#define SERVO_MODE         LEDC_LOW_SPEED_MODE
#define SERVO_TIMER        LEDC_TIMER_0
#define SERVO_CHANNEL      LEDC_CHANNEL_0
#define SERVO_RESOLUTION   LEDC_TIMER_16_BIT
#define SERVO_MAX_DUTY     65535


// ========================================
// UART SETTINGS
// ========================================

#define UART_PORT          UART_NUM_0
#define UART_BAUD_RATE     115200
#define UART_BUFFER_SIZE   1024


// ========================================
// SERVO INITIALIZATION
// ========================================

static void servo_init(void)
{
    ledc_timer_config_t timer = {
        .speed_mode = SERVO_MODE,
        .duty_resolution = SERVO_RESOLUTION,
        .timer_num = SERVO_TIMER,
        .freq_hz = SERVO_FREQ_HZ,
        .clk_cfg = LEDC_AUTO_CLK
    };

    ESP_ERROR_CHECK(
        ledc_timer_config(&timer)
    );


    ledc_channel_config_t channel = {
        .gpio_num = SERVO_GPIO,
        .speed_mode = SERVO_MODE,
        .channel = SERVO_CHANNEL,
        .intr_type = LEDC_INTR_DISABLE,
        .timer_sel = SERVO_TIMER,
        .duty = 0,
        .hpoint = 0
    };

    ESP_ERROR_CHECK(
        ledc_channel_config(&channel)
    );
}


// ========================================
// ANGLE -> MICROSECONDS
// ========================================

static uint32_t angle_to_pulse(int angle)
{
    if (angle < SERVO_MIN_ANGLE)
    {
        angle = SERVO_MIN_ANGLE;
    }

    if (angle > SERVO_MAX_ANGLE)
    {
        angle = SERVO_MAX_ANGLE;
    }


    uint32_t pulse_us =
        SERVO_MIN_PULSE_US +
        (
            (angle *
            (SERVO_MAX_PULSE_US - SERVO_MIN_PULSE_US))
            / SERVO_MAX_ANGLE
        );

    return pulse_us;
}


// ========================================
// SET SERVO PULSE
// ========================================

static void servo_set_pulse(uint32_t pulse_us)
{
    uint32_t duty =
        (pulse_us * SERVO_MAX_DUTY)
        / SERVO_PERIOD_US;

    ESP_ERROR_CHECK(
        ledc_set_duty(
            SERVO_MODE,
            SERVO_CHANNEL,
            duty
        )
    );

    ESP_ERROR_CHECK(
        ledc_update_duty(
            SERVO_MODE,
            SERVO_CHANNEL
        )
    );
}


// ========================================
// SET SERVO ANGLE
// ========================================

static void servo_set_angle(int angle)
{
    uint32_t pulse_us = angle_to_pulse(angle);

    servo_set_pulse(pulse_us);

    printf(
        "Angle: %d degrees | Pulse: %lu us\n",
        angle,
        pulse_us
    );
}


// ========================================
// UART INITIALIZATION
// ========================================

static void uart_init(void)
{
    uart_config_t config = {
        .baud_rate = UART_BAUD_RATE,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT
    };

    ESP_ERROR_CHECK(
        uart_param_config(UART_PORT, &config)
    );

    ESP_ERROR_CHECK(
        uart_driver_install(
            UART_PORT,
            UART_BUFFER_SIZE,
            0,
            0,
            NULL,
            0
        )
    );
}


// ========================================
// MAIN
// ========================================

void servo_run(void)
{
    servo_init();
    uart_init();

    servo_set_angle(135);

    printf("Xbox steering ready\n");

    char buffer[16];

    int index = 0;

    while (1)
    {
        uint8_t character;

        int received = uart_read_bytes(
            UART_PORT,
            &character,
            1,
            portMAX_DELAY
        );

        if (received > 0)
        {
            if (character == '\n')
            {
                buffer[index] = '\0';

                int angle = atoi(buffer);

                if (angle >= 0 && angle <= 270)
                {
                    servo_set_angle(angle);

                    printf(
                        "Steering: %d degrees\n",
                        angle
                    );
                }

                index = 0;
            }
            else
            {
                if (index < sizeof(buffer) - 1)
                {
                    buffer[index] = character;
                    index++;
                }
            }
        }
    }
}