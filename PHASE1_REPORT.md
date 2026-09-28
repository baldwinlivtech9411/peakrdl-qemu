# Phase 1 report (M0–M2)

Status: **complete**. The exporter installs, unit/golden tests pass, generated
C compiles in QEMU v10.2.4 with `--enable-werror`, `checkpatch.pl` is clean,
and the virt smoke check reads back the simple-timer reset values.

This is the hard stop after M2. M3+ is not implemented.

## 1. Status and acceptance commands

Repository: `/home/ubuntu/peakrdl-qemu`
Pinned QEMU tree used for this report: `/home/ubuntu/src/qemu` (`v10.2.4`)

### 13.1.1 Install and CLI

```shell
cd /home/ubuntu/peakrdl-qemu
pip install -e ".[dev]"
peakrdl qemu --help
```

`peakrdl qemu --help` lists exactly the phase 1 options: `-o`,
`--device-name`, `--qemu-subdir`, `--kconfig-select`, `--endianness`,
`--license`, `--apply-to`. It does **not** list `--qtest-base`,
`--qtest-machine`, or `--emit-ai-context`.

### 13.1.2 pytest

```shell
cd /home/ubuntu/peakrdl-qemu
pytest
```

Result: all tests passed, including the §11.0 mask table.

### 13.1.3 Generate, apply, build QEMU with `-Werror`

```shell
cd /home/ubuntu/peakrdl-qemu
peakrdl qemu examples/simple_timer/simple_timer.rdl -o out \
    --apply-to /home/ubuntu/src/qemu
git -C /home/ubuntu/src/qemu apply \
    $PWD/qemu-patches/phase1-virt-simple-timer.patch
ninja -C /home/ubuntu/src/qemu/build
```

(If the QEMU tree is not already configured:

```shell
cd /home/ubuntu/src/qemu
./configure --target-list=riscv64-softmmu --enable-werror --disable-docs \
    --disable-guest-agent --disable-sdl --disable-gtk --disable-vnc \
    --disable-tools --audio-drv-list=
```

or `./ci/build_qemu.sh`.)

The generated `simple_timer_gen.c` / `simple_timer_behavior.c` compiled and
linked with `-Werror`. No warnings from those files.

### 13.1.4 checkpatch

```shell
/home/ubuntu/src/qemu/scripts/checkpatch.pl --no-tree --no-signoff \
    /home/ubuntu/src/qemu/hw/misc/simple_timer_gen.c \
    /home/ubuntu/src/qemu/hw/misc/simple_timer_behavior.c \
    /home/ubuntu/src/qemu/hw/misc/simple_timer.h \
    /home/ubuntu/src/qemu/hw/misc/simple_timer_regs.h \
    /home/ubuntu/src/qemu/hw/misc/simple_timer_behavior.h
```

Result: **0 errors, 0 warnings** on every file.

### 13.1.5 Smoke

```shell
QEMU_BIN=/home/ubuntu/src/qemu/build/qemu-system-riscv64 \
    /home/ubuntu/peakrdl-qemu/ci/phase1_smoke.sh
```

Observed:

```
CTRL  @ 0x102000 = 0x00001000
LOAD  @ 0x102004 = 0xffffffff
ID    @ 0x102010 = 0x54494d52
info mtree: simple-timer region present
  0000000000102000-0000000000102013 (prio 0, i/o): simple-timer
phase1 smoke: MMIO region visible and reset values OK
```

Reads are qtest `readl` (MemoryRegionOps). `info mtree` is HMP over a
monitor socket. HMP `xp` was **not** used; see §5.

### 13.1.6 Determinism and overwrite policy

```shell
peakrdl qemu examples/simple_timer/simple_timer.rdl -o /tmp/a
peakrdl qemu examples/simple_timer/simple_timer.rdl -o /tmp/b
# generated files are byte-identical (covered by pytest)
peakrdl qemu examples/simple_timer/simple_timer.rdl -o out --apply-to $QEMU
peakrdl qemu examples/simple_timer/simple_timer.rdl -o out --apply-to $QEMU
# second --apply-to leaves meson.build / Kconfig unchanged
```

Existing `*_behavior.c` / `*_behavior.h` are never overwritten.

### 13.1.7 Feature gates

```shell
peakrdl qemu tests/rdl/shared_pair.rdl -o /tmp/rej
# error: shared address pairs are not supported yet (planned for M3) (tests/rdl/shared_pair.rdl:3)
peakrdl qemu tests/rdl/write_only.rdl -o /tmp/rej
# error: sw = w write-only fields are not supported yet (planned for M3) (...)
peakrdl qemu tests/rdl/singlepulse.rdl -o /tmp/rej
# error: singlepulse is not supported yet (planned for M3) (...)
```

No Python traceback. Also gated: `woset`, `rset`, arrays, `regfile`,
`regwidth=64`, `mem`, counters, non-shared overlaps.

### 13.1.8 Docs

`README.md`, `DECISIONS.md`, and this file.

## 2. Pinned versions

| Component | Version |
|---|---|
| QEMU | **v10.2.4** (`QEMU_VERSION`, `VERSION` file `10.2.4`) |
| Python | 3.12.3 (sandbox); package requires ≥ 3.9 |
| peakrdl / peakrdl-cli | 1.5.0 |
| systemrdl-compiler | 1.32.2 |
| jinja2 | 3.1.6 |
| peakrdl-qemu | 0.1.0 |

QEMU configure (this run): `--target-list=riscv64-softmmu --enable-werror --disable-docs --disable-guest-agent --disable-sdl --disable-gtk --disable-vnc --disable-tools --audio-drv-list=`.

## 3. Verified QEMU API signatures (v10.2.4)

Source: `include/hw/register.h`, `include/hw/resettable.h`,
`include/qom/object.h`, `hw/core/register.c`. In-tree reference devices:
`hw/usb/xlnx-versal-usb2-ctrl-regs.c`, `hw/rtc/xlnx-zynqmp-rtc.c`.

### `register_init_block32`

```c
RegisterInfoArray *register_init_block32(DeviceState *owner,
                                         const RegisterAccessInfo *rae,
                                         int num, RegisterInfo *ri,
                                         uint32_t *data,
                                         const MemoryRegionOps *ops,
                                         bool debug_enabled,
                                         uint64_t memory_size);
```

Matches the spec. `ri[index]` is indexed by `addr / 4`, not by table order.

### `register_reset`

```c
void register_reset(RegisterInfo *reg);
```

Writes `.reset` into storage, then calls `post_write` if present.

### `register_finalize_block`

**Does not exist** in v10.2.4. There is no public finalize helper.
`RegisterInfoArray` has a QOM `instance_finalize` (`register_array_finalize`)
that `g_free`s the pointer array. Generated devices do not call anything
from `instance_finalize`. Deviation from spec §9.3, documented in
`DECISIONS.md`.

### MMIO ops

```c
void register_write_memory(void *opaque, hwaddr addr, uint64_t value,
                           unsigned size);
uint64_t register_read_memory(void *opaque, hwaddr addr, unsigned size);
```

Lookup is by **exact** `access->addr`. Size only builds the byte enable mask
(`register_enabled_mask`). Sub-word accesses at the register base work;
`addr + 1` is "unimplemented register".

### `RegisterAccessInfo`

```c
struct RegisterAccessInfo {
    const char *name;
    uint64_t ro;
    uint64_t w1c;
    uint64_t reset;
    uint64_t cor;
    uint64_t rsvd;
    uint64_t unimp;
    uint64_t (*pre_write)(RegisterInfo *reg, uint64_t val);
    void     (*post_write)(RegisterInfo *reg, uint64_t val);
    uint64_t (*post_read)(RegisterInfo *reg, uint64_t val);
    hwaddr addr;
};
```

Callback types match spec §8.4 exactly.

### Resettable hold phase

```c
typedef void (*ResettableHoldPhase)(Object *obj, ResetType type);
```

`ObjectClass.class_init` in this tag:

```c
void (*class_init)(ObjectClass *klass, const void *data);
```

(not `void *data`). Generated `class_init` uses `const void *data`.

### Write / read semantics (relevant to STATUS.OVERRUN)

From `register_write()`:

```c
no_w_mask = ac->ro | ac->w1c | ac->rsvd | ~we;
new_val = (val & ~no_w_mask) | (old_val & no_w_mask);
new_val &= ~(val & ac->w1c);
```

`.rsvd` bits are not writable (they sit in `no_w_mask`) **and** log on
change. Spec asked to OR uncovered bits into both `.ro` and `.rsvd`; we
do. `.ro` alone would also block writes; the extra `.rsvd` is for the log.

From `register_read()`:

```c
ret = register_read_val(reg);
register_write_val(reg, ret & ~(ac->cor & re));  /* clear-on-read first */
ret &= re;
if (ac->post_read) ret = ac->post_read(reg, ret);
```

`.cor` and `.ro` on the same bit (STATUS.OVERRUN) coexist: reads return the
old value then clear storage; writes cannot set the bit because of `.ro`.

## 4. Deviations (short)

Full discussion in `DECISIONS.md`.

1. **QEMU pin is v10.2.4**, not a 9.2.x / 10.0.x example. Same 10.x register
   API.
2. **UDPs registered hard** (`soft=False`). PeakRDL's default soft
   registration cannot assign `qemu_irqs = 1;` without an RDL `property`
   declaration, which then conflicts with the plugin UDP.
3. **Root addrmap `external` is ignored.** `systemrdl-compiler` always
   reports the elaborated top as external. Nested/child `external` still
   errors.
4. **No `register_finalize_block`** — API absent; no generated finalize.
5. **Reset in hold only** (register_reset + behaviour_reset), not
   enter+hold split.
6. **Smoke uses qtest `readl`**, not HMP `xp`.
7. **Test device at 0x102000 / IRQ 12**, unused virt gap after goldfish RTC.
8. Error lines look like
   `error: <message> (<file>:<line>)` rather than `<file>:<line>: error:`.

No other spec mappings were dropped.

## 5. Risks found for M3+

### Shared address pairs

`systemrdl-compiler` 1.32.2 **accepts** two registers at the same offset
(`TXR` `sw=w` and `RXR` `sw=r` @ 0x0C). The builder already classifies them
as a `SharedPair` and currently errors. M3 can reuse `_group_by_offset()`.

### `singlepulse` on `sw=w`

Accepted by the compiler on both `sw=w` and `sw=rw` fields. Phase 1 rejects
`sw=w` first (`write-only fields ... M3`) and `singlepulse` on `sw=rw`
(`singlepulse ... M3`). M3 must generate `post_write`: user hook, then
clear the pulse bits.

### 1-byte accesses through the register API

**Mitigated before M3.** Generated `MemoryRegionOps.valid` is now
`min_access_size = max_access_size = 4`, matching in-tree register-API
devices. Guests cannot issue 1-byte accesses that would miss the exact-addr
lookup in `register_read_memory`.

The underlying helper still matches **exact** `access->addr`; that is
unchanged QEMU core. Packed 8-bit maps (not in M3; OpenCores I2C uses
`reg-shift=2`) would need `register_init_block8` or custom ops, not
`min_access_size = 1` on a 32-bit block.

### `mem`

`mem` **must** be instantiated `external`. A non-external `mem` dies in the
compiler before the exporter. `tests/rdl/mem.rdl` uses `external mem` so
the exporter's own rejection path is tested.

### STATUS.OVERRUN `.ro` + `.cor`

Not observed to misbehave: `.cor` still clears on read, `.ro` still blocks
writes. Keep the §11.0 table.

### `post_write` on reset

`register_reset()` calls `post_write` with the reset value. Behaviour write
hooks therefore run at reset, before `behavior_reset`. Empty stubs are
fine; M6 behaviour must tolerate that (or ignore writes that equal reset).

### Include path / subdir

Generated `#include "hw/<subdir>/..."` assumes `--qemu-subdir` matches the
directory `--apply-to` copies into. Mismatch would fail the QEMU build.

## 6. Proposed plan for M3

M3 = shared pairs, write-only fields, `singlepulse`, remaining
`onwrite`/`onread`. Suggested order:

1. **Write-only fields (`sw=w`/`w1`) in a normal register**
   - Keep them out of `.ro`.
   - Generated `post_read` returns `val & ~writeonly_mask`.
   - Compose with an existing user `qemu_read_hook` (hook sees the masked
     value, or the raw value? Prefer raw storage then mask after the hook,
     matching "returns val & ~mask").
2. **`onread = rset`**
   - Generated `post_read`: set bits in storage after capturing `val`.
   - Order vs `.cor` is fixed inside `register_read` (`.cor` already
     happened). Implement rset in `post_read` on storage via `reg->data`.
3. **Other `onwrite` (`woset`, `wot`, `wzc`, `wzs`, `wclr`, `wset`)**
   - Generated `pre_write`: compute new value from old + written.
   - Note `pre_write` is invoked **after** `.ro`/`.w1c`/`rsvd` have already
     been applied (`register_write`). For `woset` this is what we want
     (operate on the value about to be stored). For `wclr`/`wset` (ignore
     data, all bits clear/set) implement accordingly.
4. **`singlepulse`**
   - Generated `post_write`: call the user write hook with the full written
     value, **then** clear the pulse bits in `regs[R_X]`.
   - Must run after (3) so `pre_write` sees the pulse.
   - Reset's `post_write` will also call the user hook; document that
     pulses at reset are already 0.
5. **Shared pairs**
   - Reuse `_group_by_offset()`.
   - One `RegisterAccessInfo` named `<W>_<R>` at the offset, backed by
     write-side storage `regs[R_<W>]`.
   - `REG32(<W>, off)` + write-side `FIELD`s; read-side `FIELD(<R>, ...)`
     only (no second `REG32`).
   - `uint32_t shadow_<r>` in state + VMState.
   - `post_read` returns `s->shadow_<r>`.
   - `.ro` = write-side unused bits only; `.reset` = write-side reset;
     reset handler also sets `shadow_<r>` to the read-side reset.
   - Behaviour updates `s->shadow_<r>` directly.
   - Golden tests: OpenCores-style TXR/RXR pair (even if the full I2C
     device waits for M6).
6. **Goldens + unit tests**
   - Extend `tests/rdl/` cases that currently must fail so they generate.
   - Keep one negative test for true overlaps that are *not* a WO/RO pair.
7. **Do not start M4** (qtest generator) in the same pass.

Out of M3: arrays / `regfile` / hook-diff (M5), qtest (M4), I2C demo (M6).

## 7. M3 implemented

Status: **complete**. Shared pairs, write-only fields, `singlepulse`,
`onread = rset`, and `onwrite` other than `woclr` now generate. Arrays /
`regfile` (M5), qtest (M4), and the I2C demo (M6) are still out of scope.

Example: `examples/m3_features/m3_features.rdl` (MIXED, WOSET, RSET,
TXR/RXR pair, CR singlepulse). Goldens under `tests/golden/m3_features/`.

Generated `m3_features_gen.c` compiles with the pinned QEMU `-Werror`
flags and passes `checkpatch.pl` with 0 errors / 0 warnings.

Hook order in `post_read`:

1. Shared pair: replace `val` with `s->shadow_<r>` (and apply read-side
   `.cor` to the shadow).
2. User `qemu_read_hook`, if any.
3. `onread = rset` ORs bits into storage / shadow.
4. Write-only mask: `ret &= ~writeonly_mask` (normal registers only).

`wuser` / `ruser` remain rejected. Complementary overlapping fields in
one register are rejected (`overlapping fields`). Complementary WO/RO
*registers* at one address are the shared-pair case and generate.

## 8. M4 implemented

Status: **complete**. `--qtest-base` + `--qtest-machine` emit
`<dev>-test.c` and a meson snippet. Generated simple-timer qtest:

```
QTEST_QEMU_BINARY=./qemu-system-riscv64 ./tests/qtest/simple_timer-test --tap -k
```

7/7 TAP tests passed on RISC-V virt (`ctrl` reset/rw, `load` reset/rw,
`status` w1c/rclr, `id` reset). COUNT is skipped (hw-writable). Shared
pairs are skipped with a comment.

Edge-case RDLs (`w1c_only`, `rclr_only`, `rw_rsvd`) generate, compile
with `-Werror`, and pass `checkpatch.pl` (0 errors). They are not run
on virt because those devices are not board-mapped.

M5 (arrays / regfile / hook-diff) is not started.

## 9. M5 implemented

Status: **complete**. Register arrays expand to `X_0`…`X_{N-1}`;
`regfile` (including arrays of regfiles, nested) flatten with a name
prefix. Example: `examples/m5_arrays/m5_arrays.rdl`. Goldens under
`tests/golden/m5_arrays/`.

Regeneration hook-diff: `NEW HOOK:` / `STALE HOOK:` plus
`<dev>_behavior.new_hooks.c`. Behavior files are never overwritten.

Generated `m5_arrays_gen.c` compiles with pinned QEMU `-Werror` and
passes `checkpatch.pl` (0 errors / 0 warnings).

M6 (OpenCores I2C demo) is not started.

## 10. M6 implemented

Status: **complete** (qtest gate). Reference OpenCores I2C behavior is
filled in. RISC-V virt maps the device at 0x103000 / IRQ 13 with a DT
node and `tmp105@48`.

```
QTEST_QEMU_BINARY=./qemu-system-riscv64 ./tests/qtest/ocores_i2c-test --tap -k
```

5/5 TAP tests passed (`reset`, `detect-tmp105`, `detect-absent`,
`pointer-write`, `read-temp`). DTB contains `opencores,i2c-ocores`,
`reg-shift`, `ti,tmp105`, `tmp105@48`.

Generated C and behavior pass `checkpatch.pl` (0 errors / 0 warnings) and
build with `--enable-werror`.

A full Linux boot (`i2cdetect -y 0` / `temp1_input`) is
`ci/m6_linux_smoke.sh` and needs an external kernel+rootfs; it is not
run in this sandbox. M7 (`--emit-ai-context`) is optional and not started.
