# Design decisions (phase 1)

Record of choices and deviations from the project spec. See
`PHASE1_REPORT.md` for verified QEMU signatures and M3 risks.

## License

The tool is **MIT**. Generated C defaults to `GPL-2.0-or-later` because it is
compiled into QEMU. `--license` overrides the SPDX identifier on generated
files only.

## QEMU pin

Pinned **v10.2.4** (stored in `QEMU_VERSION`). That is a current 10.2.x
stable tag; 11.x exists but the spec asked for a 10.0.x / 9.2.x-class pin
and v10.2.4 is the closest maintained 10.x line.

Templates are written against this tag only.

## UDPs are hard, not soft

PeakRDL 1.5 registers `udp_definitions` as *soft* UDPs via
`RDLCompiler.register_udp(udp)` (default `soft=True`). Soft UDPs cannot be
assigned in RDL (`qemu_irqs = 1;`) unless they are also declared there, and
an in-RDL `property qemu_irqs { ... }` conflicts with the pre-registered
default.

**Decision:** the exporter overrides `Exporter.main()` and registers the
three UDPs with `soft=False`. Tests do the same. `qemu_udps.rdl` is shipped
for library users who compile with `systemrdl-compiler` directly.

Boolean UDPs use `default_assignment = True` so a valueless binding
(`qemu_read_hook;`) means true. `get_unassigned_default()` still returns
false when the property is not mentioned.

## Root addrmap is always `external`

`systemrdl-compiler` reports `AddrmapNode.external == True` for the
elaborated top. The non-goal "reject `external` components" is applied to
**children** (regs, fields, nested addrmaps), not the exported root.

## Masks

Implemented exactly as the spec §11.0 table:

| | reset | ro | w1c | cor | rsvd |
|---|---|---|---|---|---|
| CTRL | `0x00001000` | `0xFFFF00FC` | 0 | 0 | `0xFFFF00FC` |
| LOAD | `0xFFFFFFFF` | 0 | 0 | 0 | 0 |
| COUNT | 0 | `0xFFFFFFFF` | 0 | 0 | 0 |
| STATUS | 0 | `0xFFFFFFFE` | `0x1` | `0x2` | `0xFFFFFFFC` |
| ID | `0x54494D52` | `0xFFFFFFFF` | 0 | 0 | 0 |

Reserved (uncovered) bits are ORed into **both** `.ro` and `.rsvd`. `.rsvd`
alone only logs; `.ro` actually blocks the write (`no_w_mask` in
`register_write()`).

STATUS.OVERRUN (`sw = r`, `onread = rclr`) is in **both** `.ro` and `.cor`.
That matches the spec table. QEMU clears `.cor` bits after snapshotting the
read value, and `.ro` still prevents writes. Kept as-is.

## Shared-pair detection vs generation

`_group_by_offset()` classifies two registers at one offset as a shared pair
when one is write-only and the other is read-only. M3 folds them into one
`RegisterAccessInfo` named `<W>_<R>` backed by write-side storage
`regs[R_<W>]`, plus `uint32_t shadow_<r>` in the state struct / VMState.
Generated `post_read` returns the shadow. Reset writes the write-side
`.reset` via `register_reset`, then sets the shadow to the read-side reset.
True overlaps that are not a WO/RO pair still error.

Overlapping **fields** with complementary `sw` in one register (PeakRDL
gotcha example) are still rejected: v1 has one storage word per register
and cannot represent two values at the same bits.

## M3 onwrite / onread / pulse

`register_write()` applies `.ro` / `.w1c` / `.rsvd` **before** `pre_write`.
Generated `pre_write` therefore treats `val` as the value about to be
stored, plus `old` from `reg->data`:

| onwrite | formula |
|---|---|
| `woset` | `new \|= old & mask` (written 1s already in `val`; restore old 1s that wrote 0) |
| `wot` | bits written 1 are toggled from old |
| `wzc` | bits written 0 are cleared |
| `wzs` | bits written 0 are set |
| `wzt` | bits written 0 are toggled |
| `wclr` | mask bits forced 0 |
| `wset` | mask bits forced 1 |
| `woclr` | QEMU `.w1c` (no `pre_write`) |

`onread = rset` ORs the mask into storage in `post_read` **after** the
user hook sees the value (and after QEMU already applied `.cor`).

`singlepulse`: `post_write` calls the user write hook with the full
written value, then clears pulse bits in `regs[R_X]`. Reset's
`register_reset` also runs `post_write`; pulses are already 0 at reset so
the extra clear is a no-op.

`onwrite = wuser` and `onread = ruser` remain unsupported (no callback
in the RDL we can implement).

## `register_finalize_block`

Does **not** exist in v10.2.4. Cleanup is the `RegisterInfoArray` QOM
`instance_finalize` (`register_array_finalize`), which runs when the child
object is destroyed. Generated devices do not call a finalize helper.

## Reset phase

In-tree examples split reset across `phases.enter` (register_reset) and
`phases.hold` (side effects). The spec asks for the hold-phase signature
from the pinned tree and a loop of `register_reset` then
`<dev>_behavior_reset`. **Decision:** both the register reset and the
behaviour reset run in **hold**, matching "after every object's enter has
run, devices may affect others". `register_reset` itself already invokes
`post_write`, so write hooks run on reset; behaviour_reset follows that.

## Realize vs instance_init

`register_init_block32`, MMIO, and `sysbus_init_irq` live in `instance_init`
(as in `xlnx-versal-usb2-ctrl-regs.c`). `<dev>_behavior_init` is called from
`realize`, which is where child buses (I2C, later) will be created.

## Includes

Headers are included as `hw/<subdir>/<file>` so they resolve against QEMU's
`include/` / source-root `-iquote`. Device sources live in `hw/<subdir>/`
next to the headers.

## Access size

v1 devices are 32-bit registers on a 4-byte stride. Generated
`MemoryRegionOps.valid` is **min = max = 4**, matching in-tree users of
`register_read_memory` / `register_write_memory` (USB2 ctrl regs, ZynqMP RTC,
Versal TRNG).

Those helpers look up by **exact** `access->addr`. Advertising
`min_access_size = 1` would accept `readb(base+1)` and then log it as
unimplemented. Closing the window at the MemoryRegionOps layer is the
correct policy for 32-bit maps (OpenCores I2C with `reg-shift=2` included).
Packed 8-bit maps, if ever needed, would use `register_init_block8` rather
than teaching the 32-bit helpers about interior bytes.

## Board address for the test device

virt memmap in v10.2.4:

- `VIRT_RTC` = `0x101000` size `0x1000`
- next large window is `VIRT_CLINT` at `0x2000000`

**0x102000** is unused. IRQ **12** is unused (UART0=10, RTC=11, virtio=1–8,
PCI=32). No DT node in phase 1.

## Smoke reads use qtest, not HMP `xp`

Spec §14 asked to verify whether HMP `xp` goes through MMIO callbacks.
Phase-1 smoke uses qtest `readl` (and HMP `info mtree` on a monitor socket)
because that is a direct MemoryRegionOps path. See `ci/phase1_smoke.sh`.

## checkpatch

Generated C is formatted to pass `scripts/checkpatch.pl --no-tree` with
zero errors / zero warnings on v10.2.4.

## `mem` rejection

`tests/rdl/mem.rdl` is rejected by **systemrdl-compiler** before the
exporter (`mem` inside addrmap without a legal `mementries`/`memwidth`
combination depending on version). The unit test skips in that case. The
builder still has an explicit `mem components are not supported` path.

## Naming

- C identifiers: `inst_name` through `_c_ident` (non-alnum → `_`)
- macros: upper-case (`SIMPLE_TIMER`)
- functions / filenames: lower-case (`simple_timer_ctrl_write`)
- QOM type: underscores → dashes (`"simple-timer"`)
- CamelCase state type: `SimpleTimerState`

## Idempotent `--apply-to`

Snippets are wrapped in `# BEGIN peakrdl-qemu <DEV>` / `# END ...` markers.
Replacement uses those markers; a second run is a byte no-op on
meson/Kconfig.

## Determinism

Jinja is rendered with `keep_trailing_newline`, Unix `\n`, rstrip per line,
and a single trailing newline. No timestamps.

## M4 generated qtest

`--qtest-base` and `--qtest-machine` must be given together. They produce
`<dev>-test.c` and a `qtest.meson.build.snippet`. `--apply-to` copies the
test into `tests/qtest/` and inserts

```
qtests_riscv64 += (config_all_devices.has_key('CONFIG_<DEV>') ? ['<dev>-test'] : [])
```

**after** the existing `qtests_riscv64 =` continued assignment. Appending
at EOF is too late: meson already consumed the list.

Assertions use `g_assert(...)` rather than `g_assert_cmphex`, because
`scripts/checkpatch.pl --no-tree` treats `g_assert_cmphex` as an error.

Skip policy:

- Shared pairs and `qemu_read_hook` registers are skipped entirely
  (observed value is behavior-owned).
- Hardware-writable fields skip **reset and RW** (behavior can change
  them) but still emit W1C / RCLR checks. That is why STATUS.EXPIRED /
  STATUS.OVERRUN are tested even though COUNT is skipped.
- RW mask is software-visible stored bits only (`sw = rw`/`rw1`, not
  pulse / w1c / rclr / reserved).

The generated test boots `-machine <name>` and assumes the device is
already mapped at `--qtest-base` (the phase-1 virt patch for
simple-timer). Instantiating an extra sysbus device from qtest without a
board hookup is not attempted.

## M5 arrays, regfiles, hook-diff

Arrays are expanded with `children(unroll=True)` / `Node.unrolled()`. The
unrolled node still has `is_array=True`; we use `current_idx` plus
`absolute_address` (not `address_offset`, which is relative to a
regfile). C names come from path segments:

- `DATA[0]` → `DATA_0`
- `MAT[1][2]` → `MAT_1_2`
- `GRP.R0` → `GRP_R0`
- `BANK[1].V` → `BANK_1_V`

Each expanded instance is a normal `RegisterModel` with its own hooks
(`<dev>_data_0_write`, …). Shared-pair detection still runs after
flattening, on absolute addresses.

Hook-diff runs only when `*_behavior.c` is **kept**. Function names are
parsed from column-0 `void`/`uint32_t` definitions. `NEW HOOK` prints the
full signature; `STALE HOOK` prints the C name. New stubs go to
`<dev>_behavior.new_hooks.c` and are overwritten on each regen that still
has missing hooks.

## M6 OpenCores I2C

The RDL models 32-bit-spaced Wishbone registers (`reg-shift = 2`) with two
shared pairs (`TXR`/`RXR`, `CR`/`SR`). CR `STA/STO/RD/WR/IACK` are
`singlepulse`; `ACK` is a level used by the next `RD`.

Behavior lives in `examples/ocores_i2c/ocores_i2c_behavior.c` (never
overwritten). `behavior_init` creates `i2c_init_bus(dev, "i2c")`. CR writes
call `i2c_start_transfer` / `i2c_send` / `i2c_recv` / `i2c_nack` /
`i2c_end_transfer`, set `SR.IF`, and raise IRQ0 when `CTR.IEN` is set.
QEMU I2C is synchronous, so `TIP` is always left clear (Linux polls `TIP`
or waits for `IF`; both work).

Board: RISC-V virt at **0x103000**, IRQ **13**, DT
`compatible = "opencores,i2c-ocores"`, `reg-shift = <2>`,
`reg-io-width = <4>`, `opencores,ip-clock-frequency = <20000000>`,
child `ti,tmp105@48`. Patch:
`qemu-patches/m6-virt-ocores-i2c.patch`.

Linux guest smoke needs an external kernel/rootfs (`ci/m6_linux_smoke.sh`
skips without `OCORES_KERNEL`/`OCORES_ROOTFS`). Default M6 gate is
`ci/m6_smoke.sh`, which drives the **same CR/SR protocol as Linux
i2c-ocores** against tmp105 (detect 0x48, NACK absent addr, pointer write,
read 0 C).

## RISC-V guest firmware

Host qtest pokes MMIO without a hart. `examples/riscv-guest/` is a
freestanding rv64gc binary (`-bios none -kernel firmware.elf`) that
issues `lw`/`sw` to simple-timer (`0x102000`) and OpenCores I2C
(`0x103000`). UART is NS16550 at `0x10000000`; the firmware exits QEMU
through SiFive test (`0x100000`, `0x5555` / `0x3333`).

The I2C sequence matches Linux `i2c-ocores` / `ocores_i2c-test.c`
(enable, detect 0x48, NACK 0x22, pointer write, read 0 C). CI job
`riscv-guest` applies `m6-virt-ocores-i2c.patch` and runs
`ci/riscv_guest_smoke.sh`.
