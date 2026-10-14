#include "can.h"

void app_main(void)
{
#if defined(CONFIG_BOARD_ROLE_SERVO)
    servo_run();
#elif defined(CONFIG_BOARD_ROLE_CAN_SENDER)
    can_sender_run();
#else
    can_receiver_run();
#endif
}
