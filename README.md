# peakrdl-qemu

PeakRDL exporter that turns a SystemRDL 2.0 register description into a
**QEMU sysbus device** that compiles in a pinned QEMU tree.

Phase 1 (M0–M2) generates:

- `<dev>_regs.h`, `<dev>.h`, `<dev>_gen.c` — always overwritten
- `<dev>_behavior.h`, `<dev>_behavior.c` — stubs, written only if absent
- meson / Kconfig snippets, and optional `--apply-to` into a QEMU source tree

The generated C uses QEMU's register API (`hw/register.h` /
`hw/registerfields.h`). Device-specific behaviour lives in the behaviour
file, which the generator never overwrites.

## Install

```shell
pip install -e ".[dev]"
```

Requires Python ≥ 3.9, `peakrdl`, `systemrdl-compiler`, and `jinja2`.

## Usage

```shell
peakrdl qemu examples/simple_timer/simple_timer.rdl -o out/

peakrdl qemu examples/simple_timer/simple_timer.rdl -o out/ \
    --apply-to /path/to/qemu
```

Phase 1 options:

| Option | Default | Meaning |
|---|---|---|
| `-o PATH` | required | Output directory |
| `--device-name NAME` | top addrmap name | C / QOM identifier base |
| `--qemu-subdir SUBDIR` | `misc` | Place sources in `hw/<subdir>/` |
| `--kconfig-select SYM` | none | Extra `select` lines (repeatable) |
| `--endianness little\|big` | `little` | `MemoryRegionOps` endianness |
| `--license SPDX_ID` | `GPL-2.0-or-later` | SPDX line on generated C |
| `--apply-to QEMU_SRC` | unset | Copy into the QEMU tree and patch meson/Kconfig |
| `--qtest-base ADDR` | unset | MMIO base for generated `<dev>-test.c` (M4) |
| `--qtest-machine NAME` | unset | QEMU machine for the qtest (must be paired with `--qtest-base`) |

`--qtest-base` and `--qtest-machine` must be given together. `--emit-ai-context`
(M7) is not implemented.

### Apply-to

`--apply-to` copies the five C/H files into `hw/<subdir>/` and appends
marked snippets to `meson.build` and `Kconfig`:

```
# BEGIN peakrdl-qemu SIMPLE_TIMER
system_ss.add(when: 'CONFIG_SIMPLE_TIMER', if_true: files('simple_timer_gen.c', 'simple_timer_behavior.c'))
# END peakrdl-qemu SIMPLE_TIMER
```

A second run leaves meson/Kconfig unchanged. Behaviour files that already
exist are kept (`kept existing <file>`).

With `--qtest-base` and `--qtest-machine`, `--apply-to` also copies
`<dev>-test.c` into `tests/qtest/` and inserts a
`qtests_riscv64 += ...` snippet after the `qtests_riscv64 =` assignment.

## Pinning QEMU

The templates target the tag in [`QEMU_VERSION`](QEMU_VERSION)
(`v10.2.4`). Build it with:

```shell
./ci/build_qemu.sh          # clones to $HOME/src/qemu if needed
```

Recommended configure flags: `--target-list=riscv64-softmmu --enable-werror --disable-docs`.

## Phase 1 test device

`examples/simple_timer/simple_timer.rdl` covers RW, RO, reset, W1C, RCLR,
reserved bits, hardware-writable fields, and one IRQ.

M6 demo: `examples/ocores_i2c/` is a working OpenCores I2C master (RDL + behavior + virt DT + tmp105@0x48). See that directory's README.

After `--apply-to` plus
[`qemu-patches/phase1-virt-simple-timer.patch`](qemu-patches/phase1-virt-simple-timer.patch)
the device sits on RISC-V `virt` at **0x102000**, IRQ 12.

```shell
QEMU_SRC=$HOME/src/qemu ./ci/phase1_smoke.sh
```

## Mapping table (phase 1)

## Mapping table (M0–M3)

| SystemRDL | Generated QEMU construct |
|---|---|
| top `addrmap` | `TYPE_<DEV>`, state struct, `OBJECT_DECLARE_SIMPLE_TYPE`, MMIO of size `mmio_size` |
| `reg X @ off` | `REG32(X, off)` → `A_X`, `R_X` |
| `field F[msb:lsb]` | `FIELD(X, F, lsb, width)` |
| field `reset` | ORed into `.reset` |
| field `sw = r` | field mask ORed into `.ro` |
| `onwrite = woclr` | mask ORed into `.w1c` |
| `onread = rclr` | mask ORed into `.cor` |
| bits with no field | ORed into **both** `.ro` and `.rsvd` |
| `hw = w` / `hwset` / `hwclr` | no generated logic; listed in the per-register comment |
| field `sw = w` / `w1` | generated `post_read` returns `val & ~writeonly_mask` |
| `onwrite = woset/wot/wzs/wzc/wzt/wclr/wset` | generated `pre_write` |
| `onread = rset` | generated `post_read` ORs bits back into storage |
| `singlepulse` | `post_write` calls the user hook, then clears the bits |
| WO + RO regs at the same address | one `RegisterAccessInfo` named `<W>_<R>`; `uint32_t shadow_<r>` |

MMIO is 32-bit only (`MemoryRegionOps.valid.min_access_size =
max_access_size = 4`). QEMU's register helpers match by exact address, so
byte accesses at `reg+1` cannot be served correctly.

Still rejected (clear `error:` with file:line, no traceback):

- `onwrite = wuser`, `onread = ruser`
- true overlaps that are not a WO/RO pair
- `regwidth != 32`, `mem`, `alias`, counters, nested addrmaps, `external` children

## User-defined properties

Registered as **hard** UDPs by the plugin, so they can be assigned in RDL
without an include:

| UDP | Component | Type | Meaning |
|---|---|---|---|
| `qemu_irqs` | addrmap | longint | sysbus IRQ count (default 0, or 1 if any field has `intr`) |
| `qemu_read_hook` | reg | boolean | also generate a read hook |
| `qemu_no_write_hook` | reg | boolean | skip the write hook on a writable register |

`src/peakrdl_qemu/qemu_udps.rdl` is shipped for callers who compile with
`systemrdl-compiler` directly. Do not compile it together with the plugin's
hard UDPs.

## Hook contract

Implemented in `<dev>_behavior.c`. A missing hook is a **link error**.

```c
void <dev>_behavior_init(<Dev>State *s);              /* realize */
void <dev>_behavior_reset(<Dev>State *s);             /* after register_reset */
void <dev>_<reg>_write(<Dev>State *s, uint32_t val);  /* each writable reg */
uint32_t <dev>_<reg>_read(<Dev>State *s, uint32_t val); /* qemu_read_hook only */
```

Generated `post_write` / `post_read` wrappers obtain device state from
`reg->opaque` and call these hooks. Hardware-writable fields (`hw = w`,
`hwset`, `hwclr`) are updated from behaviour code with `FIELD_DP32` /
`ARRAY_FIELD_DP32`.

Shared-pair reads come from `s->shadow_<readreg>`. Behaviour writes that
value directly; `FIELD_EX32`/`FIELD_DP32` work on it because
`FIELD(<R>, …)` is emitted without a second `REG32`.

To migrate extra state, define `<DEV>_BEHAVIOR_HAS_VMSTATE` in the
behaviour header and provide `vmstate_<dev>_behavior`.

## Overwrite policy

| File | Policy |
|---|---|
| `*_regs.h`, `*.h`, `*_gen.c`, snippets | always overwritten |
| `*_behavior.h`, `*_behavior.c` | never overwritten if they exist |

Regeneration is deterministic: two runs produce byte-identical generated files.

On regeneration, if `*_behavior.c` already exists, the exporter prints
`NEW HOOK: <signature>` for declared hooks missing from the file and
`STALE HOOK: <name>` for functions that are no longer declared. New stubs
are written to `<dev>_behavior.new_hooks.c` (the original file is not
touched). A missing hook is still a link error.

## Development

```shell
pytest                          # unit + golden tests
peakrdl qemu --help
```

CI (`.github/workflows/phase1.yml` and `ci/Dockerfile`) installs the package,
runs pytest, generates `simple_timer`, applies it to the pinned QEMU, rebuilds
with `--enable-werror`, and runs the smoke check.

## License

- Tool code: **MIT** (see [`LICENSE`](LICENSE))
- Generated C: `SPDX-License-Identifier: GPL-2.0-or-later` by default
  (overridable with `--license`) because it links into QEMU
Phase 1 (M0–M2) plus M3 generates:
## Mapping table (M0–M5)
| `reg X[N] @ off` | expanded to `X_0` … `X_{N-1}` (`X_i_j` for 2-D) |
| `regfile GRP { … } @ off` | flattened with prefix (`GRP_R0`) |
| array of regfiles | flattened (`BANK_0_V`, `BANK_1_V`) |
