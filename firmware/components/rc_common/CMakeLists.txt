idf_component_register(
    SRCS "rc_can.c"
    INCLUDE_DIRS "include"
    REQUIRES
        esp_driver_twai
        esp_driver_gpio
        esp_timer
)
