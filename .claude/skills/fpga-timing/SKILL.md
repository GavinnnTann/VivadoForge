---
name: fpga-timing
description: Use when a build reports timing not met (negative WNS or TNS, status timing_failed), timing incomplete or unconstrained (status unverified), or when asked to make a design run faster. Find the critical path and fix the RTL; never hide violations with constraints.
---

# Close timing

A design with negative slack may work on the bench today and fail tomorrow (temperature,
another board). Fix it.

## 1. Read the numbers

```
python scripts/forge.py report --json
```

`timing.wns` < 0 means setup failure; `timing.whs` < 0 means hold failure (rare in single-clock
designs: suspect a gated or derived clock). `verification.timing` is `incomplete` when
`timing.checks.no_clock` > 0: some registers have no clock constraint, usually a clock divided
in logic (use a clock enable from `lib/tick_gen` instead) or a clock input without
`create_clock`. `unconstrained` means no clock constraint at all. Fix those first: until then
the WNS says nothing about the unclocked registers.

## 2. Find the critical path

Open `reports.timing` (`<build folder>/reports/timing.rpt`): the "Max Delay Paths" section lists
the worst paths with source, destination and logic levels. With a Vivado MCP session you can
dig deeper:

```tcl
source scripts/forge.tcl
forge::load <build folder>/forge_context.tcl
forge::open_routed
forge::worst_paths 10
```

## 3. Typical causes and fixes

| Pattern on the path | Fix |
|---|---|
| wide arithmetic chain (multiply, divide, `%`, long adders) | pipeline it (register halfway), or compute over several cycles (see `lib/bin2bcd`) |
| `/` or `%` by a non-power-of-two | avoid in hardware: count in the target base (BCD counters) or precompute |
| many logic levels from a big `case`/`if` chain | register intermediate results; one-hot state encoding |
| path between two clock domains | it should not be timed: add a proper synchroniser and constrain the crossing |
| huge fan-out from a single register | duplicate the register or pipeline the enable |
| path through a block RAM output | use the RAM's registered output (one more cycle of latency) |

Prefer RTL changes. Do not add `set_false_path`/`set_multicycle_path` unless you can explain
exactly why the path is not real or has more than one cycle, and write that reason in the XDC.
Do not loosen `create_clock`: the period comes from the board.

## 4. Re-verify

Rerun `forge.py sim`: pipelining changes latency, so testbench expectations may need updating
for a real reason. Then `forge.py build`. Report WNS before and after.
