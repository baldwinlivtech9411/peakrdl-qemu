/* RISC-V virt M-mode entry. QEMU -kernel loads this at 0x80000000. */

    .section .text.start, "ax"
    .globl _start
_start:
    /* Zero BSS */
    la      t0, __bss_start
    la      t1, __bss_end
1:
    bgeu    t0, t1, 2f
    sd      zero, 0(t0)
    addi    t0, t0, 8
    j       1b
2:
    la      sp, __stack_top
    call    main

    /* If main returns, treat as failure. */
    li      t0, 0x100000
    li      t1, 0x3333
    sw      t1, 0(t0)
    j       .
