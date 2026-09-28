#ifndef SIMPLE_TIMER_BEHAVIOR_H
#define SIMPLE_TIMER_BEHAVIOR_H

/* SPDX-License-Identifier: GPL-2.0-or-later */

/*
 * Behavior state for simple-timer. This file is owned by you: peakrdl-qemu
 * will not overwrite it once it exists.
 *
 * To migrate extra state, define SIMPLE_TIMER_BEHAVIOR_HAS_VMSTATE and
 * provide a VMStateDescription named vmstate_simple_timer_behavior.
 */

typedef struct SimpleTimerBehavior {
    /* user fields */
    int _unused;
} SimpleTimerBehavior;

#endif /* SIMPLE_TIMER_BEHAVIOR_H */
