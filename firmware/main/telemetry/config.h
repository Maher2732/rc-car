// ========================================
// TELEMETRY NODE CONFIGURATION
// ========================================

#pragma once

#include "sdkconfig.h"


// ---------- Pins ----------

#define PIN_CAN_TX              CONFIG_CAN_TWAI_TX_GPIO     // set in menuconfig
#define PIN_CAN_RX              CONFIG_CAN_TWAI_RX_GPIO
#define PIN_BATTERY_SENSE       34      // ADC1, input-only pin

// 3.5" ILI9488 display + XPT2046 touch, sharing one SPI bus
#define PIN_SPI_SCK             18
#define PIN_SPI_MOSI            23
#define PIN_SPI_MISO            19      // touch only: the ILI9488 never releases MISO
#define PIN_LCD_CS              13
#define PIN_LCD_DC              21
#define PIN_LCD_RST             22
#define PIN_LCD_BACKLIGHT       32      // drives a P-MOSFET on the mainboard: low = on
#define PIN_TOUCH_CS            14      // held high (touch isn't used yet)
#define PIN_TOUCH_IRQ           35

#define LCD_SPI_HZ              26000000


// ---------- Battery ----------
//
// Pack -> R_TOP -> ADC pin -> R_BOTTOM -> GND
// 100k / 33k turns a 2S pack's 8.4 V into ~2.1 V at the pin.

#define BATTERY_CELLS           2       // LiPo cells in series
#define DIVIDER_R_TOP_OHMS      100000
#define DIVIDER_R_BOTTOM_OHMS   33000

#define CELL_LOW_MV             3500    // warn
#define CELL_CRITICAL_MV        3300    // limit throttle (latched until reboot)
#define CELL_HYSTERESIS_MV      100

// Below this the node is assumed to be on USB power with no pack attached
#define NO_BATTERY_MV           2000


// ---------- Timing ----------

#define LOOP_PERIOD_MS          50      // CAN polling
#define BATTERY_PERIOD_MS       200     // 5 Hz battery message
#define SCREEN_PERIOD_MS        200     // 5 Hz display refresh
