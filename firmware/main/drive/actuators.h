// ========================================
// STEERING SERVO + ESC (LEDC PWM)
// ========================================

#pragma once

void actuators_init(void);

// Clamped to the steering limits in config.h
void actuators_set_steering(int angle_deg);

// -1.0 full reverse .. 0 neutral .. 1.0 full forward
void actuators_set_throttle(float throttle);
