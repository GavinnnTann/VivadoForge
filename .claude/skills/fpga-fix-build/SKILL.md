---
name: fpga-fix-build
description: Use when forge.py build fails (synthesis, implementation or bitstream), or ends "unverified" with critical warnings, DRC problems or missing reports. Maps the common Vivado messages to causes and fixes.
---

# Fix a failing or suspicious build

```
python scripts/forge.py report --json
```

Look at `status`, `stage`, `reasons[]`, `verification`, `errors[]` and `critical_warnings[]`
(each has `id`, `text`, and `file`/`line` when Vivado gives one), `drc[]`, `methodology[]` and
`notes[]`. Full logs are under `logs` in the summary. Fix the first error first.

- `failed`: no bitstream. Fix `errors[]`.
- `unverified`: a bitstream exists, but `reasons[]` names what was not verified: critical
  warnings, DRC violations, unconstrained clocks, or a missing report. Fix each one.
- `timing_failed`: follow the `fpga-timing` skill.

## Before Vivado: `check` failed

`build` runs `forge.py check` first. Fix its findings (pins, clock, top module) rather than
using `--no-check`.

## Common messages

| Message | Meaning | Fix |
|---|---|---|
| `Synth 8-439` module not found | file not in sources | add it to `sources` or its name to `lib` |
| `Synth 8-6156`/`8-87` syntax or semantic error with file:line | RTL error | fix at the given line; run `sim` first next time |
| `Synth 8-327` inferring latch | incomplete `always @*` | default every output at the top of the block |
| `Synth 8-3332` / `8-6014` removed register | logic has no effect on outputs | often a missing connection: check port wiring |
| `Synth 8-5788`/multi-driven net | same signal driven in two always blocks | drive each reg from one block |
| `Common 17-55` 'set_property' expects at least one object | XDC names a port the design does not have | fix the name in the XDC or the RTL |
| `DRC NSTD-1` unspecified I/O standard | port without IOSTANDARD | `forge.py pins add` the port |
| `DRC UCIO-1` unconstrained logical port | port without PACKAGE_PIN | `forge.py pins add` the port |
| `DRC BIVC-1` bank I/O standard conflict | mixed voltages in one bank | use the master's IOSTANDARD |
| `Place 30-574` poor placement for routing between an IO pin and BUFG | clock on a non-clock pin | use the board clock pin or set CLOCK_DEDICATED_ROUTE only if you understand why |
| `Timing 38-282` / timing not met | negative slack | follow the `fpga-timing` skill |
| utilisation over 100 % | design too big | reduce widths and memories, share logic |

Messages marked `benign` in the summary are routine Vivado notices and need no action.

## Critical warnings

A critical warning keeps the status at `unverified`. Do not dismiss it. Most mean the hardware
will differ from simulation: constraints that did not apply, ports optimised away (look for
"removed" plus "driven by constant"), or clock-domain problems. Fix it. If you believe one is
harmless for this design, explain why to the person. Only the person may add it to
`[build.waive]` in `forge.toml` (`"<id>" = "<reason>"`), which lets the build pass and keeps the
reason in the summary.

## Methodology checks

`TIMING-18` (missing input/output delay) is expected for LEDs, buttons and slow I/O. Others,
such as `TIMING-9`/`TIMING-10` (clock-domain crossing) or `LUTAR-1` (logic-driven async reset),
point at real design risks: fix them or explain them.

## After fixing

`forge.py check`, `forge.py sim`, then `forge.py build` again. Report the new timing and
utilisation.
