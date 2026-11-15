#include "gamepad.h"

#include <btstack_port_esp32.h>
#include <btstack_run_loop.h>
#include <btstack_stdio_esp32.h>
#include <uni.h>

#include "freertos/FreeRTOS.h"
#include "sdkconfig.h"

#include "config.h"

#ifndef CONFIG_BLUEPAD32_PLATFORM_CUSTOM
#error "Set CONFIG_BLUEPAD32_PLATFORM_CUSTOM=y (see sdkconfig.defaults)"
#endif


// ========================================
// SHARED STATE
// ========================================
//
// Written from the Bluetooth task, read by the control task.

static gamepad_state_t s_state;
static portMUX_TYPE    s_lock = portMUX_INITIALIZER_UNLOCKED;

// Only touched from the Bluetooth task
static uni_hid_device_t *s_active_device;
static uint16_t          s_prev_buttons;
static uint8_t           s_prev_dpad;


// ========================================
// INPUT SCALING
// ========================================

static float apply_deadzone(float value, float deadzone)
{
    if (value > -deadzone && value < deadzone)
    {
        return 0.0f;
    }

    // Rescale so output still reaches full range just outside the deadzone
    float sign = value < 0 ? -1.0f : 1.0f;
    float scaled = (value * sign - deadzone) / (1.0f - deadzone);
    return sign * (scaled > 1.0f ? 1.0f : scaled);
}

static float stick_to_unit(int32_t axis)
{
    // Bluepad32 axes run -512 .. 511
    return apply_deadzone(axis / 512.0f, STICK_DEADZONE);
}

static float trigger_to_unit(int32_t trigger)
{
    // Bluepad32 triggers run 0 .. 1023
    return apply_deadzone(trigger / 1023.0f, TRIGGER_DEADZONE);
}

static bool pressed(uint32_t now, uint32_t before, uint32_t mask)
{
    return (now & mask) && !(before & mask);
}


// ========================================
// BLUEPAD32 PLATFORM CALLBACKS
// ========================================

static void platform_init(int argc, const char **argv)
{
}

static void platform_on_init_complete(void)
{
    // Keep stored pairing keys so the controller reconnects after a reboot.
    uni_bt_start_scanning_and_autoconnect_unsafe();
    uni_bt_allow_incoming_connections(true);
    logi("drive: Bluetooth ready, hold the Xbox pair button to connect\n");
}

static uni_error_t platform_on_device_discovered(bd_addr_t addr, const char *name, uint16_t cod, uint8_t rssi)
{
    // Ignore keyboards and mice, only gamepads drive the car
    if ((cod & UNI_BT_COD_MAJOR_MASK) == UNI_BT_COD_MAJOR_PERIPHERAL
        && (cod & UNI_BT_COD_MINOR_MASK) & (UNI_BT_COD_MINOR_KEYBOARD | UNI_BT_COD_MINOR_MICE))
    {
        return UNI_ERROR_IGNORE_DEVICE;
    }
    return UNI_ERROR_SUCCESS;
}

static void platform_on_device_connected(uni_hid_device_t *d)
{
    logi("drive: controller connecting\n");
}

static void platform_on_device_disconnected(uni_hid_device_t *d)
{
    if (d != s_active_device)
    {
        return;
    }

    s_active_device = NULL;

    taskENTER_CRITICAL(&s_lock);
    s_state.connected = false;
    s_state.steer = 0;
    s_state.throttle = 0;
    s_state.brake = 0;
    taskEXIT_CRITICAL(&s_lock);

    logi("drive: controller disconnected -> failsafe\n");
}

static uni_error_t platform_on_device_ready(uni_hid_device_t *d)
{
    if (s_active_device != NULL && s_active_device != d)
    {
        logi("drive: a controller is already connected, rejecting second one\n");
        return UNI_ERROR_INVALID_DEVICE;
    }

    s_active_device = d;
    s_prev_buttons = 0;
    s_prev_dpad = 0;

    taskENTER_CRITICAL(&s_lock);
    s_state.connected = true;
    taskEXIT_CRITICAL(&s_lock);

    if (d->report_parser.play_dual_rumble != NULL)
    {
        d->report_parser.play_dual_rumble(d, 0, 150, 128, 40);
    }

    logi("drive: controller ready\n");
    return UNI_ERROR_SUCCESS;
}

static void platform_on_controller_data(uni_hid_device_t *d, uni_controller_t *ctl)
{
    if (d != s_active_device || ctl->klass != UNI_CONTROLLER_CLASS_GAMEPAD)
    {
        return;
    }

    const uni_gamepad_t *gp = &ctl->gamepad;

    bool toggle_speed = pressed(gp->buttons, s_prev_buttons, BUTTON_Y);
    bool trim_left    = pressed(gp->dpad, s_prev_dpad, DPAD_LEFT);
    bool trim_right   = pressed(gp->dpad, s_prev_dpad, DPAD_RIGHT);

    s_prev_buttons = gp->buttons;
    s_prev_dpad = gp->dpad;

    taskENTER_CRITICAL(&s_lock);

    s_state.steer = stick_to_unit(gp->axis_x);
    s_state.throttle = trigger_to_unit(gp->throttle);
    s_state.brake = trigger_to_unit(gp->brake);

    if (toggle_speed)
    {
        s_state.fast_mode = !s_state.fast_mode;
    }
    if (trim_left && s_state.trim_deg > -STEER_TRIM_LIMIT_DEG)
    {
        s_state.trim_deg--;
    }
    if (trim_right && s_state.trim_deg < STEER_TRIM_LIMIT_DEG)
    {
        s_state.trim_deg++;
    }

    bool fast = s_state.fast_mode;
    int trim = s_state.trim_deg;

    taskEXIT_CRITICAL(&s_lock);

    if (toggle_speed)
    {
        logi("drive: speed mode %s\n", fast ? "FAST" : "SLOW");
    }
    if (trim_left || trim_right)
    {
        logi("drive: steering trim %d deg\n", trim);
    }
}

static const uni_property_t *platform_get_property(uni_property_idx_t idx)
{
    return NULL;
}

static void platform_on_oob_event(uni_platform_oob_event_t event, void *data)
{
}

static struct uni_platform s_platform = {
    .name = "rc_drive",
    .init = platform_init,
    .on_init_complete = platform_on_init_complete,
    .on_device_discovered = platform_on_device_discovered,
    .on_device_connected = platform_on_device_connected,
    .on_device_disconnected = platform_on_device_disconnected,
    .on_device_ready = platform_on_device_ready,
    .on_oob_event = platform_on_oob_event,
    .on_controller_data = platform_on_controller_data,
    .get_property = platform_get_property,
};


// ========================================
// RUMBLE (RUNS ON THE BLUETOOTH TASK)
// ========================================

static volatile bool s_rumble_pending;

static void rumble_on_bt_task(void *context)
{
    s_rumble_pending = false;

    uni_hid_device_t *d = s_active_device;
    if (d != NULL && d->report_parser.play_dual_rumble != NULL)
    {
        d->report_parser.play_dual_rumble(d, 0, 200, 0, 255);
    }
}

static btstack_context_callback_registration_t s_rumble_callback = {
    .callback = rumble_on_bt_task,
};


// ========================================
// PUBLIC API
// ========================================

void gamepad_get(gamepad_state_t *state)
{
    taskENTER_CRITICAL(&s_lock);
    *state = s_state;
    taskEXIT_CRITICAL(&s_lock);
}

void gamepad_rumble(void)
{
    // BTstack is single-threaded; hand the work to its task.
    // Registering the same callback twice before it runs would corrupt its queue.
    if (!s_rumble_pending)
    {
        s_rumble_pending = true;
        btstack_run_loop_execute_on_main_thread(&s_rumble_callback);
    }
}

void gamepad_run(void)
{
#if defined(CONFIG_ESP_CONSOLE_UART) && !defined(CONFIG_BLUEPAD32_USB_CONSOLE_ENABLE)
    btstack_stdio_init();
#endif

    btstack_init();
    uni_platform_set_custom(&s_platform);
    uni_init(0, NULL);

    btstack_run_loop_execute();     // does not return
}
