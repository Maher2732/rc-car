// ========================================
// CAN BUS HELPER (ESP32 TWAI)
// ========================================
//
// Thin wrapper over the ESP-IDF TWAI driver that every node uses:
// start the bus, send a payload, receive into a queue.
// Needs an external CAN transceiver (e.g. SN65HVD230) on TX/RX.

#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "freertos/FreeRTOS.h"
#include "driver/gpio.h"
#include "esp_err.h"

typedef struct {
    uint32_t id;
    uint8_t  len;
    uint8_t  data[8];
} rc_can_msg_t;

esp_err_t rc_can_start(gpio_num_t tx_gpio, gpio_num_t rx_gpio);

// Queues a frame without blocking. Returns ESP_ERR_TIMEOUT if the bus is backed up.
esp_err_t rc_can_send(uint32_t id, const void *data, uint8_t len);

// Waits up to `timeout` for the next received frame.
bool rc_can_receive(rc_can_msg_t *msg, TickType_t timeout);

// Milliseconds since boot, used for message timeouts.
uint32_t rc_millis(void);
