idf_component_register(
    SRCS "Servo_Main.c"
    INCLUDE_DIRS "."
    REQUIRES 
        esp_driver_ledc
        esp_driver_uart
)