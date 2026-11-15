idf_component_register(
    SRCS
        "main.c"
        "actuators.c"
        "drive_logic.c"
        "gamepad.c"
    INCLUDE_DIRS "."
    REQUIRES
        rc_common
        esp_driver_ledc
        bluepad32
        btstack
)
