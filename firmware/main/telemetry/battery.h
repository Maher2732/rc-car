// ========================================
// BATTERY MONITOR (ADC + VOLTAGE DIVIDER)
// ========================================

#pragma once

#include <stdint.h>

void battery_init(void);

// Call every BATTERY_PERIOD_MS. Samples, filters and updates the flags.
void battery_update(void);

uint32_t battery_voltage_mv(void);
uint8_t  battery_percent(void);
uint8_t  battery_flags(void);       // RC_BATT_FLAG_*
