# VivadoForge Roadmap

**Describe it. Build it. Verify it.**

VivadoForge makes FPGA development with AMD Vivado accessible from VS Code, the command line and
AI coding agents. A person describes the digital system they want; an agent (or the person)
writes the RTL, and VivadoForge checks, simulates, builds and reports on it with Vivado. A person
always approves before anything is programmed onto hardware.

It does not replace Vivado or hide hardware engineering. It removes friction: project setup,
pin bookkeeping, GUI navigation and log reading. It keeps every step transparent: the RTL,
constraints, test results and reports are plain files.

*Last updated 2026-11-19 (v0.2.0).*

---

## 1. Status at a glance

| Stage | Goal | Status |
|---|---|---|
| 1. Agent-readable project | an agent can understand and build the project without guessing | **Done** |
| 2. Vivado toolchain access | agents run Vivado operations and read structured results | **Done via `forge.py`**; MCP integration documented, Ross not yet tested end-to-end |
| 3. FPGA workflows | repeatable procedures for common tasks | **Done** (8 skills) |
| 4. Vision-driven development | natural-language spec to verified bitstream | **In place** (`fpga-design` skill); evaluation not yet run |
| Hardware verification | `program`/`flash` of v0.2 on real boards | **Open**: needs a person with boards |

---

## 2. Principles

1. **Vivado is the authority** for synthesis, implementation, timing and bitstreams.
   VivadoForge orchestrates it and never re-implements it.
2. **The project owns the durable layer**: board data, conventions, checks, workflows and the
   command interface. Integrations such as MCP servers are replaceable.
3. **Facts are machine-readable.** Board, clock, pins, polarity, test verdicts and build
   results are structured data, so agents read them instead of inferring them.
4. **Verification is explicit and layered.** Simulation passed, bitstream built with timing
   met, and works on the board are different claims, reported separately.
5. **Hardware safety is enforced by tools**, not only by instructions: approval gates, pin
   validation, protected board files.

---

## 3. Architecture

```
Layer 1  Intent and agent     person, VS Code tasks, GUI, Copilot / Claude Code / Codex / Cursor
                              AGENTS.md (rules), .claude/skills (procedures)
                                         |
Layer 2  VivadoForge          scripts/forge.py  - the one interface (CLI + --json)
                              forge.toml, boards/<id>/{board.json, master.xdc}, lib/, templates/
                              check (pins, clock, config) | sim (xsim, Icarus) | build | program
                              scripts/forge.tcl - Vivado-side procedures (batch and MCP sessions)
                                         |
Layer 3  Toolchain            Vivado batch mode; optionally a live Vivado through an MCP server
                              (AMD Ross vivado-mcp, community vivado-mcp)
```

`forge.py` is the contract for every caller. An MCP server is an optional second door into
Vivado for interactive inspection (critical paths, netlist, hierarchy). It can source
`forge.tcl` and reuse the same context, but builds stay in `forge.py` so their results are
reproducible.

---

## 4. Decisions

| # | Decision | Why |
|---|---|---|
| D1 | A stdlib-only Python CLI (`forge.py`) with `--json` on every command is the agent interface | Works with every agent and editor, with or without MCP; testable; cross-platform |
| D2 | `forge.toml` (project) and `board.json` (board) are the only sources of truth; Vivado gets a generated `forge_context.tcl` | Nothing to keep in sync by hand (the old `config.tcl`/`build.ps1` duplicated the project name and paths) |
| D3 | Pins come only from the vendor's master XDC (Digilent, MIT), through `forge.py pins add`; `check` rejects anything else | "Never invent pins" enforced by the tool. The old hand-written reference XDCs had wrong I/O standards (Nexys A7 switches) |
| D4 | AMD Ross is the primary Vivado MCP; the community `vivado-mcp` (Apache-2.0) is the fallback; coreyhahn/vivado_mcp is dropped | Ross is official (launched Sept 2026) and maintained monthly. coreyhahn's server uses pexpect and is unlikely to run on Windows |
| D5 | `AGENTS.md` is the canonical instruction file; `CLAUDE.md` and Copilot instructions point to it; procedures use the Agent Skills format in `.claude/skills/` | One source of truth read by every major agent; the same skill format AMD uses for Ross |
| D6 | `program`/`flash` need a real-console "yes" or `--yes`; `--json` never prompts; Claude Code permissions ask before program/flash/`boards/` edits | Instructions alone can be ignored; the gate cannot |
| D7 | Tests are self-checking (`forge_tb.vh`), and verdicts come from output, not exit codes | xsim exits 0 after `$fatal`; tests that print values without checking them prove nothing |
| D8 | Failed timing fails the build by default (`[build].timing = "error"`) | A bitstream with negative slack is not a finished design |
| D9 | Vivado project mode, regenerated from `forge.toml` on every build, in a marker-protected build folder | Standard reports, GUI-openable project, nothing generated in git, `clean` can never delete user files |
| D10 | Python 3.11+, Vivado 2023.1+, Windows first but tested paths for Linux | Python 3.10 reached end-of-life in Oct 2026; the template's users are mostly on Windows |
| D11 | `program`/`flash` refuse a bitstream whose recorded inputs (`reports/manifest.json`) differ from the current sources; `forge::program`/`flash` run only when started by `forge.py` | An existing bitstream is not the current design. Without this, "edit, forget to rebuild, program" loads the old design silently |
| D12 | `passed` means verified: bitstream, timing analysed and met (or no clocked logic), DRC clean, every critical warning benign or waived with a person's reason. Anything less is `unverified` with `reasons` | A missing timing report or an unexplained critical warning must never read as success to an agent |

---

## 5. Scope and non-goals

**In scope:** AMD/Xilinx 7-series boards (Artix-7 today); Verilog, SystemVerilog and VHDL RTL
projects; simulation with xsim and Icarus; synthesis, implementation, bitstream, JTAG
programming and SPI flash; agent workflows.

**Not now:** Zynq/MPSoC software flows (Vitis), block designs (`.bd`), IP-heavy designs (`.xci`
works in builds but is experimental and not simulated), multi-clock CDC verification, formal
verification, and non-AMD toolchains.

---

## 6. Stage details

### Stage 1: Agent-readable project (done)

- [x] `AGENTS.md`, `CLAUDE.md`, `.github/copilot-instructions.md`
- [x] Standard layout: `forge.toml`, `src/`, `tb/`, `constraints/`, `boards/`, `lib/`, `templates/`
- [x] Machine-readable boards: `board.json` (part, clock, flash, roles, polarity) + vendor `master.xdc`
- [x] `forge.py info/board/pins --json` expose part, clock, pins and polarity
- [x] Deterministic commands: `check`, `sim`, `build`, `report`, `program`, `flash`, `devices`
- [x] Validation: config schema with typo detection, top module, every port pinned with an I/O
      standard, pins exist on the board, no duplicate pins, `create_clock` matches the board clock,
      port direction matches the board wiring, `_n` names only on active-low peripherals
- [x] Fixed the old inconsistencies: hard-coded project name in `build.ps1`, `simulate.tcl`
      ignoring the config, the Tcl inline-comment bug, the wrong flash-size comment, the
      committed private config, and builds that reported success with failing timing

### Stage 2: Vivado toolchain access

- [x] Evaluated the Vivado MCP options (section 8)
- [x] Batch Vivado orchestration with structured results (`reports/summary.json`: status,
      stage, errors and critical warnings with file:line, WNS/TNS/WHS, utilisation, DRC,
      methodology)
- [x] Build verdicts that separate "bitstream exists" from "verified" (`verification`, `reasons`,
      status `unverified`), `[build.waive]` for reviewed critical warnings, stable error `code`s
- [x] Build manifest: `program`/`flash` refuse a stale bitstream; `info`/`report` show `up_to_date`
- [x] `forge.tcl` usable from an MCP session (`forge::load`, `forge::open_routed`, `forge::worst_paths`);
      its `program`/`flash` refuse to run there, and every hardware error path closes the session
- [x] MCP setup documented for Claude Code and VS Code (`docs/agents.md`)
- [x] Simulation, synthesis, implementation, timing and utilisation on Vivado 2023.1 for all 5 boards
- [ ] Test AMD Ross end-to-end with this template (needs a supported Vivado; Ross is tested against 2026.1)
- [ ] Test `program` and `flash` of v0.2 on a Cmod A7, then the other boards

### Stage 3: FPGA workflows (done)

- [x] `fpga-module`: new RTL module and testbench
- [x] `fpga-debug-sim`: failing, hanging or verdict-less simulations
- [x] `fpga-fix-build`: build errors, critical warnings, DRC
- [x] `fpga-timing`: timing closure without hiding violations
- [x] `fpga-pins`: peripherals, Pmods, headers, moving boards
- [x] `fpga-add-board`: new boards from vendor files
- [x] `fpga-program`: programming with approval
- [x] Reusable tested RTL: `tick_gen`, `debounce`, `seven_seg`, `pwm`, `uart_tx`, `uart_rx`,
      `spi_master`, `fifo_sync`, `ram_sp`, `lfsr`, `bin2bcd`
- [x] Starter templates: `blink`, `button_counter`, `uart_echo`, `reaction_timer`

### Stage 4: Vision-driven development

- [x] `fpga-design` skill: spec, architecture, RTL and tests, pins, check, sim, build, report, approval
- [x] The PLAN's reaction-timer example exists as a template, simulates on 3 boards and builds on 2
- [ ] Run the evaluation in section 9 with real users and agents
- [ ] Collect failure cases from the evaluation into skills and checks

### Next (backlog)

- I2C master and VGA timing modules (with tests); a stopwatch template
- More boards (Cmod A7-15T, Arty S7, Zybo PL-only, Basys 3 variants); community board reports
- `forge.py lint` (Verilator lint or `xvlog` checks without elaboration)
- `check`: flag every XDC `get_ports` that matches no design port, wildcards included (today only
  lines with a `PACKAGE_PIN` are checked, so a stray `set_property PULLDOWN` reaches Vivado as
  `Common 17-55`)
- IP support in simulation (`.xci` simulation sources)
- Simple CDC helper modules (`sync_bit`, `pulse_sync`) and a skill for multi-clock designs
- Optional hardware-in-the-loop check: UART loopback test after `program`, with approval
- Ross-specific skill: interactive timing debug through `vivado_execute`

---

## 7. Risks and mitigations

| Risk | Mitigation in place |
|---|---|
| Wrong clock assumption | Clock in `board.json`; templates take `CLK_HZ` from it; `check` compares `create_clock` with the board |
| Invented or wrong pins | Vendor master XDC only; `pins add`; `check` rejects unknown and duplicate pins and I/O-standard mismatches |
| Wrong port direction (driving a button, reading an LED) | `dir` per role in `board.json`; `check` rejects a port that points against the board wiring |
| Polarity mistakes | `active_low` per role in `board.json`; templates pass it as parameters; `forge.py board` shows it; `check` warns about `_n` names on active-high peripherals |
| Bouncing / asynchronous inputs | `lib/debounce` (synchroniser + debounce); rule 5 in AGENTS.md |
| Timing failures shipped | Build fails on negative slack by default; unconstrained or partly unclocked designs are `unverified`, not `passed`; `fpga-timing` skill |
| "It built, so it works" | `verification` block in every summary (hardware always `not_tested`); `passed` only when verified; layered verification language in AGENTS.md |
| Stale bitstream programmed | Build manifest; `program`/`flash` refuse with `stale_bitstream` and list what changed |
| Agent programs hardware unasked | Console/`--yes` gate; `--json` never prompts; Claude Code `ask` rules; rule 10 |
| Arbitrary Tcl through MCP | `forge::program`/`flash` refuse outside `forge.py`. Raw Tcl (`program_hw_devices`) is outside forge's control: documented as relying on the client's tool approval (Ross has no gate of its own); Claude Code hooks are not relied on because their `ask` decisions are reported as not enforced in every mode |
| Build output destroys files | Build folder marker: forge refuses to use or delete folders it did not create |
| OneDrive / sync folders | `check` warns; `forge.local.toml` `build_dir` outside the synced folder |

---

## 8. Vivado MCP landscape (researched 2026-11-18)

| Option | Licence | Windows | Notes |
|---|---|---|---|
| [AMD Ross](https://github.com/Xilinx/ross-ai-assistant) `vivado-mcp-server` | skills MIT; server binary from AMD | listed | Official. `vivado_execute` (any Tcl), session tools, attach to a running GUI via `webserver`; skills for simulation, lint, timing methodology, ILA/VIO; no Tcl approval gate |
| [mapleleavessssssss-wq/vivado-mcp](https://github.com/mapleleavessssssss-wq/vivado-mcp) | Apache-2.0 | yes | 32 curated tools incl. `xdc_lint`, `check_bitstream_readiness`, `program_device`; docs mostly in Chinese |
| [vivado-mcp-native](https://pypi.org/project/vivado-mcp-native/) | MIT | yes | Windows fork of coreyhahn's; 14 simulation tools; beta |
| [coreyhahn/vivado_mcp](https://github.com/coreyhahn/vivado_mcp) | MIT | unlikely (pexpect) | 5 commits, last Feb 2026: dropped |
| [Xilinx FPL'26 VivadoMCP](https://github.com/Xilinx/fpl26_optimization_contest/tree/main/VivadoMCP) | Apache-2.0 | n/a | Contest example for checkpoint timing optimisation; reference only |

Re-check this table before relying on it: the field moves monthly.

---

## 9. Measuring success

Give users a supported board and three tasks of increasing difficulty, described in natural
language:

| Level | Task | Concepts |
|---|---|---|
| Beginner | LED pattern that changes with a switch | clocks, counters, GPIO, polarity |
| Intermediate | stopwatch on the 7-segment display | FSM, debouncing, display multiplexing, BCD |
| Advanced | UART-controlled PWM brightness | serial protocol, parsing, timing |

Run each task twice: with VivadoForge (agent + forge.py) and with a baseline (the same agent in
a plain Vivado project). Measure completion rate, time to a working board, human
interventions, agent errors by type (pins, clock, polarity, timing, logic), sim/build/hardware
pass rates, and user confidence. Without the baseline, improvements cannot be attributed to
VivadoForge.

---

## 10. Open questions

1. **Name.** "Vivado" is an AMD trademark. The README states that the project is independent and
   not affiliated with AMD. Before wider promotion, check AMD's trademark guidelines, and
   consider a name such as "Forge for Vivado" or a neutral one.
2. **Hardware verification.** Who will run `program`/`flash` on each board, and how will
   results be recorded (`verified_on_hardware` in `board.json`)?
3. **Ross versions.** Ross is tested against Vivado 2026.1. Is a Vivado upgrade acceptable for
   the course, or does Stage 2 MCP work target the community server on 2023.1?
4. **Course fit.** Should the SUTD kit be the default board for course forks (`forge.py new -b
   sutd_dsl_kit`)?

---

## References

- [VivadoForge repository](https://github.com/GavinnnTann/VivadoForge)
- [AMD Ross agent skills and MCP docs](https://github.com/Xilinx/ross-ai-assistant)
- [Digilent master XDC files](https://github.com/Digilent/digilent-xdc)
- [VS Code MCP servers](https://code.visualstudio.com/docs/agent-customization/mcp-servers)
- [AGENTS.md convention](https://agents.md)
