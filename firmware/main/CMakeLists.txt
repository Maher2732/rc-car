idf_component_register(
    SRCS "main.c" "servo.c" "can_sender.c" "can_receiver.c"
    INCLUDE_DIRS "."
    REQUIRES esp_driver_ledc esp_driver_uart esp_driver_twai
)
