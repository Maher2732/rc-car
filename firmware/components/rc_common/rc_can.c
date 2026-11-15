#include "rc_can.h"

#include <string.h>

#include "freertos/queue.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_twai.h"
#include "esp_twai_onchip.h"

#include "rc_can_protocol.h"

static const char *TAG = "rc_can";


// ========================================
// SETTINGS
// ========================================

#define TX_QUEUE_DEPTH      8
#define RX_QUEUE_DEPTH      32

// The TWAI driver sends straight from our buffers, so each frame needs storage
// that stays valid until the hardware is done with it.
#define TX_SLOTS            (TX_QUEUE_DEPTH * 2)


typedef struct {
    twai_frame_t  frame;            // must be first: on_tx_done hands this pointer back
    uint8_t       data[8];
    volatile bool busy;
} tx_slot_t;

static twai_node_handle_t s_node;
static QueueHandle_t      s_rx_queue;
static tx_slot_t          s_tx_slots[TX_SLOTS];
static portMUX_TYPE       s_tx_lock = portMUX_INITIALIZER_UNLOCKED;
static volatile bool      s_bus_off;


// ========================================
// DRIVER CALLBACKS (ISR CONTEXT)
// ========================================

static bool on_rx_done(twai_node_handle_t node, const twai_rx_done_event_data_t *edata, void *ctx)
{
    uint8_t buffer[8];
    twai_frame_t frame = {
        .buffer = buffer,
        .buffer_len = sizeof(buffer),
    };

    if (twai_node_receive_from_isr(node, &frame) != ESP_OK || frame.header.ide || frame.header.rtr)
    {
        return false;
    }

    rc_can_msg_t msg = {
        .id = frame.header.id,
        .len = frame.header.dlc > 8 ? 8 : frame.header.dlc,
    };
    memcpy(msg.data, buffer, msg.len);

    BaseType_t woken = pdFALSE;
    xQueueSendFromISR(s_rx_queue, &msg, &woken);   // drops the frame if the queue is full
    return woken == pdTRUE;
}

static bool on_tx_done(twai_node_handle_t node, const twai_tx_done_event_data_t *edata, void *ctx)
{
    tx_slot_t *slot = (tx_slot_t *)edata->done_tx_frame;
    slot->busy = false;
    return false;
}

static bool on_state_change(twai_node_handle_t node, const twai_state_change_event_data_t *edata, void *ctx)
{
    if (edata->new_sta == TWAI_ERROR_BUS_OFF)
    {
        s_bus_off = true;
    }
    return false;
}


// ========================================
// BUS-OFF RECOVERY
// ========================================

// A wiring fault or missing terminator can push the controller into bus-off,
// where it stops sending entirely. Recover automatically instead of staying silent.
static void bus_monitor_task(void *arg)
{
    while (1)
    {
        if (s_bus_off)
        {
            ESP_LOGW(TAG, "Bus-off detected, recovering");
            s_bus_off = false;
            twai_node_recover(s_node);
        }

        vTaskDelay(pdMS_TO_TICKS(100));
    }
}


// ========================================
// PUBLIC API
// ========================================

esp_err_t rc_can_start(gpio_num_t tx_gpio, gpio_num_t rx_gpio)
{
    s_rx_queue = xQueueCreate(RX_QUEUE_DEPTH, sizeof(rc_can_msg_t));
    if (s_rx_queue == NULL)
    {
        return ESP_ERR_NO_MEM;
    }

    twai_onchip_node_config_t config = {
        .io_cfg = {
            .tx = tx_gpio,
            .rx = rx_gpio,
            .quanta_clk_out = GPIO_NUM_NC,
            .bus_off_indicator = GPIO_NUM_NC,
        },
        .bit_timing.bitrate = RC_CAN_BITRATE,
        .fail_retry_cnt = -1,
        .tx_queue_depth = TX_QUEUE_DEPTH,
    };

    esp_err_t err = twai_new_node_onchip(&config, &s_node);
    if (err != ESP_OK)
    {
        return err;
    }

    twai_event_callbacks_t callbacks = {
        .on_rx_done = on_rx_done,
        .on_tx_done = on_tx_done,
        .on_state_change = on_state_change,
    };

    err = twai_node_register_event_callbacks(s_node, &callbacks, NULL);
    if (err != ESP_OK)
    {
        return err;
    }

    err = twai_node_enable(s_node);
    if (err != ESP_OK)
    {
        return err;
    }

    xTaskCreate(bus_monitor_task, "can_monitor", 2048, NULL, 5, NULL);

    ESP_LOGI(TAG, "CAN started at %d bit/s (TX=%d RX=%d)", RC_CAN_BITRATE, tx_gpio, rx_gpio);
    return ESP_OK;
}

esp_err_t rc_can_send(uint32_t id, const void *data, uint8_t len)
{
    if (len > 8)
    {
        return ESP_ERR_INVALID_SIZE;
    }

    // Claim a free slot
    tx_slot_t *slot = NULL;

    taskENTER_CRITICAL(&s_tx_lock);
    for (int i = 0; i < TX_SLOTS; i++)
    {
        if (!s_tx_slots[i].busy)
        {
            slot = &s_tx_slots[i];
            slot->busy = true;
            break;
        }
    }
    taskEXIT_CRITICAL(&s_tx_lock);

    if (slot == NULL)
    {
        return ESP_ERR_TIMEOUT;     // nobody is acknowledging frames; drop this one
    }

    memcpy(slot->data, data, len);
    slot->frame = (twai_frame_t) {
        .header.id = id,
        .header.dlc = len,
        .buffer = slot->data,
        .buffer_len = len,
    };

    esp_err_t err = twai_node_transmit(s_node, &slot->frame, 0);
    if (err != ESP_OK)
    {
        slot->busy = false;
    }
    return err;
}

bool rc_can_receive(rc_can_msg_t *msg, TickType_t timeout)
{
    return xQueueReceive(s_rx_queue, msg, timeout) == pdTRUE;
}

uint32_t rc_millis(void)
{
    return (uint32_t)(esp_timer_get_time() / 1000);
}
