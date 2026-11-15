idf_component_register(
    SRCS
        "main.c"
        "battery.c"
        "speed_sensor.c"
    INCLUDE_DIRS "."
    REQUIRES
        rc_common
        esp_driver_pcnt
        esp_driver_gpio
        esp_adc
)
