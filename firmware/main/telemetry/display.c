#include "display.h"

#include <string.h>

#include "driver/gpio.h"
#include "driver/spi_master.h"
#include "esp_err.h"
#include "esp_heap_caps.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "config.h"
#include "font5x7.h"


#define LCD_HOST        SPI3_HOST
#define MAX_SCALE       6
#define CELL_BYTES      ((6 * MAX_SCALE) * (8 * MAX_SCALE) * 3)
#define FILL_PIXELS     1024

static spi_device_handle_t s_lcd;
static uint8_t *s_buf;          // DMA-capable scratch buffer for fills and glyphs


// ========================================
// LOW LEVEL
// ========================================

static void send(bool is_data, const void *data, size_t len)
{
    if (len == 0)
    {
        return;
    }

    gpio_set_level(PIN_LCD_DC, is_data);

    spi_transaction_t t = {
        .length = len * 8,
        .tx_buffer = data,
    };
    ESP_ERROR_CHECK(spi_device_polling_transmit(s_lcd, &t));
}

static void command(uint8_t cmd, const uint8_t *data, size_t len)
{
    send(false, &cmd, 1);
    send(true, data, len);
}

static void set_window(int x0, int y0, int x1, int y1)
{
    uint8_t cols[] = {x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF};
    uint8_t rows[] = {y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF};
    command(0x2A, cols, 4);         // column address set
    command(0x2B, rows, 4);         // page address set
    command(0x2C, NULL, 0);         // memory write
}

// The ILI9488 only accepts 18-bit colour over SPI: one byte each for R, G, B
static void put_pixel(uint8_t *p, uint32_t color)
{
    p[0] = (color >> 16) & 0xFC;
    p[1] = (color >> 8) & 0xFC;
    p[2] = color & 0xFC;
}


// ========================================
// INIT
// ========================================

typedef struct {
    uint8_t cmd;
    uint8_t len;
    uint8_t data[15];
    uint16_t delay_ms;
} init_cmd_t;

static const init_cmd_t INIT_SEQUENCE[] = {
    {0xE0, 15, {0x00, 0x03, 0x09, 0x08, 0x16, 0x0A, 0x3F, 0x78, 0x4C, 0x09, 0x0A, 0x08, 0x16, 0x1A, 0x0F}, 0},
    {0xE1, 15, {0x00, 0x16, 0x19, 0x03, 0x0F, 0x05, 0x32, 0x45, 0x46, 0x04, 0x0E, 0x0D, 0x35, 0x37, 0x0F}, 0},
    {0xC0, 2, {0x17, 0x15}, 0},                 // power control 1
    {0xC1, 1, {0x41}, 0},                       // power control 2
    {0xC5, 3, {0x00, 0x12, 0x80}, 0},           // VCOM
    {0x36, 1, {0x28}, 0},                       // landscape (row/column exchange), BGR
    {0x3A, 1, {0x66}, 0},                       // 18 bits per pixel (SPI only supports this)
    {0xB0, 1, {0x00}, 0},                       // interface mode
    {0xB1, 1, {0xA0}, 0},                       // frame rate 60 Hz
    {0xB4, 1, {0x02}, 0},                       // 2-dot inversion
    {0xB6, 3, {0x02, 0x02, 0x3B}, 0},           // display function control
    {0xB7, 1, {0xC6}, 0},                       // entry mode
    {0xF7, 4, {0xA9, 0x51, 0x2C, 0x82}, 0},     // adjust control 3
    {0x11, 0, {0}, 120},                        // sleep out
    {0x29, 0, {0}, 25},                         // display on
};

void display_init(void)
{
    gpio_config_t outputs = {
        .pin_bit_mask = (1ULL << PIN_LCD_DC) | (1ULL << PIN_LCD_RST) |
                        (1ULL << PIN_LCD_BACKLIGHT) | (1ULL << PIN_TOUCH_CS),
        .mode = GPIO_MODE_OUTPUT,
    };
    ESP_ERROR_CHECK(gpio_config(&outputs));
    gpio_set_level(PIN_TOUCH_CS, 1);            // keep touch off the bus
    display_backlight(false);

    spi_bus_config_t bus = {
        .sclk_io_num = PIN_SPI_SCK,
        .mosi_io_num = PIN_SPI_MOSI,
        .miso_io_num = PIN_SPI_MISO,
        .quadwp_io_num = -1,
        .quadhd_io_num = -1,
        .max_transfer_sz = CELL_BYTES,
    };
    ESP_ERROR_CHECK(spi_bus_initialize(LCD_HOST, &bus, SPI_DMA_CH_AUTO));

    spi_device_interface_config_t dev = {
        .clock_speed_hz = LCD_SPI_HZ,
        .mode = 0,
        .spics_io_num = PIN_LCD_CS,
        .queue_size = 1,
    };
    ESP_ERROR_CHECK(spi_bus_add_device(LCD_HOST, &dev, &s_lcd));

    s_buf = heap_caps_malloc(CELL_BYTES, MALLOC_CAP_DMA);
    assert(s_buf != NULL);

    // Hardware reset
    gpio_set_level(PIN_LCD_RST, 0);
    vTaskDelay(pdMS_TO_TICKS(10));
    gpio_set_level(PIN_LCD_RST, 1);
    vTaskDelay(pdMS_TO_TICKS(120));

    for (size_t i = 0; i < sizeof(INIT_SEQUENCE) / sizeof(INIT_SEQUENCE[0]); i++)
    {
        const init_cmd_t *c = &INIT_SEQUENCE[i];
        command(c->cmd, c->data, c->len);
        if (c->delay_ms)
        {
            vTaskDelay(pdMS_TO_TICKS(c->delay_ms));
        }
    }

    display_fill(0, 0, DISPLAY_WIDTH, DISPLAY_HEIGHT, 0x000000);
    display_backlight(true);
}

void display_backlight(bool on)
{
    gpio_set_level(PIN_LCD_BACKLIGHT, on ? 0 : 1);  // P-MOSFET: low = on
}


// ========================================
// DRAWING
// ========================================

void display_fill(int x, int y, int w, int h, uint32_t color)
{
    if (w <= 0 || h <= 0)
    {
        return;
    }

    int pixels_in_buf = CELL_BYTES / 3 < FILL_PIXELS ? CELL_BYTES / 3 : FILL_PIXELS;
    for (int i = 0; i < pixels_in_buf; i++)
    {
        put_pixel(&s_buf[i * 3], color);
    }

    set_window(x, y, x + w - 1, y + h - 1);

    int remaining = w * h;
    while (remaining > 0)
    {
        int n = remaining < pixels_in_buf ? remaining : pixels_in_buf;
        send(true, s_buf, n * 3);
        remaining -= n;
    }
}

int display_text_width(const char *text, int scale)
{
    return (int)strlen(text) * 6 * scale;
}

static void draw_char(int x, int y, char c, int scale, uint32_t fg, uint32_t bg)
{
    const uint8_t *cols = font_glyph(c);
    int w = 6 * scale;
    int h = 8 * scale;

    // Render the whole character cell, then send it in one transfer
    for (int py = 0; py < h; py++)
    {
        int row = py / scale;
        for (int px = 0; px < w; px++)
        {
            int col = px / scale;
            bool on = col < 5 && row < 7 && (cols[col] >> row) & 1;
            put_pixel(&s_buf[(py * w + px) * 3], on ? fg : bg);
        }
    }

    set_window(x, y, x + w - 1, y + h - 1);
    send(true, s_buf, w * h * 3);
}

void display_text(int x, int y, const char *text, int scale, uint32_t fg, uint32_t bg)
{
    if (scale > MAX_SCALE)
    {
        scale = MAX_SCALE;
    }

    for (const char *p = text; *p; p++)
    {
        if (x + 6 * scale > DISPLAY_WIDTH)
        {
            break;
        }
        draw_char(x, y, *p, scale, fg, bg);
        x += 6 * scale;
    }
}
