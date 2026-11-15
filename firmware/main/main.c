#include "can.h"

void app_main(void)
{
#if defined(CONFIG_BOARD_ROLE_DRIVE)
    drive_node_run();
#elif defined(CONFIG_BOARD_ROLE_TELEMETRY)
    telemetry_node_run();
#elif defined(CONFIG_BOARD_ROLE_CAN_SENDER)
    can_sender_run();
#else
    can_receiver_run();
#endif
}
