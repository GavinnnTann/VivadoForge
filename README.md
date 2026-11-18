# VivadoForge

**Describe it. Build it. Verify it.** A template for AMD Vivado FPGA projects that you drive
from VS Code, the command line or an AI coding agent.

- **One command line for the whole flow.** `python scripts/forge.py check | sim | build | program`
  creates the Vivado project, runs it in batch mode and summarises timing, utilisation and
  warnings. You never have to click through the Vivado GUI (but you can open the project in it
  at any time).
- **Pins you can trust.** Board pin data comes from the vendor's official master XDC files.
  `forge.py check` catches unpinned ports, invented pins, wrong clock constraints and duplicate
  pins in seconds, before a Vivado run.
- **Tested building blocks.** UART, SPI, debouncer, 7-segment driver, PWM, FIFO, RAM, LFSR and
  BCD modules, each with a self-checking testbench that runs on Vivado's simulator and on Icarus
  Verilog.
- **Ready for AI agents.** `AGENTS.md`, step-by-step skills, JSON output for every command and
  a hard approval gate before anything touches the hardware. Optional Vivado MCP integration,
  including AMD's official server.

## Quick start

You need [Vivado](https://www.xilinx.com/support/download.html) 2023.1 or newer (the free
Standard edition covers every board here), Python 3.11+ and, ideally, VS Code.

```sh
# 1. Get the template: click "Use this template" on GitHub, or
git clone https://github.com/GavinnnTann/VivadoForge my-fpga-project
cd my-fpga-project

# 2. Find Vivado (writes forge.local.toml, which is never committed)
python scripts/forge.py setup --detect

# 3. Make a project for your board (it starts as blink on the Cmod A7)
python scripts/forge.py boards
python scripts/forge.py new --template blink --board basys3 --force

# 4. Check, simulate and build
python scripts/forge.py check
python scripts/forge.py sim
python scripts/forge.py build

# 5. Plug in the board and program it (asks before touching the hardware)
python scripts/forge.py program
```

On Linux and macOS use `python3`. In VS Code: **Ctrl+Shift+B** builds, **Tasks: Run Test Task**
simulates, and errors appear in the Problems panel with file and line. Prefer buttons? Run
`python scripts/forge_gui.py`.

New to all this? [docs/getting-started.md](docs/getting-started.md) walks through installing
Vivado and drivers, the first build and programming the board.

## Everyday commands

| Command | What it does |
|---|---|
| `forge.py info` | Project, board, clock, tools and last build at a glance |
| `forge.py check` | Validates config, top module, every pin and the clock constraint (seconds, no Vivado) |
| `forge.py sim [test]` | Runs the self-checking testbenches in `tb/` (`--wave`/`--gui` for waveforms) |
| `forge.py build` | Synthesis, implementation, bitstream, then a timing/utilisation/warnings summary |
| `forge.py report` | Shows the last build summary again |
| `forge.py program` / `flash` | Loads the FPGA (volatile) or writes its configuration flash (persistent) |
| `forge.py pins add btn[0]=start` | Copies a pin from the board's master XDC into your constraints, renamed |
| `forge.py board` | The board's peripherals with pin names and active-low/high polarity |
| `forge.py new -t <template> -b <board>` | Starts a project: `blink`, `button_counter`, `uart_echo`, `reaction_timer` |
| `forge.py lib` | Lists the reusable modules in `lib/` |
| `forge.py open` | Opens the generated project in the Vivado GUI |

Add `--json` to any command for machine-readable output.

## Project layout

```
forge.toml           the one file you edit: name, top module, board, sources, lib modules
src/  tb/            your design and its testbenches (tb/<module>_tb.v)
constraints/         your pin constraints, filled by `forge.py pins add` / `forge.py new`
boards/              board definitions: board.json + the vendor's master.xdc
lib/                 tested reusable modules + lib/include/forge_tb.vh (testbench macros)
templates/           starting projects for `forge.py new`
scripts/             forge.py (CLI), forge.tcl (Vivado side), forge_gui.py
AGENTS.md            rules and commands for AI coding agents
.claude/skills/      step-by-step workflows (design, pins, debug, timing, program, ...)
docs/                guides
```

Build output (Vivado project, reports, bitstream, simulation logs) goes to `build/` or the
folder set in `forge.local.toml`. It is disposable: `forge.py clean` deletes it.

## Boards

| Board | Id | FPGA | Clock | Tested build (Vivado 2023.1) |
|---|---|---|---|---|
| Digilent Cmod A7-35T | `cmod_a7` | xc7a35tcpg236-1 | 12 MHz | `blink`, timing met |
| SUTD DSL Starter Kit (Cmod A7) | `sutd_dsl_kit` | xc7a35tcpg236-1 | 12 MHz | `reaction_timer`, timing met |
| Digilent Basys 3 | `basys3` | xc7a35tcpg236-1 | 100 MHz | `reaction_timer`, timing met |
| Digilent Arty A7-35T | `arty_a7_35t` | xc7a35ticsg324-1L | 100 MHz | `button_counter`, timing met |
| Digilent Nexys A7-100T | `nexys_a7_100t` | xc7a100tcsg324-1 | 100 MHz | `uart_echo`, timing met |

Every template simulates on every compatible board (checked in CI). The `program` and `flash`
steps of this version have not yet been run on a physical board: their Tcl comes from the
previous scripts, which programmed and flashed a Cmod A7. Hardware reports are welcome. Adding
a board takes two files: [docs/boards.md](docs/boards.md).

## Working with AI agents

Open the folder in VS Code with GitHub Copilot, Claude Code, Codex or Cursor and describe what
you want ("a stopwatch on the Basys 3 that starts and stops with the centre button"). The agent
reads [AGENTS.md](AGENTS.md), follows the skills in `.claude/skills/`, and uses `forge.py` to
check, simulate and build. It reports what was verified and asks before programming the board.
Optional Vivado MCP servers (AMD Ross, community `vivado-mcp`) add interactive inspection of
timing paths and netlists: [docs/agents.md](docs/agents.md).

## Documentation

| Guide | Contents |
|---|---|
| [getting-started.md](docs/getting-started.md) | Install, first build, programming, troubleshooting |
| [configuration.md](docs/configuration.md) | `forge.toml` and `forge.local.toml` reference |
| [simulation.md](docs/simulation.md) | Writing self-checking testbenches, waveforms, simulators |
| [boards.md](docs/boards.md) | Board definitions, pins, polarity, adding a board |
| [agents.md](docs/agents.md) | AI agents, skills and Vivado MCP setup |
| [architecture.md](docs/architecture.md) | How forge.py, forge.tcl and Vivado fit together |
| [PLAN.md](PLAN.md) | Roadmap |

The repository tests itself: `python scripts/forge.py selftest` runs the unit tests, every
`lib/` testbench and every template on every compatible board. CI runs the same with Icarus
Verilog on each push.

## License

MIT, see [LICENSE](LICENSE). The board master XDC files are Digilent's, also MIT
([boards/LICENSE-digilent-xdc.txt](boards/LICENSE-digilent-xdc.txt)).

Vivado is a trademark of Advanced Micro Devices, Inc. This project is independent and not
affiliated with or endorsed by AMD.

Created by Gavin Tan, Singapore University of Technology and Design (SUTD).
