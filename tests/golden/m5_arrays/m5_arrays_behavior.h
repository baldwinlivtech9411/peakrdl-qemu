#ifndef M5_ARRAYS_BEHAVIOR_H
#define M5_ARRAYS_BEHAVIOR_H

/* SPDX-License-Identifier: GPL-2.0-or-later */

/*
 * Behavior state for m5-arrays. This file is owned by you: peakrdl-qemu
 * will not overwrite it once it exists.
 *
 * To migrate extra state, define M5_ARRAYS_BEHAVIOR_HAS_VMSTATE and
 * provide a VMStateDescription named vmstate_m5_arrays_behavior.
 */

typedef struct M5ArraysBehavior {
    /* user fields */
    int _unused;
} M5ArraysBehavior;

#endif /* M5_ARRAYS_BEHAVIOR_H */
