"""`forge.py check`: catch configuration, pin and clock mistakes before a slow Vivado run."""

from __future__ import annotations

from pathlib import Path

from .boards import Board, load_board, validate_board
from .common import Finding, ForgeError, is_synced_folder, rel
from .config import Config
from .hdl import Module, has_timescale, scan_modules
from .tools import Icarus, Vivado
from .xdc import Xdc, read_xdc


def run_checks(cfg: Config, vivado: Vivado | None, icarus: Icarus | None, need_vivado: bool = False) -> tuple[list[Finding], dict]:
    f: list[Finding] = []
    facts: dict = {}

    for w in cfg.warnings:
        f.append(Finding("warning", "config", w, rel(cfg.file)))

    # ---- board ------------------------------------------------------------------------------
    try:
        board = load_board(cfg.board_id)
    except ForgeError as exc:
        f.append(Finding("error", "board", str(exc), rel(cfg.file), hint=exc.hint))
        return f, facts
    for p in validate_board(board):
        f.append(Finding("error", "board", f"{board.id}: {p}", rel(board.dir / "board.json")))
    facts["board"] = board.id

    # ---- files ------------------------------------------------------------------------------
    sources, missing_src = cfg.source_files()
    for pat in missing_src:
        if pat.startswith("lib:"):
            f.append(Finding("error", "files", f"[project].lib names '{pat[4:]}' but lib/{pat[4:]}/ does not exist",
                             rel(cfg.file), hint="List lib modules with: python scripts/forge.py lib"))
        else:
            f.append(Finding("error", "files", f"[project].sources lists '{pat}', which does not exist", rel(cfg.file)))
    hdl_sources = [s for s in sources if s.suffix.lower() in (".v", ".sv", ".vhd", ".vhdl")]
    if not hdl_sources:
        f.append(Finding("error", "files", "no HDL source files", rel(cfg.file)))
    cons, missing_cons = cfg.constraint_files()
    for pat in missing_cons:
        f.append(Finding("error", "files", f"[project].constraints lists '{pat}', which does not exist", rel(cfg.file)))
    tests, missing_tests = cfg.test_files()
    for pat in missing_tests:
        f.append(Finding("error", "files", f"[sim].tests lists '{pat}', which does not exist", rel(cfg.file)))
    if not tests:
        f.append(Finding("warning", "tests", "no testbenches found",
                         rel(cfg.file), hint="Add tb/<module>_tb.v (see lib/*/ for examples) and run forge.py sim"))
    facts.update(sources=len(sources), constraints=len(cons), tests=len(tests))

    for s in sources:
        if s.suffix.lower() in (".v",) and not has_timescale(s):
            f.append(Finding("warning", "timescale", "no `timescale directive; add `timescale 1ns / 1ps as the first line",
                             rel(s), 1, hint="Simulators disagree on the default time unit (Icarus uses 1 s)."))

    # ---- modules ----------------------------------------------------------------------------
    modules = scan_modules(hdl_sources)
    by_name: dict[str, list[Module]] = {}
    for m in modules:
        by_name.setdefault(m.name, []).append(m)
    for name, ms in by_name.items():
        if len(ms) > 1:
            where = ", ".join(f"{rel(m.file)}:{m.line}" for m in ms)
            f.append(Finding("error", "modules", f"module '{name}' is defined {len(ms)} times ({where})", rel(ms[0].file), ms[0].line))
    top = by_name.get(cfg.top, [None])[0]
    if top is None:
        names = ", ".join(sorted(by_name)) or "none"
        f.append(Finding("error", "top", f"top module '{cfg.top}' not found in the sources (found: {names})",
                         rel(cfg.file), hint="Set [project].top to the module that has the board pins as ports."))
    else:
        facts["top_file"] = rel(top.file)
        for p in top.problems:
            f.append(Finding("warning", "ports", p, rel(top.file), top.line))

    # ---- constraints vs. ports vs. board ----------------------------------------------------
    xdcs = [read_xdc(c) for c in cons]
    if top is not None and xdcs:
        _check_pins(cfg, board, top, xdcs, f, facts)
    elif top is not None and not xdcs:
        f.append(Finding("error", "pins", "no constraint files: every top-level port needs a pin",
                         rel(cfg.file), hint="python scripts/forge.py pins add <board port>=<your port>"))

    # ---- tools and paths ---------------------------------------------------------------------
    if vivado is None:
        f.append(Finding("error" if need_vivado else "warning", "tools", "Vivado not found",
                         hint="Install Vivado, or set 'vivado = \"C:/Xilinx/Vivado/<ver>/bin/vivado.bat\"' in "
                              "forge.local.toml, or set $VIVADO_PATH."))
    facts["vivado"] = vivado.version if vivado else None
    facts["iverilog"] = icarus.version if icarus else None
    sync = is_synced_folder(cfg.build_dir)
    if sync:
        f.append(Finding("warning", "paths", f"build folder is inside {sync}; syncing Vivado's many temporary files is slow "
                                             "and can lock files mid-build",
                         hint="Set build_dir = \"C:/fpga_build/{name}\" (any local folder) in forge.local.toml"))
    return f, facts


def _bits(top: Module) -> tuple[dict[str, str], list[str]]:
    """Port bit name -> direction, plus names of ports whose width could not be worked out."""
    bits: dict[str, str] = {}
    unknown = []
    for p in top.ports:
        b = p.bits()
        if b is None:
            unknown.append(p.name)
            continue
        for name in b:
            bits[name] = p.direction
    return bits, unknown


ROLE_DIR = {"in": "input", "out": "output"}


def _check_role(board: Board, bit: str, direction: str, pin: str, masters: list, where: str, line: int,
                f: list[Finding]) -> None:
    """The port must point the way the board is wired, and an _n (active-low) name must fit the polarity."""
    roles = [r for m in masters for r in board.roles_of(m.name)]
    if not roles:
        return
    port_name = masters[0].name
    base = bit.split("[")[0]
    dirs = {r.dir for r in roles if r.dir in ROLE_DIR}
    if len(dirs) == 1 and direction in ("input", "output", "inout"):
        role_dir = dirs.pop()
        want = ROLE_DIR[role_dir]
        role = next(r for r in roles if r.dir == role_dir)
        if direction != want:
            what = (f"an input to the FPGA (board {role.name}): the design must only read it" if role_dir == "in"
                    else f"an output of the FPGA (board {role.name}): the design must drive it")
            f.append(Finding("warning" if direction == "inout" else "error", "direction",
                             f"port '{bit}' is declared {direction}, but pin {pin} is {port_name}, {what}", where, line,
                             hint=f"Declare '{base}' as {want} in the top module, or connect it to another pin "
                                  "(forge.py board lists each role's direction)."))
    lows = {r.active_low for r in roles if r.active_low is not None}
    if base.endswith("_n") and lows == {False}:
        role = next(r for r in roles if r.active_low is False)
        f.append(Finding("warning", "polarity",
                         f"port '{bit}' is named active-low (_n), but {port_name} (board {role.name}) is active-high "
                         f"on the {board.name}: 1 means pressed / on", where, line,
                         hint="Rename the port without _n, or invert the signal in the top module."))


def _check_pins(cfg: Config, board: Board, top: Module, xdcs: list[Xdc], f: list[Finding], facts: dict) -> None:
    bits, unknown = _bits(top)
    for name in unknown:
        f.append(Finding("warning", "ports", f"could not work out the width of port '{name}'; its pins are not checked",
                         rel(top.file), top.line))
    facts["top_ports"] = len(bits)

    pin_of: dict[str, tuple[str, Xdc, int]] = {}
    for x in xdcs:
        for port in x.ports.values():
            if port.pin:
                pin_of[port.name] = (port.pin.upper(), x, port.lineno)

    def prop(port: str, key: str) -> str | None:
        for x in reversed(xdcs):
            v = x.prop_for(port, key)
            if v:
                return v
        return None

    master_by_pin = board.pins_by_package_pin()
    used_pins: dict[str, str] = {}
    for bit, direction in bits.items():
        if bit not in pin_of:
            f.append(Finding("error", "pins", f"top-level port '{bit}' ({direction}) has no PACKAGE_PIN",
                             rel(top.file), top.line,
                             hint=f"python scripts/forge.py pins add <board port>={bit}  (list board ports: forge.py pins)"))
            continue
        pin, x, line = pin_of[bit]
        if not prop(bit, "IOSTANDARD"):
            f.append(Finding("error", "pins", f"port '{bit}' has no IOSTANDARD (Vivado will refuse to write a bitstream)",
                             rel(x.path), line))
        if pin in used_pins and used_pins[pin] != bit:
            f.append(Finding("error", "pins", f"pin {pin} is assigned to both '{used_pins[pin]}' and '{bit}'", rel(x.path), line))
        used_pins[pin] = bit
        masters = master_by_pin.get(pin)
        if not masters:
            f.append(Finding("error", "pins", f"pin {pin} (port '{bit}') is not a user pin on {board.name}",
                             rel(x.path), line,
                             hint=f"Copy pins from {rel(board.master_path)} with forge.py pins add; never type them by hand."))
            continue
        mstd = masters[0].iostandard
        std = prop(bit, "IOSTANDARD")
        if mstd and std and mstd.upper() != std.upper():
            f.append(Finding("warning", "pins", f"port '{bit}' uses IOSTANDARD {std} but the board master says {mstd} for pin {pin}",
                             rel(x.path), line, hint="The bank voltage decides this; a mismatch is usually a DRC error."))
        _check_role(board, bit, direction, pin, masters, rel(x.path), line, f)

    for x in xdcs:
        for port in x.ports.values():
            if port.pin and port.name not in bits and not unknown:
                f.append(Finding("warning", "pins", f"constraint for '{port.name}', which is not a port of '{top.name}'",
                                 rel(x.path), port.lineno, hint="Remove the line or fix the port name (Vivado reports it as a critical warning)."))

    # ---- clock ---------------------------------------------------------------------------------
    clock_pin = (board.clock_pin or "").upper()
    clock_ports = [b for b, (pin, _, _) in pin_of.items() if pin == clock_pin and b in bits]
    clocks = [c for x in xdcs for c in x.clocks]
    if not clock_ports:
        f.append(Finding("warning", "clock", f"no top-level port is on the board clock pin {clock_pin} "
                                             f"({board.clock_hz / 1e6:g} MHz)",
                         rel(top.file), top.line, hint=f"python scripts/forge.py pins add {board.clock_port}=clk"))
    for cp in clock_ports:
        match = [c for c in clocks if c.port == cp]
        if not match:
            f.append(Finding("error", "clock", f"clock port '{cp}' has no create_clock constraint, so timing is not checked",
                             hint=f"Add: create_clock -period {board.clock_period_ns:.3f} [get_ports {{ {cp} }}]"))
            continue
        period = match[0].period
        if period and abs(period - board.clock_period_ns) / board.clock_period_ns > 0.01:
            f.append(Finding("error", "clock", f"create_clock on '{cp}' says {period} ns but the board clock is "
                                               f"{board.clock_period_ns:.3f} ns ({board.clock_hz / 1e6:g} MHz)"))
    for c in clocks:
        if c.port not in bits and not unknown:
            f.append(Finding("warning", "clock", f"create_clock on '{c.port}', which is not a port of '{top.name}'"))

    have_cfg = any("CFGBVS" in Path(x.path).read_text(encoding="utf-8", errors="replace") for x in xdcs if x.path)
    if not have_cfg and board.xdc_config:
        f.append(Finding("info", "pins", "constraints do not set CFGBVS/CONFIG_VOLTAGE (Vivado warns about it)",
                         hint="forge.py pins add writes the board's configuration lines automatically."))
