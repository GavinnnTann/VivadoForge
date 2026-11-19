# Simulation and testbenches

Simulate every module before you build: a simulation takes seconds and shows every signal; a
build takes minutes and a board shows almost nothing.

## Running

```sh
python scripts/forge.py sim                    # every tb/*_tb.v
python scripts/forge.py sim counter_tb         # one testbench
python scripts/forge.py sim --wave             # also record waveforms
python scripts/forge.py sim counter_tb --gui   # record and open the waveform viewer
python scripts/forge.py sim --simulator iverilog
python scripts/forge.py sim --lib uart_rx      # the tests of a lib/ module
```

Each testbench is compiled with all project sources and lib modules, in its own folder
`<build folder>/sim/<testbench>/` (log: `sim.log`, waves: `waves.wdb` for xsim or `waves.vcd`
for Icarus).

## Pass or fail

A testbench **passes** only when its output contains `TEST PASSED` and none of `TEST FAILED`,
`CHECK FAILED`, `Error:` or `Fatal:`. The exit code of the simulator is not trusted on its own:
Vivado's xsim exits successfully even after `$fatal`. Other outcomes:

| Status | Meaning |
|---|---|
| `error` | did not compile or elaborate (see the first `ERROR:` line) |
| `timeout` | never reached `$finish` within `[sim].timeout` seconds |
| `no_verdict` | finished without printing `TEST PASSED` (missing `` `TEST_DONE ``) |

## Writing a self-checking testbench

`lib/include/forge_tb.vh` is on every testbench's include path:

```verilog
`timescale 1ns / 1ps
module debounce_demo_tb;
    reg clk = 1'b0;
    reg btn = 1'b0;
    wire pressed;

    // Shrink the clock so 10 ms of debounce is only 100 cycles
    debounce #(.CLK_HZ(10_000), .DEBOUNCE_MS(10)) dut (
        .clk(clk), .btn_in(btn), .level(), .pressed(pressed), .released());

    `include "forge_tb.vh"
    `TEST_TIMEOUT(100_000_000)        // ns; the test fails instead of hanging

    always #50_000 clk = ~clk;        // 10 kHz

    integer presses = 0;
    always @(posedge clk) if (pressed) presses = presses + 1;

    initial begin
        btn = 1'b1; #20_000_000; btn = 1'b0; #20_000_000;
        `CHECK_EQ(presses, 1, "one press")
        `TEST_DONE
    end
endmodule
```

| Macro | Use |
|---|---|
| `` `CHECK(condition, "message") `` | fails the test (and keeps going) when the condition is false |
| `` `CHECK_EQ(actual, expected, "message") `` | same, and prints both values; uses `!==` so X and Z count as wrong |
| `` `TEST_TIMEOUT(ns) `` | at module level: fail if the test runs longer than this |
| `` `TEST_DONE `` | prints `TEST PASSED (n checks)` or `TEST FAILED (...)` and calls `$finish` |

## Habits that make tests useful

- **Parameterise time.** Give modules a `CLK_HZ` parameter (and baud rates, delays) and
  instantiate them in the testbench with small values. A simulated second at 100 MHz is 100
  million cycles; at `CLK_HZ = 1_000` it is a thousand.
- **Check, don't print.** Every important behaviour gets a `CHECK`. Printing values for a
  person to read is not a test.
- **Model the outside world.** Drive a UART line bit by bit, model the SPI slave, bounce the
  button. The `lib/*/*_tb.v` files show how.
- **No races at the clock edge.** After `@(posedge clk)`, drive inputs with non-blocking `<=`
  (or `#1` first), and check registered outputs after `#1`. A blocking `rst = 0` exactly at the
  edge can pass on one simulator and fail on another, because scheduling order decides whether
  the design sees the old or the new value.
- **Test the edges.** Reset, the first and last value, overflow, back-to-back operations,
  inputs arriving at awkward moments.
- **`timescale 1ns / 1ps` in every file.** Simulators disagree on the default (Icarus uses
  1 s), so `forge.py check` warns when it is missing.

## The two simulators

| | xsim (Vivado) | Icarus Verilog |
|---|---|---|
| Speed | about 15 s per testbench (tool start-up) | under a second |
| Languages | Verilog, SystemVerilog, VHDL, mixed | Verilog, most SystemVerilog, no VHDL |
| Xilinx primitives (BUFG, MMCM, ...) | yes (`unisims_ver` and `glbl` are added automatically) | no |
| Waveforms | `waves.wdb`, opens in the Vivado viewer | `waves.vcd` for GTKWave, Surfer or VS Code viewers |

`simulator = "auto"` uses xsim when Vivado is installed. Treat xsim as the reference: it is
Vivado's own simulator, it simulates Xilinx primitives, and its language support is closest to
what Vivado accepts. Icarus is a fast second opinion and runs in CI where Vivado is not
available. Either way, simulation checks the RTL against your testbench; it does not prove what
synthesis builds. Mismatches come from incomplete sensitivity lists, unintended latches and
`x` values that simulation resolves one way and hardware another, so read the build's warnings
and test on the board.
