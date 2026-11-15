#pragma once

#include "sdkconfig.h"

#define CAN_BITRATE 500000

void drive_node_run(void);
void telemetry_node_run(void);
void can_sender_run(void);
void can_receiver_run(void);
