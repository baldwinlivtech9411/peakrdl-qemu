/* SPDX-License-Identifier: GPL-2.0-or-later */

/*
 * QTest for the peakrdl-qemu OpenCores I2C master on RISC-V virt.
 *
 * Drives the same command/status protocol as Linux i2c-ocores:
 *   PRELOW/PREHIGH, CONTROL.EN, DATA + CMD_START/WRITE/READ/STOP,
 *   STATUS.IF / RXACK / BUSY. tmp105 is at 0x48.
 */

#include "qemu/osdep.h"
#include "libqtest.h"

#define OC_BASE     0x103000
#define OC_PRERLO   (OC_BASE + 0x00)
#define OC_PRERHI   (OC_BASE + 0x04)
#define OC_CTR      (OC_BASE + 0x08)
#define OC_DATA     (OC_BASE + 0x0c)
#define OC_CR       (OC_BASE + 0x10)
#define OC_SR       (OC_BASE + 0x10)

#define CTR_IEN     0x40
#define CTR_EN      0x80

#define CMD_IACK    0x01
#define CMD_ACK     0x08
#define CMD_WR      0x10
#define CMD_RD      0x20
#define CMD_STO     0x40
#define CMD_STA     0x80

#define STAT_IF     0x01
#define STAT_TIP    0x02
#define STAT_AL     0x20
#define STAT_BUSY   0x40
#define STAT_RXACK  0x80

#define TMP105_ADDR 0x48

static QTestState *oc_boot(void)
{
    QTestState *qts;

    g_assert(qtest_has_machine("virt"));
    qts = qtest_initf("-machine virt");
    return qts;
}

static uint32_t oc_wait_if(QTestState *qts)
{
    uint32_t sr = qtest_readl(qts, OC_SR);

    g_assert((sr & STAT_IF) != 0);
    g_assert((sr & STAT_TIP) == 0);
    qtest_writel(qts, OC_CR, CMD_IACK);
    sr = qtest_readl(qts, OC_SR);
    g_assert((sr & STAT_IF) == 0);
    return sr;
}

static void oc_enable(QTestState *qts)
{
    qtest_writel(qts, OC_PRERLO, 0x3f);
    qtest_writel(qts, OC_PRERHI, 0x00);
    qtest_writel(qts, OC_CTR, CTR_EN);
}

static void test_reset_and_enable(void)
{
    QTestState *qts = oc_boot();
    uint32_t v;

    v = qtest_readl(qts, OC_PRERLO);
    g_assert((v & 0xff) == 0xff);
    v = qtest_readl(qts, OC_PRERHI);
    g_assert((v & 0xff) == 0xff);
    v = qtest_readl(qts, OC_CTR);
    g_assert(v == 0);
    v = qtest_readl(qts, OC_SR);
    g_assert((v & STAT_BUSY) == 0);
    oc_enable(qts);
    v = qtest_readl(qts, OC_CTR);
    g_assert((v & CTR_EN) != 0);
    qtest_quit(qts);
}

static void test_detect_tmp105(void)
{
    QTestState *qts = oc_boot();
    uint32_t sr;

    oc_enable(qts);
    /* START write-address for 0x48 */
    qtest_writel(qts, OC_DATA, (TMP105_ADDR << 1) | 0);
    qtest_writel(qts, OC_CR, CMD_STA);
    sr = oc_wait_if(qts);
    g_assert((sr & STAT_RXACK) == 0);
    g_assert((sr & STAT_BUSY) != 0);
    qtest_writel(qts, OC_CR, CMD_STO);
    sr = oc_wait_if(qts);
    g_assert((sr & STAT_BUSY) == 0);
    qtest_quit(qts);
}

static void test_detect_absent(void)
{
    QTestState *qts = oc_boot();
    uint32_t sr;

    oc_enable(qts);
    qtest_writel(qts, OC_DATA, (0x22 << 1) | 0);
    qtest_writel(qts, OC_CR, CMD_STA);
    sr = oc_wait_if(qts);
    g_assert((sr & STAT_RXACK) != 0);
    qtest_writel(qts, OC_CR, CMD_STO);
    oc_wait_if(qts);
    qtest_quit(qts);
}

static void test_tmp105_pointer_write(void)
{
    QTestState *qts = oc_boot();
    uint32_t sr;

    oc_enable(qts);
    /* Select temperature register (pointer 0) */
    qtest_writel(qts, OC_DATA, (TMP105_ADDR << 1) | 0);
    qtest_writel(qts, OC_CR, CMD_STA);
    sr = oc_wait_if(qts);
    g_assert((sr & STAT_RXACK) == 0);
    qtest_writel(qts, OC_DATA, 0x00);
    qtest_writel(qts, OC_CR, CMD_WR);
    sr = oc_wait_if(qts);
    g_assert((sr & STAT_RXACK) == 0);
    qtest_writel(qts, OC_CR, CMD_STO);
    oc_wait_if(qts);
    qtest_quit(qts);
}

static void test_tmp105_read_temp(void)
{
    QTestState *qts = oc_boot();
    uint32_t sr;
    uint8_t hi, lo;

    oc_enable(qts);
    /* pointer write 0 */
    qtest_writel(qts, OC_DATA, (TMP105_ADDR << 1) | 0);
    qtest_writel(qts, OC_CR, CMD_STA);
    oc_wait_if(qts);
    qtest_writel(qts, OC_DATA, 0x00);
    qtest_writel(qts, OC_CR, CMD_WR);
    oc_wait_if(qts);

    /* repeated START, read two bytes, NACK last */
    qtest_writel(qts, OC_DATA, (TMP105_ADDR << 1) | 1);
    qtest_writel(qts, OC_CR, CMD_STA);
    sr = oc_wait_if(qts);
    g_assert((sr & STAT_RXACK) == 0);

    qtest_writel(qts, OC_CR, CMD_RD);
    oc_wait_if(qts);
    hi = qtest_readl(qts, OC_DATA) & 0xff;

    qtest_writel(qts, OC_CR, CMD_RD | CMD_ACK);
    oc_wait_if(qts);
    lo = qtest_readl(qts, OC_DATA) & 0xff;

    qtest_writel(qts, OC_CR, CMD_STO);
    oc_wait_if(qts);

    /*
     * Default TMP105 temperature is 0 C (8.8 fixed point 0x0000).
     */
    g_assert(hi == 0x00);
    g_assert(lo == 0x00);
    qtest_quit(qts);
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);

    if (!qtest_has_machine("virt")) {
        g_test_skip("machine virt is not available");
        return g_test_run();
    }

    qtest_add_func("/ocores-i2c/reset", test_reset_and_enable);
    qtest_add_func("/ocores-i2c/detect-tmp105", test_detect_tmp105);
    qtest_add_func("/ocores-i2c/detect-absent", test_detect_absent);
    qtest_add_func("/ocores-i2c/pointer-write", test_tmp105_pointer_write);
    qtest_add_func("/ocores-i2c/read-temp", test_tmp105_read_temp);

    return g_test_run();
}
