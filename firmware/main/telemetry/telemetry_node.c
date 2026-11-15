// ========================================
// TELEMETRY NODE
// ========================================
//
// Measures the battery and runs the dashboard display.
//   Sends    0x301  battery          5 Hz   (drive node limits throttle on low battery)
//   Receives 0x200  drive status     -> controller connected?
//            0x100  Pi correction    -> nearest object the lidar sees
//
// Display: 3.5" ILI9488, refreshed at 5 Hz, redrawing only what changed.

#include <stdio.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"

#include "rc_can.h"
#include "rc_can_protocol.h"

#include "battery.h"
#include "can.h"
#include "config.h"
#include "display.h"

static const char *TAG = "telemetry";


// ========================================
// COLOURS + LAYOUT
// ========================================

#define COLOR_BG        0x0B0F14
#define COLOR_LABEL     0x8A96A6
#define COLOR_TEXT      0xF2F5F8
#define COLOR_GOOD      0x3CCB6A
#define COLOR_WARN      0xFFB020
#define COLOR_BAD       0xFF5A4E
#define COLOR_DIM       0x4A5562
#define COLOR_RULE      0x232B35

#define MARGIN          20
#define ROW_CONTROLLER  52
#define ROW_BATTERY     138
#define ROW_NEAREST     236

#define BAR_X           300
#define BAR_W           160
#define BAR_H           40


// ========================================
// LATEST CAN DATA
// ========================================

typedef struct {
    rc_drive_status_t  drive;
    uint32_t           drive_ms;
    bool               drive_seen;

    rc_pi_correction_t pi;
    uint32_t           pi_ms;
    bool               pi_seen;
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
        if (msg.id == RC_CAN_ID_DRIVE_STATUS && msg.len == sizeof(rc_drive_status_t))
        {
            memcpy(&bus->drive, msg.data, sizeof(rc_drive_status_t));
            bus->drive_ms = rc_millis();
            bus->drive_seen = true;
        }
        else if (msg.id == RC_CAN_ID_PI_CORRECTION && msg.len == sizeof(rc_pi_correction_t))
        {
            memcpy(&bus->pi, msg.data, sizeof(rc_pi_correction_t));
            bus->pi_ms = rc_millis();
            bus->pi_seen = true;
        }
    }
}


// ========================================
// SCREEN
// ========================================
//
// Each value remembers what it last drew, so a refresh only touches pixels
// that actually changed (no flicker, little SPI traffic).

typedef struct {
    char     text[24];
    uint32_t color;
    int      width;
} field_t;

static void draw_field(field_t *f, int x, int y, int scale, const char *text, uint32_t color)
{
    if (strcmp(f->text, text) == 0 && f->color == color)
    {
        return;
    }

    int width = display_text_width(text, scale);
    if (width < f->width)
    {
        display_fill(x + width, y, f->width - width, 8 * scale, COLOR_BG);   // erase leftover tail
    }

    display_text(x, y, text, scale, color, COLOR_BG);

    snprintf(f->text, sizeof(f->text), "%s", text);
    f->color = color;
    f->width = width;
}

static void draw_static(void)
{
    display_fill(0, 0, DISPLAY_WIDTH, DISPLAY_HEIGHT, COLOR_BG);
    display_fill(0, 0, DISPLAY_WIDTH, 36, COLOR_RULE);
    display_text(MARGIN, 6, "RC CAR", 3, COLOR_TEXT, COLOR_RULE);

    display_text(MARGIN, ROW_CONTROLLER, "CONTROLLER", 2, COLOR_LABEL, COLOR_BG);
    display_text(MARGIN, ROW_BATTERY, "BATTERY", 2, COLOR_LABEL, COLOR_BG);
    display_text(MARGIN, ROW_NEAREST, "NEAREST OBJECT", 2, COLOR_LABEL, COLOR_BG);

    display_fill(0, ROW_BATTERY - 14, DISPLAY_WIDTH, 2, COLOR_RULE);
    display_fill(0, ROW_NEAREST - 14, DISPLAY_WIDTH, 2, COLOR_RULE);

    // Battery bar frame
    display_fill(BAR_X - 2, ROW_BATTERY + 24 - 2, BAR_W + 4, BAR_H + 4, COLOR_LABEL);
    display_fill(BAR_X, ROW_BATTERY + 24, BAR_W, BAR_H, COLOR_BG);
}

static void draw_battery_bar(int percent, uint32_t color)
{
    static int last_fill = -1;
    static uint32_t last_color;

    int fill = BAR_W * percent / 100;
    if (fill == last_fill && color == last_color)
    {
        return;
    }

    display_fill(BAR_X, ROW_BATTERY + 24, fill, BAR_H, color);
    display_fill(BAR_X + fill, ROW_BATTERY + 24, BAR_W - fill, BAR_H, COLOR_BG);
    last_fill = fill;
    last_color = color;
}

static void update_screen(const bus_state_t *bus, uint32_t now)
{
    static field_t controller, percent, volts, nearest;
    char text[24];


    // ---------- Controller ----------

    if (!is_fresh(bus->drive_seen, bus->drive_ms, now))
    {
        draw_field(&controller, MARGIN, ROW_CONTROLLER + 24, 4, "NO DRIVE NODE", COLOR_WARN);
    }
    else if (bus->drive.flags & RC_DRIVE_FLAG_CONTROLLER)
    {
        draw_field(&controller, MARGIN, ROW_CONTROLLER + 24, 4, "CONNECTED", COLOR_GOOD);
    }
    else
    {
        draw_field(&controller, MARGIN, ROW_CONTROLLER + 24, 4, "NOT CONNECTED", COLOR_BAD);
    }


    // ---------- Battery ----------

    uint32_t mv = battery_voltage_mv();
    uint8_t flags = battery_flags();

    if (mv < NO_BATTERY_MV)
    {
        draw_field(&percent, MARGIN, ROW_BATTERY + 24, 6, "--", COLOR_DIM);
        draw_field(&volts, MARGIN + 6 * 6 * 4 + 12, ROW_BATTERY + 48, 3, "USB", COLOR_DIM);
        draw_battery_bar(0, COLOR_DIM);
    }
    else
    {
        int pct = battery_percent();
        uint32_t color = (flags & RC_BATT_FLAG_CRITICAL) ? COLOR_BAD
                       : (flags & RC_BATT_FLAG_LOW) ? COLOR_WARN
                       : COLOR_GOOD;

        snprintf(text, sizeof(text), "%d%%", pct);
        draw_field(&percent, MARGIN, ROW_BATTERY + 24, 6, text, color);

        snprintf(text, sizeof(text), "%lu.%02luV", (unsigned long)(mv / 1000), (unsigned long)((mv % 1000) / 10));
        draw_field(&volts, MARGIN + 6 * 6 * 4 + 12, ROW_BATTERY + 48, 3, text, COLOR_TEXT);
        draw_battery_bar(pct, color);
    }


    // ---------- Nearest object ----------

    if (!is_fresh(bus->pi_seen, bus->pi_ms, now))
    {
        draw_field(&nearest, MARGIN, ROW_NEAREST + 24, 5, "PI OFFLINE", COLOR_DIM);
    }
    else if (!(bus->pi.flags & RC_CORR_FLAG_LIDAR_OK))
    {
        draw_field(&nearest, MARGIN, ROW_NEAREST + 24, 5, "NO LIDAR", COLOR_WARN);
    }
    else if (bus->pi.nearest_any_mm == RC_NO_OBSTACLE_MM)
    {
        draw_field(&nearest, MARGIN, ROW_NEAREST + 24, 5, "NONE", COLOR_TEXT);
    }
    else
    {
        uint16_t mm = bus->pi.nearest_any_mm;
        bool blocked = bus->pi.flags & RC_CORR_FLAG_BLOCK_FORWARD;
        uint32_t color = blocked || mm < 300 ? COLOR_BAD : mm < 800 ? COLOR_WARN : COLOR_TEXT;

        snprintf(text, sizeof(text), "%u.%02u M%s", mm / 1000, (mm % 1000) / 10, blocked ? "  STOP" : "");
        draw_field(&nearest, MARGIN, ROW_NEAREST + 24, 5, text, color);
    }
}


// ========================================
// MAIN LOOP
// ========================================

static void telemetry_task(void *arg)
{
    bus_state_t bus = {0};
    uint8_t battery_counter = 0;
    uint32_t last_battery_ms = 0;
    uint32_t last_screen_ms = 0;
    uint32_t last_log_ms = 0;

    draw_static();

    TickType_t wake = xTaskGetTickCount();

    while (1)
    {
        vTaskDelayUntil(&wake, pdMS_TO_TICKS(LOOP_PERIOD_MS));

        uint32_t now = rc_millis();
        read_can(&bus);


        // ---------- Battery ----------

        if (now - last_battery_ms >= BATTERY_PERIOD_MS)
        {
            battery_update();

            rc_battery_t battery = {
                .counter = battery_counter++,
                .flags = battery_flags(),
                .voltage_mv = battery_voltage_mv() > 0xFFFF ? 0xFFFF : battery_voltage_mv(),
                .percent = battery_percent(),
                .cells = BATTERY_CELLS,
            };
            rc_can_send(RC_CAN_ID_BATTERY, &battery, sizeof(battery));
            last_battery_ms = now;
        }


        // ---------- Display ----------

        if (now - last_screen_ms >= SCREEN_PERIOD_MS)
        {
            update_screen(&bus, now);
            last_screen_ms = now;
        }


        if (now - last_log_ms >= 1000)
        {
            ESP_LOGI(TAG, "battery %lu mV %u%% | controller %s | nearest %u mm",
                     (unsigned long)battery_voltage_mv(), battery_percent(),
                     (bus.drive.flags & RC_DRIVE_FLAG_CONTROLLER) ? "yes" : "no",
                     bus.pi.nearest_any_mm);
            last_log_ms = now;
        }
    }
}


void telemetry_node_run(void)
{
    battery_init();
    display_init();
    ESP_ERROR_CHECK(rc_can_start(PIN_CAN_TX, PIN_CAN_RX));

    xTaskCreate(telemetry_task, "telemetry", 6144, NULL, 10, NULL);

    ESP_LOGI(TAG, "Telemetry node ready");
}
