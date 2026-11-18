---
name: fpga-module
description: Use when adding or changing a Verilog/SystemVerilog module in an FPGA project, including writing its self-checking testbench. Covers file layout, synthesisable coding rules, parameters for fast simulation and the forge_tb.vh test macros.
---

# Add or change an RTL module (with its testbench)

## Files

- Design: `src/<module>.v`, one module per file, first line `` `timescale 1ns / 1ps ``.
- Test: `tb/<module>_tb.v`, module `<module>_tb`. `forge.py sim` runs every `tb/*_tb.v`.
- Before writing a UART, debouncer, display driver, FIFO, RAM or PWM, check `forge.py lib`:
  reuse the tested module (add its name to `lib = [...]` in `forge.toml`).

## RTL rules

- Parameterise time: `parameter integer CLK_HZ = <board clock>` and derive counts from it
  (`localparam integer TICKS = CLK_HZ / 1000;`). Tests then run with a small `CLK_HZ`.
- One clock domain; slow events through enables (`lib/tick_gen`), not derived clocks.
- Sequential logic: `always @(posedge clk)` with non-blocking `<=`.
  Combinational: `always @*` with blocking `=` and a default for every output (no latches).
- Size counters with `$clog2`; give registers initial values (`reg [7:0] count = 0;`).
- No `#` delays, `initial` stimulus or `$display` in `src/`.
- Asynchronous inputs need a 2-flop synchroniser (`(* ASYNC_REG = "TRUE" *)`) or `lib/debounce`.

## Testbench pattern

```verilog
`timescale 1ns / 1ps
module counter_tb;
    reg clk = 1'b0;
    reg rst = 1'b1;
    wire [3:0] count;

    counter #(.CLK_HZ(1_000)) dut (.clk(clk), .rst(rst), .count(count));   // tiny clock = fast test

    `include "forge_tb.vh"
    `TEST_TIMEOUT(1_000_000)          // fail instead of hanging

    always #5 clk = ~clk;

    initial begin
        repeat (2) @(posedge clk);
        rst <= 1'b0;                   // non-blocking: the DUT still sees rst=1 at this edge
        repeat (3) @(posedge clk);
        #1;
        `CHECK_EQ(count, 4'd3, "counts three clocks after reset")
        `TEST_DONE                     // prints TEST PASSED / TEST FAILED, calls $finish
    end
endmodule
```

- Check behaviour that matters (values, timing, edge cases, reset, overflow, back-to-back
  operations), not just that something toggles.
- **Avoid races at the clock edge.** After `@(posedge clk)`, drive DUT inputs with
  non-blocking `<=` (or wait `#1` first), and sample outputs after `#1`. A blocking `=` right
  at the edge makes the result depend on the simulator: this exact example passes on Icarus
  and fails on xsim if `rst <= 1'b0` is written `rst = 1'b0`.
- Model external devices in the testbench (a UART sender, an SPI slave) instead of poking
  internal signals where possible.

## Run

```
python scripts/forge.py sim <module>_tb --json
python scripts/forge.py sim --simulator iverilog      # quick second opinion if Icarus is installed
```

A test passes only with `TEST PASSED` and no `CHECK FAILED` / `Error:` lines. On failure follow
the `fpga-debug-sim` skill. When the module is used by the top, run `forge.py check` too.
