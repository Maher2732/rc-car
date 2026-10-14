import pygame
import serial
import time

ESP32_PORT = "COM4"   # change if needed
BAUD_RATE = 115200

LEFT_ANGLE = 100
CENTER_ANGLE = 135
RIGHT_ANGLE = 170

DEADZONE = 0.08

pygame.init()
pygame.joystick.init()

if pygame.joystick.get_count() == 0:
    print("No controller detected")
    exit()

controller = pygame.joystick.Joystick(0)
controller.init()

print("Controller:", controller.get_name())

esp = serial.Serial(
    ESP32_PORT,
    BAUD_RATE,
    timeout=1
)

time.sleep(2)

last_angle = None

while True:

    pygame.event.pump()

    # Left stick X axis
    x = controller.get_axis(0)

    # Deadzone around center
    if abs(x) < DEADZONE:
        x = 0.0

    # Convert -1.0 -> +1.0
    # into 100° -> 170°
    if x < 0:
        angle = CENTER_ANGLE + int(
            x * (CENTER_ANGLE - LEFT_ANGLE)
        )
    else:
        angle = CENTER_ANGLE + int(
            x * (RIGHT_ANGLE - CENTER_ANGLE)
        )

    # Only send when angle changes
    if angle != last_angle:

        message = f"{angle}\n"

        esp.write(message.encode())

        print(
            f"Stick: {x:.2f} | "
            f"Steering angle: {angle}"
        )

        last_angle = angle

    time.sleep(0.02)