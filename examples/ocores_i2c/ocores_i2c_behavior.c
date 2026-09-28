/* SPDX-License-Identifier: GPL-2.0-or-later */

/*
 * OpenCores I2C master behavior.
 *
 * Mirrors the Wishbone I2C-Master Core command/status protocol used by
 * Linux drivers/i2c/busses/i2c-ocores.c. Transfers complete immediately
 * (QEMU I2C is synchronous), so TIP is always left clear.
 */

#include "qemu/osdep.h"
#include "hw/i2c/i2c.h"
#include "hw/irq.h"
#include "hw/i2c/ocores_i2c.h"

static void ocores_update_irq(OcoresI2cState *s)
{
    int level = FIELD_EX32(s->regs[R_CTR], CTR, IEN) &&
                FIELD_EX32(s->shadow_sr, SR, IF);

    qemu_set_irq(s->irq[0], level);
}

static void ocores_set_if(OcoresI2cState *s)
{
    s->shadow_sr = FIELD_DP32(s->shadow_sr, SR, IF, 1);
    s->shadow_sr = FIELD_DP32(s->shadow_sr, SR, TIP, 0);
    ocores_update_irq(s);
}

void ocores_i2c_behavior_init(OcoresI2cState *s)
{
    s->bh.bus = i2c_init_bus(DEVICE(s), "i2c");
}

void ocores_i2c_behavior_reset(OcoresI2cState *s)
{
    if (s->bh.bus) {
        i2c_end_transfer(s->bh.bus);
    }
    s->shadow_rxr = 0;
    s->shadow_sr = 0;
    qemu_set_irq(s->irq[0], 0);
}

void ocores_i2c_ctr_write(OcoresI2cState *s, uint32_t val)
{
    if (!FIELD_EX32(val, CTR, EN) && s->bh.bus) {
        i2c_end_transfer(s->bh.bus);
        s->shadow_sr = FIELD_DP32(s->shadow_sr, SR, BUSY, 0);
        s->shadow_sr = FIELD_DP32(s->shadow_sr, SR, TIP, 0);
    }
    ocores_update_irq(s);
}

void ocores_i2c_cr_write(OcoresI2cState *s, uint32_t val)
{
    I2CBus *bus = s->bh.bus;
    uint8_t data = FIELD_EX32(s->regs[R_TXR], TXR, DATA);
    int nack;

    if (FIELD_EX32(val, CR, IACK)) {
        s->shadow_sr = FIELD_DP32(s->shadow_sr, SR, IF, 0);
        ocores_update_irq(s);
    }

    if (!FIELD_EX32(s->regs[R_CTR], CTR, EN) || bus == NULL) {
        return;
    }

    if (FIELD_EX32(val, CR, STA)) {
        /*
         * TXR holds the 8-bit address byte: [7:1] slave, [0] R/W.
         * i2c_start_transfer: 0 = ACK (device present), -1 = NACK.
         */
        nack = i2c_start_transfer(bus, data >> 1, data & 1);
        s->shadow_sr = FIELD_DP32(s->shadow_sr, SR, RXACK, nack ? 1 : 0);
        s->shadow_sr = FIELD_DP32(s->shadow_sr, SR, AL, 0);
        s->shadow_sr = FIELD_DP32(s->shadow_sr, SR, BUSY, 1);
        ocores_set_if(s);
        return;
    }

    if (FIELD_EX32(val, CR, WR)) {
        nack = i2c_send(bus, data);
        s->shadow_sr = FIELD_DP32(s->shadow_sr, SR, RXACK, nack ? 1 : 0);
        s->shadow_sr = FIELD_DP32(s->shadow_sr, SR, AL, 0);
        s->shadow_sr = FIELD_DP32(s->shadow_sr, SR, BUSY, 1);
        ocores_set_if(s);
        return;
    }

    if (FIELD_EX32(val, CR, RD)) {
        uint8_t rx = i2c_recv(bus);

        /* ACK=1 means NACK the slave (last byte of a read). */
        if (FIELD_EX32(val, CR, ACK)) {
            i2c_nack(bus);
        }
        s->shadow_rxr = FIELD_DP32(s->shadow_rxr, RXR, DATA, rx);
        s->shadow_sr = FIELD_DP32(s->shadow_sr, SR, RXACK, 0);
        s->shadow_sr = FIELD_DP32(s->shadow_sr, SR, AL, 0);
        s->shadow_sr = FIELD_DP32(s->shadow_sr, SR, BUSY, 1);
        ocores_set_if(s);
        return;
    }

    if (FIELD_EX32(val, CR, STO)) {
        i2c_end_transfer(bus);
        s->shadow_sr = FIELD_DP32(s->shadow_sr, SR, BUSY, 0);
        s->shadow_sr = FIELD_DP32(s->shadow_sr, SR, TIP, 0);
        s->shadow_sr = FIELD_DP32(s->shadow_sr, SR, AL, 0);
        ocores_set_if(s);
    }
}
