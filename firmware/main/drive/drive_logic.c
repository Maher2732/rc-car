#include "drive_logic.h"

#include "config.h"


static float minf(float a, float b)
{
    return a < b ? a : b;
}

static int clampi(int value, int low, int high)
{
    if (value < low)
    {
        return low;
    }
    if (value > high)
    {
        return high;
    }
    return value;
}


void drive_compute(const drive_inputs_t *in, drive_output_t *out)
{
    int center = STEER_CENTER_DEG + in->trim_deg;

    out->flags = 0;

    if (in->pi_alive)
    {
        out->flags |= RC_DRIVE_FLAG_PI_ALIVE;
    }
    if (in->telemetry_alive)
    {
        out->flags |= RC_DRIVE_FLAG_TELEMETRY;
    }


    // ---------- Failsafe: no controller, no movement ----------

    if (!in->controller_connected)
    {
        out->steering_deg = clampi(center, STEER_LEFT_DEG, STEER_RIGHT_DEG);
        out->throttle = 0.0f;
        out->flags |= RC_DRIVE_FLAG_FAILSAFE;
        return;
    }

    out->flags |= RC_DRIVE_FLAG_CONTROLLER;


    // ---------- Driver steering ----------

    float half_range = in->steer < 0
        ? (float)(center - STEER_LEFT_DEG)
        : (float)(STEER_RIGHT_DEG - center);

    int steering = center + (int)(in->steer * half_range);


    // ---------- Driver throttle ----------

    float throttle = in->throttle - in->brake;


    // ---------- Forward limit: the strictest rule wins ----------

    float limit = in->speed_limit;
    bool pi_limited = false;

    if (in->pi_alive)
    {
        const rc_pi_correction_t *c = &in->correction;

        if (c->flags & RC_CORR_FLAG_BLOCK_FORWARD)
        {
            limit = 0.0f;
            pi_limited = true;
        }
        else if (c->flags & RC_CORR_FLAG_ACTIVE)
        {
            float pi_limit = c->throttle_limit_pct / 100.0f;
            if (pi_limit < limit)
            {
                limit = pi_limit;
                pi_limited = true;
            }
        }
    }
    else
    {
        // No obstacle detection running: drive more carefully
        limit = minf(limit, PI_LOST_LIMIT);
    }

    if ((in->battery_flags & RC_BATT_FLAG_CRITICAL) && BATTERY_CRITICAL_LIMIT < limit)
    {
        limit = BATTERY_CRITICAL_LIMIT;
        pi_limited = false;
        out->flags |= RC_DRIVE_FLAG_BATTERY_LIMIT;
    }

    if (throttle > limit)
    {
        throttle = limit;

        if (pi_limited)
        {
            out->flags |= RC_DRIVE_FLAG_CORRECTING;
        }
    }

    if (throttle < -MAX_REVERSE)
    {
        throttle = -MAX_REVERSE;
    }


    // ---------- Pi steering correction (forward only) ----------
    //
    // Steering works the other way round in reverse, so the offset only
    // applies while the driver is asking to go forward.

    if (in->pi_alive
        && (in->correction.flags & RC_CORR_FLAG_ACTIVE)
        && in->correction.steer_offset_deg != 0
        && in->throttle > in->brake)
    {
        steering += in->correction.steer_offset_deg;
        out->flags |= RC_DRIVE_FLAG_CORRECTING;
    }

    out->steering_deg = clampi(steering, STEER_LEFT_DEG, STEER_RIGHT_DEG);
    out->throttle = throttle;
}
