/* SPDX-License-Identifier: GPL-2.0-or-later */

/*
 * Behavior stubs for simple-timer. This file is owned by you: peakrdl-qemu
 * will not overwrite it once it exists.
 */

#include "qemu/osdep.h"
#include "hw/misc/simple_timer.h"

void simple_timer_behavior_init(SimpleTimerState *s)
{
    /* TODO: implement */
    (void)s;
}

void simple_timer_behavior_reset(SimpleTimerState *s)
{
    /* TODO: implement */
    (void)s;
}

void simple_timer_ctrl_write(SimpleTimerState *s, uint32_t val)
{
    /* TODO: implement */
    (void)s;
    (void)val;
}

void simple_timer_load_write(SimpleTimerState *s, uint32_t val)
{
    /* TODO: implement */
    (void)s;
    (void)val;
}

void simple_timer_status_write(SimpleTimerState *s, uint32_t val)
{
    /* TODO: implement */
    (void)s;
    (void)val;
}

