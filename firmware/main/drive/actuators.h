// ========================================
// STEERING SERVO + MOTOR (BTS7960)
// ========================================

#pragma once

void actuators_init(void);

// Clamped to the steering limits in config.h
void actuators_set_steering(int angle_deg);

// -1.0 full reverse .. 0 stop .. 1.0 full forward
void actuators_set_throttle(float throttle);
