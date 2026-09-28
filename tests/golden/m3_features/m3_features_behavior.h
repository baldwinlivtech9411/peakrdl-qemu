#ifndef M3_FEATURES_BEHAVIOR_H
#define M3_FEATURES_BEHAVIOR_H

/* SPDX-License-Identifier: GPL-2.0-or-later */

/*
 * Behavior state for m3-features. This file is owned by you: peakrdl-qemu
 * will not overwrite it once it exists.
 *
 * To migrate extra state, define M3_FEATURES_BEHAVIOR_HAS_VMSTATE and
 * provide a VMStateDescription named vmstate_m3_features_behavior.
 */

typedef struct M3FeaturesBehavior {
    /* user fields */
    int _unused;
} M3FeaturesBehavior;

#endif /* M3_FEATURES_BEHAVIOR_H */
