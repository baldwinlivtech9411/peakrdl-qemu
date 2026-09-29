/*
 * Bare-metal RISC-V firmware for QEMU virt.
 *
 * The hart itself issues 32-bit loads/stores to:
 *   simple-timer  @ 0x102000
 *   OpenCores I2C @ 0x103000  (tmp105 @ 0x48 on that bus)
 *
 * UART is NS16550 at 0x10000000. Exit via SiFive test at 0x100000
 * (0x5555 pass, 0x3333 fail).
 */

#include <stdint.h>

#define UART_BASE     0x10000000UL
#define UART_THR      (*(volatile uint8_t *)(UART_BASE + 0x00))
#define UART_LSR      (*(volatile uint8_t *)(UART_BASE + 0x05))
#define LSR_THRE      0x20

#define TEST_BASE     0x100000UL
#define TEST_PASS     0x5555u
#define TEST_FAIL     0x3333u

#define TIMER_BASE    0x102000UL
#define TIMER_CTRL    (*(volatile uint32_t *)(TIMER_BASE + 0x00))
#define TIMER_LOAD    (*(volatile uint32_t *)(TIMER_BASE + 0x04))
#define TIMER_ID      (*(volatile uint32_t *)(TIMER_BASE + 0x10))
#define TIMER_ID_VAL  0x54494D52u  /* "TIMR" */

#define I2C_BASE      0x103000UL
#define I2C_PRERLO    (*(volatile uint32_t *)(I2C_BASE + 0x00))
#define I2C_PRERHI    (*(volatile uint32_t *)(I2C_BASE + 0x04))
#define I2C_CTR       (*(volatile uint32_t *)(I2C_BASE + 0x08))
#define I2C_DATA      (*(volatile uint32_t *)(I2C_BASE + 0x0c))
#define I2C_CR        (*(volatile uint32_t *)(I2C_BASE + 0x10))
#define I2C_SR        (*(volatile uint32_t *)(I2C_BASE + 0x10))

#define CTR_EN        0x80u
#define CMD_IACK      0x01u
#define CMD_ACK       0x08u
#define CMD_WR        0x10u
#define CMD_RD        0x20u
#define CMD_STO       0x40u
#define CMD_STA       0x80u
#define STAT_IF       0x01u
#define STAT_TIP      0x02u
#define STAT_BUSY     0x40u
#define STAT_RXACK    0x80u

#define TMP105_ADDR   0x48u

static int failed;

static void uart_putc(char c)
{
    while ((UART_LSR & LSR_THRE) == 0) {
        /* wait */
    }
    UART_THR = (uint8_t)c;
}

static void uart_puts(const char *s)
{
    while (*s) {
        if (*s == '\n') {
            uart_putc('\r');
        }
        uart_putc(*s++);
    }
}

static void uart_hex8(uint8_t v)
{
    static const char hex[] = "0123456789abcdef";

    uart_putc(hex[(v >> 4) & 0xf]);
    uart_putc(hex[v & 0xf]);
}

static void uart_hex32(uint32_t v)
{
    for (int i = 28; i >= 0; i -= 4) {
        static const char hex[] = "0123456789abcdef";
        uart_putc(hex[(v >> i) & 0xf]);
    }
}

static void fail(const char *msg)
{
    uart_puts("FAIL: ");
    uart_puts(msg);
    uart_puts("\n");
    failed = 1;
}

static void pass(const char *msg)
{
    uart_puts("ok: ");
    uart_puts(msg);
    uart_puts("\n");
}

static uint32_t i2c_wait_if(void)
{
    uint32_t sr = I2C_SR;

    if ((sr & STAT_IF) == 0) {
        fail("SR.IF not set after command");
        return sr;
    }
    if ((sr & STAT_TIP) != 0) {
        fail("SR.TIP set (expected clear; QEMU I2C is sync)");
    }
    I2C_CR = CMD_IACK;
    sr = I2C_SR;
    if ((sr & STAT_IF) != 0) {
        fail("SR.IF still set after IACK");
    }
    return sr;
}

static void i2c_enable(void)
{
    I2C_PRERLO = 0x3f;
    I2C_PRERHI = 0x00;
    I2C_CTR = CTR_EN;
}

static void test_timer(void)
{
    uint32_t id = TIMER_ID;
    uint32_t ctrl = TIMER_CTRL;
    uint32_t load = TIMER_LOAD;

    uart_puts("timer ID=0x");
    uart_hex32(id);
    uart_puts(" CTRL=0x");
    uart_hex32(ctrl);
    uart_puts(" LOAD=0x");
    uart_hex32(load);
    uart_puts("\n");

    if (id != TIMER_ID_VAL) {
        fail("simple-timer ID");
        return;
    }
    if (ctrl != 0x00001000u) {
        fail("simple-timer CTRL reset");
        return;
    }
    if (load != 0xffffffffu) {
        fail("simple-timer LOAD reset");
        return;
    }
    pass("simple-timer MMIO reset values");
}

static void test_i2c_reset(void)
{
    if ((I2C_PRERLO & 0xffu) != 0xffu || (I2C_PRERHI & 0xffu) != 0xffu) {
        fail("I2C prescale reset");
        return;
    }
    if (I2C_CTR != 0) {
        fail("I2C CTR reset");
        return;
    }
    if ((I2C_SR & STAT_BUSY) != 0) {
        fail("I2C BUSY at reset");
        return;
    }
    i2c_enable();
    if ((I2C_CTR & CTR_EN) == 0) {
        fail("I2C CTR.EN did not stick");
        return;
    }
    pass("OpenCores I2C enable via MMIO");
}

static uint32_t i2c_start(uint8_t addr7, int read)
{
    I2C_DATA = (uint32_t)((addr7 << 1) | (read ? 1u : 0u));
    I2C_CR = CMD_STA;
    return i2c_wait_if();
}

static uint32_t i2c_write(uint8_t data)
{
    I2C_DATA = data;
    I2C_CR = CMD_WR;
    return i2c_wait_if();
}

static uint32_t i2c_read(int nack, uint8_t *out)
{
    I2C_CR = CMD_RD | (nack ? CMD_ACK : 0);
    uint32_t sr = i2c_wait_if();
    *out = (uint8_t)(I2C_DATA & 0xffu);
    return sr;
}

static uint32_t i2c_stop(void)
{
    I2C_CR = CMD_STO;
    return i2c_wait_if();
}

static void test_detect_tmp105(void)
{
    uint32_t sr = i2c_start(TMP105_ADDR, 0);

    if ((sr & STAT_RXACK) != 0) {
        fail("tmp105@0x48 NACKed START");
        i2c_stop();
        return;
    }
    if ((sr & STAT_BUSY) == 0) {
        fail("BUS not busy after START to tmp105");
    }
    sr = i2c_stop();
    if ((sr & STAT_BUSY) != 0) {
        fail("BUS still busy after STOP");
        return;
    }
    pass("detected tmp105 @ 0x48 over I2C MMIO");
}

static void test_detect_absent(void)
{
    uint32_t sr = i2c_start(0x22, 0);

    if ((sr & STAT_RXACK) == 0) {
        fail("absent 0x22 ACKed (expected NACK)");
        i2c_stop();
        return;
    }
    i2c_stop();
    pass("absent 0x22 NACKed");
}

static void test_read_temp(void)
{
    uint8_t hi = 0xff, lo = 0xff;
    uint32_t sr;

    /* pointer write: select temperature register 0 */
    sr = i2c_start(TMP105_ADDR, 0);
    if (sr & STAT_RXACK) {
        fail("tmp105 NACK on pointer START");
        return;
    }
    sr = i2c_write(0x00);
    if (sr & STAT_RXACK) {
        fail("tmp105 NACK on pointer byte");
        i2c_stop();
        return;
    }

    /* repeated START, read two bytes, NACK last */
    sr = i2c_start(TMP105_ADDR, 1);
    if (sr & STAT_RXACK) {
        fail("tmp105 NACK on read START");
        i2c_stop();
        return;
    }
    i2c_read(0, &hi);
    i2c_read(1, &lo);
    i2c_stop();

    uart_puts("tmp105 temp bytes: ");
    uart_hex8(hi);
    uart_puts(" ");
    uart_hex8(lo);
    uart_puts("\n");

    if (hi != 0 || lo != 0) {
        fail("tmp105 default temperature is not 0 C");
        return;
    }
    pass("tmp105 read 0 C via RISC-V MMIO");
}

int main(void)
{
    uart_puts("\npeakrdl-qemu RISC-V guest: I2C over MMIO\n");

    test_timer();
    test_i2c_reset();
    test_detect_tmp105();
    test_detect_absent();
    test_read_temp();

    if (failed) {
        uart_puts("RESULT: FAIL\n");
        *(volatile uint32_t *)TEST_BASE = TEST_FAIL;
    } else {
        uart_puts("RESULT: PASS\n");
        *(volatile uint32_t *)TEST_BASE = TEST_PASS;
    }

    for (;;) {
        /* SiFive test should have exited QEMU. */
    }
    return 0;
}
