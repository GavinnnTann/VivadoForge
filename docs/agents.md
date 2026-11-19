# AI agents and Vivado MCP

VivadoForge is built so that an AI coding agent can take a description ("a reaction timer on the
SUTD kit") to a verified bitstream, while a person keeps control of the hardware.

## How an agent works here

1. **Instructions:** [AGENTS.md](../AGENTS.md) holds the rules (never invent pins, use the real
   clock, check polarity, test every module, never program without approval) and the commands.
   Copilot, Codex, Cursor and others read `AGENTS.md`; Claude Code reads it through `CLAUDE.md`;
   `.github/copilot-instructions.md` points there too.
2. **Procedures:** `.claude/skills/*/SKILL.md` are step-by-step workflows: `fpga-design`
   (end-to-end), `fpga-module`, `fpga-pins`, `fpga-debug-sim`, `fpga-fix-build`, `fpga-timing`,
   `fpga-program`, `fpga-add-board`. They are plain Markdown in the open Agent Skills format.
   Claude Code and GitHub Copilot (VS Code and the coding agent) load `.claude/skills/`
   automatically; Codex and other agents find them through the index in `AGENTS.md`.
3. **Tools:** everything goes through `python scripts/forge.py ... --json`. Results are
   structured (findings with file and line, per-test verdicts, build summaries that say what was
   and was not verified, error codes), so the agent reads facts instead of scraping logs.
4. **Guard rails** (see the next section for what each one does and does not cover):
   - `program` and `flash` refuse to run without an interactive "yes" from a person at a real
     terminal, or `--yes`. In `--json` mode they never prompt. `AGENTS.md` allows `--yes` only
     after the person approved in the conversation.
   - `program` and `flash` also refuse a bitstream that does not match the current sources
     (`stale_bitstream`), so an edited-but-not-rebuilt design never reaches the board.
   - A build only reports `passed` when timing was analysed and met, the DRC is clean and no
     critical warning is left unexplained; otherwise it says `unverified` and why.
   - `.claude/settings.json` lets routine commands (info, check, sim, build, report, pins, ...)
     run without prompts, and makes Claude Code ask before `program`, `flash` and any edit
     under `boards/`.
   - `forge.py check` rejects pins that are not on the board and ports that point the wrong
     way (an output on a button pin, an input on an LED pin).

## What the approval gate covers

| Path to the hardware | What stops an unapproved or stale program |
|---|---|
| `forge.py program` / `flash` | forge itself: the freshness check, then a terminal "yes" or `--yes` |
| The same command run by Claude Code | also the `ask` rules in `.claude/settings.json` |
| `forge::program` / `forge::flash` in an MCP or Tcl session | they refuse: they only run from `forge.py` |
| Raw Tcl through an MCP server (`program_hw_devices`, `program_hw_cfgmem`) | **only your agent client's tool approval**, plus rule 10 in `AGENTS.md` |
| The Vivado GUI Hardware Manager | the person at the keyboard |

forge cannot inspect Tcl that an MCP server runs, so the last two rows are outside its control.
If you connect a Vivado MCP server, keep its Tcl-execution tool on "ask" in your agent client
rather than "always allow", and allow-list only read-only tools if you want fewer prompts. A
Claude Code hook can catch some such calls, but hook `ask` decisions are reported not to be
enforced in every permission mode, so do not treat a hook as a guarantee.

A good first prompt:

> Read AGENTS.md. Build a stopwatch on the Basys 3: centre button starts/stops, down button
> resets, show seconds and hundredths on the 7-segment display. Test it, build it, and tell me
> what you verified. Don't program the board.

## Vivado MCP servers (optional)

The `forge.py` command line covers check, simulation, build and programming, so no MCP server
is required. An MCP server adds **interactive** access to a live Vivado session: exploring the
routed design, critical paths, the netlist and hierarchy. It is useful when timing fails or a
build behaves unexpectedly.

| Server | Who | Notes |
|---|---|---|
| **[AMD Ross](https://github.com/Xilinx/ross-ai-assistant)** `vivado-mcp-server` | AMD (official, launched Sept 2026) | Generic `vivado_execute` Tcl tool plus session tools; can attach to a running Vivado GUI; Agent Skills for simulation, linting, timing methodology, ILA/VIO debug; VS Code/Cursor extension or standalone server, downloaded from AMD's Ross page |
| [mapleleavessssssss-wq/vivado-mcp](https://github.com/mapleleavessssssss-wq/vivado-mcp) (`pip install vivado-mcp`) | community, Apache-2.0 | 32 tools including XDC lint, I/O placement and bitstream-readiness checks; Windows supported |
| [vivado-mcp-native](https://pypi.org/project/vivado-mcp-native/) | community, MIT | Windows-friendly fork of coreyhahn/vivado_mcp with simulation tools |

Prefer AMD Ross: it is maintained by AMD and released monthly. Check its documentation for the
Vivado versions it supports (its docs mention 2020.2+ and test against 2026.1).

### AMD Ross with Claude Code (or another CLI agent)

Download the standalone Vivado MCP server from AMD's Ross page
([setup guide](https://github.com/Xilinx/ross-ai-assistant)), then register it. This is the
form from AMD's documentation, with your own paths:

```sh
claude mcp add vivado-mcp --scope user --transport stdio \
  --env VIVADO_PATH=<Vivado install>/bin/vivado \
  -- <path to vivado-mcp-server> --stdio-bridge
```

### AMD Ross with VS Code or Cursor

AMD ships an extension (`.vsix`) that bundles the server and its skills; install it and set
its Vivado path. AMD's docs say to use either the extension or the standalone server, not both.

### Community servers

Follow the setup in each project's README (both document VS Code and Claude Code
configuration, and a `doctor` command to test the Vivado connection). Pin a released version:
these are single-maintainer projects.

### Using forge inside an MCP session

`scripts/forge.tcl` is a Tcl library as well as the batch script, so any server that can run Tcl
can use the same procedures as `forge.py`:

```tcl
source C:/path/to/project/scripts/forge.tcl
forge::load C:/fpga_build/blink/forge_context.tcl   ;# written by every forge.py build
forge::open_routed                                   ;# the routed design of the last build
forge::worst_paths 10                                ;# report_timing on the 10 worst paths
```

`forge.py info --json` prints the exact `context_tcl` path. Keep running check, sim and build
through `forge.py` so results stay reproducible and land in `reports/summary.json`. Use the MCP
session to investigate, not to program: `forge::program` and `forge::flash` refuse to run there,
and raw programming Tcl skips the freshness check and the approval gate (see the table above).
Ross's `vivado_execute` has no approval gate of its own.

## Data and privacy

`forge.py` runs entirely on your machine. Your RTL goes to whichever language model your agent
uses. AMD's Ross Vivado MCP server runs locally and does not upload design data; its optional
documentation search (`amd-doc-search`) sends queries to AMD.
