---
name: fpga-debug-sim
description: Use when forge.py sim reports a failed, erroring, hanging (timeout) or no_verdict testbench, or when simulation results look wrong. Systematic procedure to find whether the design or the testbench is at fault.
---

# Debug a failing simulation

```
python scripts/forge.py sim <test> --json
```

Read `status`, `failures` and `log` (the full log is `<build folder>/sim/<test>/sim.log`).

## By status

- **error**: it did not compile or elaborate. The first `ERROR:` line has the file and line.
  Common causes: a missing module (add its file to `sources` or its name to `lib`), a typo in a
  port name, a SystemVerilog keyword in a `.v` file (`logic`, `bit`, `expect`), a missing
  `` `include "forge_tb.vh" ``.
- **no_verdict**: the testbench finished without `TEST_DONE`. Make sure the main `initial`
  block ends with `` `TEST_DONE ``.
- **timeout**: `$finish` was never reached. Usually the testbench waits for an event that never
  comes (`@(posedge done)` when `done` never pulses). Add `` `TEST_TIMEOUT(<ns>) `` and print
  progress, then work out why the event is missing.
- **failed**: a `CHECK` failed or an `Error:`/`Fatal:` line was printed. Read the first failure:
  later ones are often consequences.

## Method

1. Reproduce with one test: `forge.py sim <test>`.
2. State what you expected at the failing check and why (from the spec, not from the code).
3. Decide who is wrong, the design or the test: re-derive the expected value by hand. Tests
   with wrong expectations are common, but do not "fix" a test just to make it pass.
4. Look inside: `forge.py sim <test> --wave` records every signal (`--gui` opens the viewer). Or
   temporarily add `$display` lines with `$time` in the testbench around the failure.
5. Common design bugs: off-by-one counters (`== N` vs `== N-1`), blocking `=` in clocked
   blocks, missing defaults in `always @*` (latches, X values), reading a register in the same
   cycle it is written, wrong polarity, unsynchronised inputs, a width mismatch truncating a
   value (check widths of constants such as `8'd300`).
6. Fix one thing, rerun the single test, then run the whole suite: `forge.py sim`.
7. If the test was slow, shrink `CLK_HZ`/timing parameters in the testbench instance rather
   than simulating real seconds.

Get a second opinion from the other simulator (`--simulator iverilog` or `--simulator xsim`)
when behaviour looks simulator-specific. The design must pass on xsim, since that matches
Vivado's synthesis.
