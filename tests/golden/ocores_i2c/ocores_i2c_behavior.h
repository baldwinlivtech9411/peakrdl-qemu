#ifndef OCORES_I2C_BEHAVIOR_H
#define OCORES_I2C_BEHAVIOR_H

/* SPDX-License-Identifier: GPL-2.0-or-later */

/*
 * Behavior state for ocores-i2c. This file is owned by you: peakrdl-qemu
 * will not overwrite it once it exists.
 *
 * To migrate extra state, define OCORES_I2C_BEHAVIOR_HAS_VMSTATE and
 * provide a VMStateDescription named vmstate_ocores_i2c_behavior.
 */

typedef struct OcoresI2cBehavior {
    /* user fields */
    int _unused;
} OcoresI2cBehavior;

#endif /* OCORES_I2C_BEHAVIOR_H */
