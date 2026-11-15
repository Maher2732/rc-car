// ========================================
// WHEEL SPEED (HALL SENSOR + PCNT)
// ========================================

#pragma once

#include <stdint.h>

void speed_sensor_init(void);

// Call every SPEED_PERIOD_MS. Updates speed from the pulses since the last call.
void speed_sensor_update(void);

uint32_t speed_sensor_mm_per_s(void);
uint32_t speed_sensor_wheel_rpm(void);
uint32_t speed_sensor_distance_m(void);
