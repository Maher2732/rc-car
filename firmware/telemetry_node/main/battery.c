#include "battery.h"

#include <stdbool.h>

#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"
#include "esp_adc/adc_oneshot.h"
#include "esp_err.h"
#include "esp_log.h"

#include "rc_can_protocol.h"

#include "config.h"

static const char *TAG = "battery";


#define SAMPLES_PER_READ    16

// Heavy filtering so motor current spikes don't trip the low-voltage warning.
// At 5 Hz, 0.1 gives a time constant of about 2 seconds.
#define FILTER_ALPHA        0.1f


static adc_oneshot_unit_handle_t s_adc;
static adc_channel_t             s_channel;
static adc_cali_handle_t         s_cali;
static bool                      s_calibrated;

static float    s_filtered_mv;
static uint8_t  s_flags;


// ========================================
// LIPO STATE OF CHARGE (RESTING VOLTAGE PER CELL)
// ========================================

typedef struct {
    uint16_t mv;
    uint8_t  percent;
} soc_point_t;

static const soc_point_t SOC_TABLE[] = {
    {4200, 100}, {4110, 90}, {4020, 80}, {3950, 70}, {3870, 60},
    {3840,  50}, {3800, 40}, {3770, 30}, {3730, 20}, {3690, 10},
    {3610,   5}, {3270,  0},
};

#define SOC_POINTS (sizeof(SOC_TABLE) / sizeof(SOC_TABLE[0]))

static uint8_t cell_mv_to_percent(uint32_t cell_mv)
{
    if (cell_mv >= SOC_TABLE[0].mv)
    {
        return 100;
    }

    for (int i = 1; i < SOC_POINTS; i++)
    {
        if (cell_mv >= SOC_TABLE[i].mv)
        {
            // Linear interpolation between the two neighbouring points
            const soc_point_t *hi = &SOC_TABLE[i - 1];
            const soc_point_t *lo = &SOC_TABLE[i];
            return lo->percent + (cell_mv - lo->mv) * (hi->percent - lo->percent) / (hi->mv - lo->mv);
        }
    }

    return 0;
}


// ========================================
// ADC
// ========================================

void battery_init(void)
{
    adc_unit_t unit;
    ESP_ERROR_CHECK(adc_oneshot_io_to_channel(PIN_BATTERY_SENSE, &unit, &s_channel));

    adc_oneshot_unit_init_cfg_t unit_config = {
        .unit_id = unit,
    };
    ESP_ERROR_CHECK(adc_oneshot_new_unit(&unit_config, &s_adc));

    adc_oneshot_chan_cfg_t channel_config = {
        .atten = ADC_ATTEN_DB_12,           // ~0-3.1 V input range
        .bitwidth = ADC_BITWIDTH_DEFAULT,
    };
    ESP_ERROR_CHECK(adc_oneshot_config_channel(s_adc, s_channel, &channel_config));

    // Factory calibration from eFuse; much more accurate than raw counts
#if ADC_CALI_SCHEME_LINE_FITTING_SUPPORTED
    adc_cali_line_fitting_config_t cali_config = {
        .unit_id = unit,
        .atten = ADC_ATTEN_DB_12,
        .bitwidth = ADC_BITWIDTH_DEFAULT,
    };
    s_calibrated = adc_cali_create_scheme_line_fitting(&cali_config, &s_cali) == ESP_OK;
#elif ADC_CALI_SCHEME_CURVE_FITTING_SUPPORTED
    adc_cali_curve_fitting_config_t cali_config = {
        .unit_id = unit,
        .chan = s_channel,
        .atten = ADC_ATTEN_DB_12,
        .bitwidth = ADC_BITWIDTH_DEFAULT,
    };
    s_calibrated = adc_cali_create_scheme_curve_fitting(&cali_config, &s_cali) == ESP_OK;
#endif

    if (!s_calibrated)
    {
        ESP_LOGW(TAG, "No ADC calibration available, readings will be less accurate");
    }
}

static uint32_t read_pin_mv(void)
{
    int sum = 0;

    for (int i = 0; i < SAMPLES_PER_READ; i++)
    {
        int raw = 0;
        adc_oneshot_read(s_adc, s_channel, &raw);
        sum += raw;
    }

    int raw = sum / SAMPLES_PER_READ;

    if (s_calibrated)
    {
        int mv = 0;
        adc_cali_raw_to_voltage(s_cali, raw, &mv);
        return mv;
    }

    return raw * 3100 / 4095;       // rough fallback
}


// ========================================
// UPDATE
// ========================================

void battery_update(void)
{
    uint32_t pin_mv = read_pin_mv();
    float pack_mv = pin_mv * (float)(DIVIDER_R_TOP_OHMS + DIVIDER_R_BOTTOM_OHMS) / DIVIDER_R_BOTTOM_OHMS;

    if (s_filtered_mv == 0)
    {
        s_filtered_mv = pack_mv;    // first reading: start from the real value
    }
    else
    {
        s_filtered_mv += FILTER_ALPHA * (pack_mv - s_filtered_mv);
    }

    if (s_filtered_mv < NO_BATTERY_MV)
    {
        s_flags = 0;                // bench testing on USB power
        return;
    }

    uint32_t cell_mv = (uint32_t)s_filtered_mv / BATTERY_CELLS;
    uint8_t old_flags = s_flags;

    // Low: with hysteresis so it doesn't flicker around the threshold
    if (cell_mv < CELL_LOW_MV)
    {
        s_flags |= RC_BATT_FLAG_LOW;
    }
    else if (cell_mv > CELL_LOW_MV + CELL_HYSTERESIS_MV)
    {
        s_flags &= ~RC_BATT_FLAG_LOW;
    }

    // Critical: latched. A sagging pack recovers a little when the load drops,
    // which must not re-enable full throttle.
    if (cell_mv < CELL_CRITICAL_MV)
    {
        s_flags |= RC_BATT_FLAG_CRITICAL | RC_BATT_FLAG_LOW;
    }

    if (s_flags != old_flags)
    {
        ESP_LOGW(TAG, "Battery %lu mV (%lu mV/cell): low=%d critical=%d",
                 (unsigned long)s_filtered_mv, (unsigned long)cell_mv,
                 !!(s_flags & RC_BATT_FLAG_LOW), !!(s_flags & RC_BATT_FLAG_CRITICAL));
    }
}


uint32_t battery_voltage_mv(void)
{
    return (uint32_t)s_filtered_mv;
}

uint8_t battery_percent(void)
{
    if (s_filtered_mv < NO_BATTERY_MV)
    {
        return 0;
    }
    return cell_mv_to_percent((uint32_t)s_filtered_mv / BATTERY_CELLS);
}

uint8_t battery_flags(void)
{
    return s_flags;
}
