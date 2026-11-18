# AGENTS.md: working in a VivadoForge FPGA project

This repository is an FPGA project for AMD Vivado, driven by one command-line tool:
`python scripts/forge.py` (`python3` on Linux/macOS). You can write RTL, simulate it, build a
bitstream and read the results without opening Vivado. Programming the physical board needs a
person's approval.

Hardware mistakes are silent until something on a desk misbehaves, so follow the rules below
exactly. Step-by-step procedures for common tasks are in `.claude/skills/*/SKILL.md`; read the
matching one before you start (index at the end).

## Start every task by looking, not guessing

```
python scripts/forge.py info --json     # project, board, FPGA part, clock, tools, last build
python scripts/forge.py board --json    # peripherals, pin names, active-low/high, notes
```

Then read `forge.toml` and the top module named there.

## Rules

1. **Never invent a pin.** Pins come only from `boards/<board>/master.xdc`. Add them with
   `python scripts/forge.py pins add <board port or role>=<design port>`; never type a
   `PACKAGE_PIN` yourself. `forge.py check` rejects pins that are not on the board.
2. **Use the real clock.** Read the frequency from `forge.py info`. The Cmod A7 and the SUTD
   kit run at 12 MHz, the others at 100 MHz. Compute counts from a `CLK_HZ` parameter; never
   hard-code a count for an assumed frequency.
3. **Check polarity** of every LED, button, switch and display signal (`forge.py board`). The
   Basys 3 7-segment display is active-low; the SUTD kit's segments are active-high.
4. **One clock.** Make slow events with clock enables (`lib/tick_gen`), never by dividing the
   clock into a new clock signal or by clocking flip-flops from logic.
5. **Synchronise every asynchronous input** (buttons, switches, UART RX, external chips) with
   two flip-flops; debounce buttons (`lib/debounce` does both).
6. **Write synthesisable RTL** in `src/`: Verilog-2001 (`.v`) unless the project already uses
   SystemVerilog. No `#` delays or `$display` logic in design files. In `always @*` blocks give
   every output a default so no latches are inferred.
7. **Test every module you write** with a self-checking testbench `tb/<module>_tb.v` that uses
   `forge_tb.vh` (`CHECK`, `CHECK_EQ`, `TEST_TIMEOUT`, `TEST_DONE`). A testbench that only prints
   values is not a test. Make time constants parameters so the testbench can run with a tiny
   `CLK_HZ`.
8. **Order of work:** `check`, then `sim`, then `build`. Do not build while tests fail.
9. **Read the build result** (`forge.py report --json`): errors, critical warnings, timing (WNS
   must be >= 0) and utilisation. Negative slack or an unexplained critical warning means the
   work is not done.
10. **Never program or flash the board on your own.** Run `forge.py program` or `forge.py flash`
    only after a person in this conversation has explicitly said yes for this design, and only
    then add `--yes`. Flash is persistent: the board boots that design at every power-up. The
    same applies to programming Tcl sent through an MCP server.
11. **Report exactly what was verified.** "Simulation passed", "bitstream built with timing met"
    and "works on the board" are three different claims. Only a person can confirm the last one.
    Never write that a design works because it built.
12. **Do not edit** `boards/` (the pin authority, changes need a person), anything in the build
    folder (generated), or `forge.local.toml` (per-machine). If you change a module in `lib/`,
    update and rerun its testbench (`forge.py sim --lib <name>`).

## Commands

| Goal | Command | Notes |
|---|---|---|
| Overview | `forge.py info --json` | start here |
| Board facts | `forge.py board [--pins] --json` | roles, polarity, every pin |
| Validate | `forge.py check --json` | config, top module, every port pinned, clock constraint; seconds, no Vivado |
| Simulate | `forge.py sim [name ...] --json` | runs `tb/*_tb.v`; `--wave` records waveforms, `--simulator iverilog` for a fast run |
| Library tests | `forge.py sim --lib [module ...]` | tests of the `lib/` modules |
| Build | `forge.py build --json` | runs `check` first; 2-10 minutes |
| Last result | `forge.py report --json` | timing, utilisation, messages with file:line |
| Add pins | `forge.py pins add btn[0]=start led=status` | copies lines from the board master, renames, adds `create_clock` for the clock |
| New project | `forge.py new -t <template> -b <board> [--dir D]` | `forge.py templates` lists templates |
| Reusable RTL | `forge.py lib` | tested modules: UART, SPI, debounce, 7-segment, PWM, FIFO, RAM, LFSR, BCD |
| Board present? | `forge.py devices` | read-only JTAG scan |
| Program / flash | `forge.py program --yes` / `forge.py flash --yes` | only after a person approves |

Every command accepts `--json` (the result goes to stdout, progress to stderr) and
`-p <project folder>`. A non-zero exit code means failure.

## Project layout

```
forge.toml            project config: name, top module, board, sources, lib modules, tests
forge.local.toml      this machine only: Vivado path, build folder (git-ignored)
src/                  design RTL (one module per file, file name = module name)
tb/                   testbenches, <module>_tb.v
constraints/          your XDC; lines come from the board master via `forge.py pins add`
boards/<id>/          board.json (part, clock, roles, polarity) + master.xdc (every pin)
lib/<module>/         reusable modules, each with a self-checking testbench
lib/include/          forge_tb.vh testbench macros (on the include path automatically)
templates/            starting projects for `forge.py new`
scripts/forge.py      the CLI; scripts/forge.tcl is the Vivado side
<build folder>/       generated: Vivado project, reports/, reports/summary.json, sim/<test>/sim.log
```

## Conventions

- Put `` `timescale 1ns / 1ps `` on the first line of every Verilog file.
- Ports: `clk`; active-low signals end in `_n`; buses are `[N-1:0]`.
- Resets: FPGAs initialise registers from their declarations (`reg [7:0] q = 0;`), so most
  designs need no reset. If you need one, make it synchronous.
- Use `lib/` modules instead of rewriting UARTs and debouncers. Each file's header comment
  documents its ports and parameters.
- Memory initialisation files (`.mem`, `.hex`): list them in `[project].sources` and refer to
  them by bare file name in `$readmemh`.
- Keep the top module thin: it connects board pins to submodules and applies polarity.

## Reading results

- `check`: findings with `severity`, `code`, `message`, `file`, `line` and `hint`. Fix every error.
- `sim`: one result per testbench with `status` (`passed`, `failed`, `error` = did not compile,
  `timeout`, `no_verdict` = no `TEST_DONE`), the failing lines and the log path.
- `build`: `status` is `passed`, `timing_failed` or `failed`, plus `stage`, `errors`,
  `critical_warnings` (each with file and line when Vivado gives one), `timing` (`wns`, `tns`,
  `whs`, `met`), `utilization`, `methodology`, `notes` and `bitstream`. Messages marked
  `benign` are routine Vivado notices.

## Vivado through MCP (optional)

If a Vivado MCP server is connected (AMD's official Ross `vivado-mcp`, or the community
`vivado-mcp`), use it for interactive inspection after a build. Keep using `forge.py` for check,
sim and build so results stay reproducible:

```tcl
source scripts/forge.tcl
forge::load <build folder>/forge_context.tcl
forge::open_routed        ;# routed design of the last build
forge::worst_paths 10     ;# critical paths as text
```

Setup: `docs/agents.md`. Programming Tcl (`program_hw_devices`, `program_hw_cfgmem`) is covered
by rule 10.

## Skills (procedures in `.claude/skills/`)

| Skill | Use it when |
|---|---|
| `fpga-design` | a person describes a system to build ("make a stopwatch on the Basys 3") |
| `fpga-module` | adding or changing an RTL module and its testbench |
| `fpga-pins` | connecting a peripheral, Pmod or header pin, or moving to another board |
| `fpga-debug-sim` | a testbench fails, hangs or prints no verdict |
| `fpga-fix-build` | `build` fails or reports critical warnings / DRC problems |
| `fpga-timing` | timing is not met (negative WNS/TNS) |
| `fpga-program` | the person wants the design on the board |
| `fpga-add-board` | adding support for a board that is not in `boards/` |
