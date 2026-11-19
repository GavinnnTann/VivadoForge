"""Command-line interface: python scripts/forge.py <command> [--json]."""

from __future__ import annotations

import argparse
import json
import sys
import time
import unittest
from pathlib import Path

from . import __version__
from . import build as B
from . import manifest as M
from . import sim as S
from . import templates as T
from .boards import board_ids, load_board, validate_board
from .build_dir import clean_build_dir, ensure_build_dir
from .checks import run_checks
from .common import (LIB_DIR, LOCAL_CONFIG_NAME, REPO_ROOT, ForgeError, Out, forge_cmd, natural_key, rel)
from .config import Config, load_config, write_local_setting
from .tools import find_iverilog, find_vivado, launch_detached, tool_summary

COMMANDS_HELP = """
commands (run `forge.py <command> -h` for options):
  info        project, board, tools and last build at a glance (start here)
  check       validate config, pins and clock before building (fast, no Vivado)
  sim         run testbenches (tb/*_tb.v; --lib for the lib/ module tests)
  build       synthesis + implementation + bitstream, then a timing/usage summary
  report      show the last build summary again
  program     load the bitstream into the FPGA over JTAG (volatile; needs approval)
  flash       write the bitstream to configuration flash (persistent; needs approval)
  devices     list FPGAs connected over JTAG (read-only)
  open        open the built Vivado project in the Vivado GUI
  clean       delete the build folder
  boards      list supported boards
  board       details of a board: part, clock, peripherals and polarities (--pins for all pins)
  pins        list the board's pins, or `pins add <board port>=<your port>` to constrain them
  lib         list the reusable, tested RTL modules in lib/
  templates   list project templates
  new         create a project from a template for a board
  setup       save machine settings (Vivado path, build folder) in forge.local.toml
  selftest    test this repository itself: lib modules and every template on every board
"""


# ---------------------------------------------------------------------------------------------
def _cfg(args) -> Config:
    try:
        return load_config(Path(args.project) if args.project else None)
    except ForgeError as exc:
        if exc.code == "error":
            exc.code = "config"
        raise


def _no_vivado(hint: str = "Set 'vivado' in forge.local.toml (forge.py setup --detect) or $VIVADO_PATH.") -> ForgeError:
    return ForgeError("Vivado not found.", hint=hint, code="vivado_not_found")


def _last_build(cfg: Config, board) -> dict | None:
    """The last build summary plus whether its bitstream still matches the design."""
    s = B.last_summary(cfg)
    if s is None:
        return None
    fresh = M.freshness(cfg, board)
    s["up_to_date"] = fresh["up_to_date"] if fresh else None
    s["changes_since_build"] = fresh["changes"] if fresh else []
    return s


def _emit(args, out: Out, data: dict, ok: bool = True) -> int:
    if args.json:
        data = dict(data)
        data.setdefault("ok", ok)
        print(json.dumps(data, indent=2, default=str))
    return 0 if ok else 1


def _tools(cfg: Config | None):
    return find_vivado(cfg.vivado_hint if cfg else None), find_iverilog(cfg.iverilog_hint if cfg else None)


def _findings_text(out: Out, findings) -> tuple[int, int]:
    errors = [f for f in findings if f.severity == "error"]
    warns = [f for f in findings if f.severity == "warning"]
    for f in errors + warns + [f for f in findings if f.severity == "info"]:
        out(f.format())
    return len(errors), len(warns)


# ---------------------------------------------------------------------------------------------
def cmd_info(args, out: Out) -> int:
    cfg = _cfg(args)
    board = load_board(cfg.board_id)
    viv, ivl = _tools(cfg)
    last = _last_build(cfg, board)
    data = {
        "forge_version": __version__,
        "project": cfg.to_dict(),
        "board": board.summary(),
        "tools": tool_summary(viv, ivl),
        "paths": {"build_dir": cfg.build_dir.as_posix(), "bitstream": cfg.bitstream.as_posix(),
                  "summary": cfg.summary_file.as_posix(), "context_tcl": (cfg.build_dir / "forge_context.tcl").as_posix(),
                  "forge_tcl": (REPO_ROOT / "scripts" / "forge.tcl").as_posix()},
        "last_build": {k: last.get(k) for k in ("status", "stage", "finished", "verification", "reasons", "up_to_date",
                                                "changes_since_build", "timing", "utilization", "bitstream")}
                      if last else None,
        "commands": {c: forge_cmd(c) for c in ("check", "sim", "build", "report", "program", "flash")},
    }
    if not args.json:
        p = data["project"]
        out(f"VivadoForge {__version__}")
        out(f"  project : {cfg.name}  (top: {cfg.top})  config: {rel(cfg.file)}")
        out(f"  board   : {board.id} - {board.name}, part {board.part}, clock {board.clock_port} on {board.clock_pin} "
            f"at {board.clock_hz / 1e6:g} MHz")
        out(f"  files   : {len(p['sources'])} sources, {len(p['constraints'])} constraint files, {len(p['tests'])} testbenches"
            + (f", lib: {', '.join(cfg.lib)}" if cfg.lib else ""))
        out(f"  build   : {cfg.build_dir.as_posix()}")
        if last:
            t = last.get("timing") or {}
            fresh = {True: "matches the sources", False: "OUT OF DATE (sources changed since)",
                     None: "not on record (build again before programming)"}
            out(f"  last    : {last.get('status')} at {last.get('finished')}  WNS {t.get('wns')} ns  "
                f"bitstream {fresh[last.get('up_to_date')]}")
        else:
            out("  last    : no build yet")
        out(f"  vivado  : {viv.version + '  ' + viv.vivado.as_posix() if viv else 'NOT FOUND (see docs/getting-started.md)'}")
        out(f"  iverilog: {ivl.version if ivl else 'not found (optional)'}")
        out(f"  next    : {forge_cmd('check')}  ->  {forge_cmd('sim')}  ->  {forge_cmd('build')}")
    return _emit(args, out, data)


def cmd_check(args, out: Out) -> int:
    cfg = _cfg(args)
    viv, ivl = _tools(cfg)
    findings, facts = run_checks(cfg, viv, ivl)
    n_err = sum(f.severity == "error" for f in findings)
    n_warn = sum(f.severity == "warning" for f in findings)
    ok = n_err == 0 and (not args.strict or n_warn == 0)
    if not args.json:
        out(f"Checking {cfg.name} for {cfg.board_id} ...")
        _findings_text(out, findings)
        out(("CHECK PASSED" if ok else "CHECK FAILED") + f"  ({n_err} errors, {n_warn} warnings)")
    return _emit(args, out, {"errors": n_err, "warnings": n_warn, "facts": facts,
                             "findings": [f.to_dict() for f in findings]}, ok)


def cmd_sim(args, out: Out) -> int:
    viv, ivl = None, None
    if args.lib is not None:
        cfg = None
        try:
            cfg = _cfg(args)
        except ForgeError:
            pass
        root = cfg.build_dir if cfg else REPO_ROOT / "build"
        viv, ivl = _tools(cfg)
        jobs = S.lib_jobs(args.lib or None, root / "sim" / "lib")
        simulator = args.simulator or (cfg.simulator if cfg else "auto")
        timeout = args.timeout or 300
    else:
        cfg = _cfg(args)
        root = cfg.build_dir
        viv, ivl = _tools(cfg)
        jobs = S.project_jobs(cfg, args.tests or None, root / "sim")
        if not jobs:
            raise ForgeError("No testbenches to run.", hint="Add tb/<name>_tb.v (template: lib/*/<name>_tb.v) or check [sim].tests.")
        simulator = args.simulator or cfg.simulator
        timeout = args.timeout or cfg.sim_timeout
    out(f"Simulating {len(jobs)} testbench(es)")
    results = S.run_jobs(jobs, simulator, viv, ivl, wave=args.wave or args.gui, gui=args.gui, timeout=timeout,
                         out=out, verbose=args.verbose, build_root=root)
    passed = sum(r.ok for r in results)
    ok = passed == len(results)
    out(("SIM PASSED" if ok else "SIM FAILED") + f"  ({passed}/{len(results)} passed)")
    return _emit(args, out, {"passed": passed, "total": len(results), "results": [r.to_dict() for r in results]}, ok)


def cmd_build(args, out: Out) -> int:
    cfg = _cfg(args)
    board = load_board(cfg.board_id)
    viv, ivl = _tools(cfg)
    if not args.no_check:
        findings, _ = run_checks(cfg, viv, ivl, need_vivado=True)
        errs = [f for f in findings if f.severity == "error"]
        if errs:
            if not args.json:
                out("Pre-build check failed (fix these or use --no-check):")
                _findings_text(out, errs)
            return _emit(args, out, {"status": "check_failed", "findings": [f.to_dict() for f in errs]}, False)
    if viv is None:
        raise _no_vivado()
    summary = B.build(cfg, board, viv, out, verbose=args.verbose)
    for line in B.format_summary(summary):
        out(line)
    return _emit(args, out, summary, B.build_ok(summary, cfg.timing_policy))


def cmd_report(args, out: Out) -> int:
    cfg = _cfg(args)
    s = _last_build(cfg, load_board(cfg.board_id))
    if s is None:
        raise ForgeError("No build summary yet.", hint=f"Run {forge_cmd('build')} first.", code="no_build")
    if not args.json:
        for line in B.format_summary(s):
            out(line)
        if s.get("up_to_date") is False:
            out("  OUT OF DATE: the design changed after this build, so the bitstream is not the current design:")
            for c in s.get("changes_since_build", []):
                out(f"    {c}")
        out(f"  full data: {rel(cfg.summary_file)}   reports: {rel(cfg.build_dir / 'reports')}")
    # A good build of sources that have since changed does not verify the current design.
    return _emit(args, out, s, B.build_ok(s, cfg.timing_policy) and s.get("up_to_date") is not False)


def _interactive() -> bool:
    """True only for a real terminal a person is typing into (not a pipe, file or NUL device)."""
    try:
        if not sys.stdin or not sys.stdin.isatty():
            return False
    except (AttributeError, ValueError):
        return False
    if sys.platform == "win32":
        # On Windows the NUL device also reports isatty(); only a console handle has a console mode.
        try:
            import ctypes
            import msvcrt
            mode = ctypes.c_uint32()
            return bool(ctypes.windll.kernel32.GetConsoleMode(msvcrt.get_osfhandle(sys.stdin.fileno()), ctypes.byref(mode)))
        except (OSError, AttributeError, ValueError):
            return False
    return True


def _confirm(args, out: Out, what: str) -> None:
    if args.yes:
        return
    refuse = ForgeError(f"{what}: this changes physical hardware and needs explicit approval.",
                        hint="A person must approve it. Re-run with --yes only after they have said yes.",
                        code="approval_required")
    if args.json or not _interactive():
        raise refuse
    try:
        reply = input(f"{what}? [y/N] ").strip().lower()
    except EOFError:
        raise refuse
    if reply not in ("y", "yes"):
        raise ForgeError("Cancelled.", code="cancelled")


def _hardware(args, out: Out, action: str) -> int:
    cfg = _cfg(args)
    board = load_board(cfg.board_id)
    extra: dict = {}
    if action in ("program", "flash"):
        # Before anything else: the bitstream must be the one a forge build made from the current design.
        man = M.verify_bitstream(cfg, board)
        last = B.last_summary(cfg) or {}
        warnings = [] if last.get("status") == "passed" else \
            [r["text"] for r in last.get("reasons", [])] or [f"the last build has status '{last.get('status')}'"]
        if warnings:
            out(f"WARNING: the last build is '{last.get('status')}', so this design is not fully verified:")
            for w in warnings:
                out(f"  - {w}")
        extra = {"bitstream": {"path": cfg.bitstream.as_posix(), "sha256": man["bitstream"]["sha256"],
                               "built": man.get("built"), "build_status": last.get("status")},
                 "warnings": warnings}
    viv, _ = _tools(cfg)
    if viv is None:
        raise _no_vivado()
    if action in ("program", "flash"):
        what = {"program": f"Program the FPGA on the {board.name} with {cfg.name} (volatile, lost at power-off)",
                "flash": f"Erase and rewrite the configuration flash on the {board.name} with {cfg.name} "
                         f"(persistent: it boots this design at every power-up)"}[action]
        if action == "flash" and not board.flash.get("verified_on_hardware", False):
            out(f"NOTE: the flash settings for {board.id} have not been verified on hardware yet.")
        _confirm(args, out, what)
        M.verify_bitstream(cfg, board)   # again: the prompt may have waited while files changed
    out({"program": "Programming FPGA ...", "flash": "Programming configuration flash ...",
         "devices": "Looking for JTAG devices ..."}[action])
    res = B.hardware(cfg, board, viv, action, out, verbose=args.verbose)
    res.update(extra)
    if not args.json:
        if action == "devices":
            for d in res.get("devices", []):
                out(f"  {d.get('device', '?'):<14} part {d.get('part', '?'):<10} target {d.get('target', '')}")
            if not res.get("devices"):
                out("  no FPGA found (check the USB cable, board power and cable drivers)")
        for e in res["errors"]:
            out(f"  ERROR {e}")
        out(("DONE" if res["ok"] else "FAILED") + f"  ({res['seconds']} s, log: {res['log']})")
    return _emit(args, out, res, res["ok"])


def cmd_open(args, out: Out) -> int:
    cfg = _cfg(args)
    viv, _ = _tools(cfg)
    if viv is None:
        raise _no_vivado()
    if not cfg.xpr.is_file():
        raise ForgeError(f"No Vivado project at {cfg.xpr.as_posix()}.", hint=f"Run {forge_cmd('build')} first.")
    launch_detached([viv.vivado, cfg.xpr.name], cwd=cfg.xpr.parent)
    out(f"Opening {cfg.xpr.as_posix()} in Vivado (the project is regenerated by every build).")
    return _emit(args, out, {"opened": cfg.xpr.as_posix()})


def cmd_clean(args, out: Out) -> int:
    cfg = _cfg(args)
    deleted = clean_build_dir(cfg.build_dir)
    out(f"Deleted {cfg.build_dir.as_posix()}" if deleted else "Nothing to clean.")
    return _emit(args, out, {"deleted": deleted, "build_dir": cfg.build_dir.as_posix()})


def cmd_boards(args, out: Out) -> int:
    rows = []
    for b in board_ids():
        bd = load_board(b)
        rows.append({"id": b, "name": bd.name, "part": bd.part, "clock_mhz": bd.clock_hz / 1e6,
                     "roles": sorted(bd.roles), "problems": validate_board(bd)})
    if not args.json:
        for r in rows:
            out(f"  {r['id']:<15} {r['name']:<38} {r['part']:<20} {r['clock_mhz']:g} MHz")
        out(f"Details: {forge_cmd('board <id>')}")
    return _emit(args, out, {"boards": rows})


def cmd_board(args, out: Out) -> int:
    cfg = None
    board_id = args.id
    if not board_id:
        cfg = _cfg(args)
        board_id = cfg.board_id
    else:
        try:
            cfg = _cfg(args)
        except ForgeError:
            cfg = None
    board = load_board(board_id)
    data = board.summary()
    if args.pins:
        data["pins"] = T.pins_table(cfg if cfg and cfg.board_id == board.id else None, board)
    if not args.json:
        s = data
        out(f"{s['name']}  [{board.id}]  part {s['part']}")
        out(f"  clock: port {s['clock']['port']} on pin {s['clock']['pin']}, {board.clock_hz / 1e6:g} MHz "
            f"({s['clock']['period_ns']} ns)")
        out(f"  pins : {rel(board.master_path)}  (source: {board.data.get('master_xdc_source', '')})")
        out(f"  docs : {s['reference_manual']}")
        out("  roles (use these names with `forge.py pins add <role>=<your name>`):")
        for name, r in board.roles.items():
            pol = "" if r.active_low is None else ("  ACTIVE-LOW" if r.active_low else "  active-high")
            ports = ", ".join(r.ports[:6]) + (f", ... ({len(r.ports)})" if len(r.ports) > 6 else "")
            out(f"    {name:<10} {r.dir:<6}{pol:<12} {ports}")
            if r.note:
                out(f"               {r.note}")
        for n in s["notes"]:
            out(f"  note: {n}")
        if args.pins:
            _print_pins(out, data["pins"])
    return _emit(args, out, data)


def _print_pins(out: Out, rows: list[dict]) -> None:
    section = None
    for r in rows:
        if r["section"] != section:
            section = r["section"]
            out(f"  ## {section}")
        used = f"  <- used by {r['used_by']}" if r["used_by"] else ""
        pol = "" if r["active_low"] is None else (" active-low" if r["active_low"] else "")
        out(f"    {r['port']:<16} {r['pin'] or '?':<6} {r['iostandard'] or '':<10}{pol}{used}")


def cmd_pins(args, out: Out) -> int:
    cfg = _cfg(args)
    board = load_board(cfg.board_id)
    if args.action == "add":
        if not args.specs:
            raise ForgeError("Nothing to add.", hint="Example: forge.py pins add btn[0]=start led=status sysclk=clk")
        res = T.pins_add(cfg, board, args.specs, Path(args.file) if args.file else None)
        if not args.json:
            for a in res["added"]:
                out(f"  added   {a['design']:<16} <- {a['board_port']:<14} pin {a['pin']}  {a['iostandard']}")
            for s in res["skipped"]:
                out(f"  skipped {s}")
            out(f"Updated {res['file']}. Port names must match your top module; run forge.py check.")
        return _emit(args, out, res)
    rows = T.pins_table(cfg, board)
    if not args.json:
        out(f"Pins of {board.name} from {rel(board.master_path)}:")
        _print_pins(out, rows)
        out("Add one: forge.py pins add <port>[=<your name>]   e.g.  pins add btn[0]=start  or  pins add led")
    return _emit(args, out, {"board": board.id, "pins": rows})


def _first_comment(path: Path) -> str:
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line.startswith("//"):
            text = line.lstrip("/ ").strip()
            if " - " in text:
                return text.split(" - ", 1)[1]
            return text
    return ""


def cmd_lib(args, out: Out) -> int:
    mods = []
    for d in sorted(p for p in LIB_DIR.iterdir() if p.is_dir() and (p / f"{p.name}.v").is_file()):
        mods.append({"name": d.name, "file": rel(d / f"{d.name}.v"), "description": _first_comment(d / f"{d.name}.v"),
                     "testbench": rel(d / f"{d.name}_tb.v") if (d / f"{d.name}_tb.v").is_file() else None})
    if not args.json:
        for m in mods:
            out(f"  {m['name']:<12} {m['description']}")
        out('Use one: add its name to lib = [...] in forge.toml, then instantiate it. Read the header comment for ports.')
    return _emit(args, out, {"modules": mods})


def cmd_templates(args, out: Out) -> int:
    rows = []
    boards = {b: load_board(b) for b in board_ids()}
    for name in T.template_names():
        t = T.load_template(name)
        rows.append({"name": name, "description": t.description,
                     "boards": [b for b, bd in boards.items() if not T.compatible(t, bd)]})
    if not args.json:
        for r in rows:
            out(f"  {r['name']:<15} {r['description']}")
            out(f"  {'':<15} boards: {', '.join(r['boards'])}")
        out(f"Create one: {forge_cmd('new --template <name> --board <board>')}")
    return _emit(args, out, {"templates": rows})


def cmd_new(args, out: Out) -> int:
    dest = Path(args.dir) if args.dir else REPO_ROOT
    res = T.new_project(args.template, args.board, dest, args.name, args.force)
    if not args.json:
        out(f"Created '{res['template']}' for {res['board']} in {res['project'] or '.'}:")
        for f in res["files"]:
            out(f"  {f}")
        out("Next: " + forge_cmd(("-p " + res['project'] + " " if args.dir else "") + "check") + "  then sim, build")
    return _emit(args, out, res)


def cmd_setup(args, out: Out) -> int:
    cfg = None
    try:
        cfg = _cfg(args)
    except ForgeError:
        pass
    root = cfg.root if cfg else REPO_ROOT
    changes = {}
    if args.vivado:
        changes["vivado"] = args.vivado
    elif args.detect:
        viv = find_vivado()
        if viv is None:
            raise ForgeError("Vivado not found in the usual places.", hint="Pass --vivado <path to vivado(.bat)>.")
        changes["vivado"] = viv.vivado.as_posix()
    if args.build_dir:
        changes["build_dir"] = args.build_dir
    for k, v in changes.items():
        write_local_setting(root, k, v)
        out(f"  {LOCAL_CONFIG_NAME}: {k} = {v}")
    viv, ivl = _tools(load_config(root) if (root / "forge.toml").is_file() else None)
    out(f"Vivado  : {viv.vivado.as_posix() + ' (' + viv.version + ')' if viv else 'not found'}")
    out(f"Icarus  : {ivl.iverilog.as_posix() + ' (' + ivl.version + ')' if ivl else 'not found (optional)'}")
    return _emit(args, out, {"written": changes, "tools": tool_summary(viv, ivl)})


def cmd_selftest(args, out: Out) -> int:
    """Unit tests + lib module tests + every template on every compatible board (simulation only)."""
    t0 = time.monotonic()
    report: dict = {"unit": None, "lib": None, "templates": []}
    ok = True
    tests_dir = REPO_ROOT / "tests"
    if tests_dir.is_dir():
        out("Unit tests (tests/) ...")
        suite = unittest.defaultTestLoader.discover(str(tests_dir))
        res = unittest.TextTestRunner(stream=sys.stderr, verbosity=1).run(suite)
        report["unit"] = {"run": res.testsRun, "failures": len(res.failures), "errors": len(res.errors)}
        ok &= res.wasSuccessful()
    cfg0 = None
    try:
        cfg0 = _cfg(args)
    except ForgeError:
        pass
    # honour the project's build folder (e.g. a local folder outside OneDrive from forge.local.toml)
    base = cfg0.build_dir if cfg0 else REPO_ROOT / "build"
    viv, ivl = _tools(cfg0)
    simulator = args.simulator or "auto"
    root = base / "selftest"
    ensure_build_dir(base)
    out("Library module tests ...")
    lib_res = S.run_jobs(S.lib_jobs(None, root / "lib"), simulator, viv, ivl, out=out, build_root=base)
    report["lib"] = {"passed": sum(r.ok for r in lib_res), "total": len(lib_res)}
    ok &= all(r.ok for r in lib_res)
    boards = {b: load_board(b) for b in board_ids()}
    for name in T.template_names():
        t = T.load_template(name)
        targets = [b for b, bd in boards.items() if not T.compatible(t, bd)]
        if args.quick:
            targets = targets[:1]
        for b in targets:
            dest = root / f"{name}-{b}"
            out(f"Template {name} on {b} ...")
            T.new_project(name, b, dest, None, force=True)
            cfg = load_config(dest)
            findings, _ = run_checks(cfg, viv, ivl)
            errs = [f.format() for f in findings if f.severity == "error"]
            for e in errs:
                out(e)
            res = S.run_jobs(S.project_jobs(cfg, None, cfg.build_dir / "sim"), simulator, viv, ivl, out=out,
                             build_root=cfg.build_dir)
            entry = {"template": name, "board": b, "check_errors": errs, "sim": [r.status for r in res]}
            report["templates"].append(entry)
            ok &= not errs and all(r.ok for r in res)
    report["seconds"] = round(time.monotonic() - t0, 1)
    n_t = len(report["templates"])
    n_ok = sum(1 for e in report["templates"] if not e["check_errors"] and all(s == "passed" for s in e["sim"]))
    out(("SELFTEST PASSED" if ok else "SELFTEST FAILED") +
        f"  (lib {report['lib']['passed']}/{report['lib']['total']}, templates {n_ok}/{n_t}, {report['seconds']} s)")
    return _emit(args, out, report, ok)


# ---------------------------------------------------------------------------------------------
def make_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="forge.py", usage="forge.py [-p PROJECT] [--json] [-v] <command> [options]",
                                description="VivadoForge: Vivado projects from the command line.",
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=COMMANDS_HELP)
    p.add_argument("--version", action="version", version=f"VivadoForge {__version__}")
    # Global options work before or after the command: `forge.py -p X check` == `forge.py check -p X`.
    p.add_argument("-p", "--project", default=None, help="project folder or forge.toml (default: nearest forge.toml)")
    p.add_argument("--json", action="store_true", help="print machine-readable JSON on stdout")
    p.add_argument("-v", "--verbose", action="store_true", help="show full tool output")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-p", "--project", default=argparse.SUPPRESS, help="project folder or forge.toml")
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="machine-readable JSON on stdout")
    common.add_argument("-v", "--verbose", action="store_true", default=argparse.SUPPRESS, help="full tool output")
    sub = p.add_subparsers(dest="command", metavar="<command>", help=argparse.SUPPRESS)  # listed in the epilog

    sub.add_parser("info", parents=[common], help="project overview")
    c = sub.add_parser("check", parents=[common], help="validate before building")
    c.add_argument("--strict", action="store_true", help="treat warnings as errors")
    s = sub.add_parser("sim", parents=[common], help="run testbenches")
    s.add_argument("tests", nargs="*", help="testbench names (default: all)")
    s.add_argument("--lib", nargs="*", metavar="MODULE", help="run lib/ module tests instead (all if none named)")
    s.add_argument("--simulator", choices=["auto", "xsim", "iverilog"])
    s.add_argument("--wave", action="store_true", help="record waveforms")
    s.add_argument("--gui", action="store_true", help="record waveforms and open the viewer")
    s.add_argument("--timeout", type=int, help="seconds per test")
    b = sub.add_parser("build", parents=[common], help="synthesise, implement, write bitstream")
    b.add_argument("--no-check", action="store_true", help="skip the pre-build check")
    sub.add_parser("report", parents=[common], help="show the last build summary")
    for name, text in (("program", "program the FPGA (volatile)"), ("flash", "program the configuration flash")):
        h = sub.add_parser(name, parents=[common], help=text)
        h.add_argument("--yes", action="store_true", help="confirm without a prompt (only after a person approved it)")
    sub.add_parser("devices", parents=[common], help="list JTAG devices")
    sub.add_parser("open", parents=[common], help="open the project in the Vivado GUI")
    sub.add_parser("clean", parents=[common], help="delete the build folder")
    sub.add_parser("boards", parents=[common], help="list boards")
    bd = sub.add_parser("board", parents=[common], help="board details")
    bd.add_argument("id", nargs="?", help="board id (default: the project's board)")
    bd.add_argument("--pins", action="store_true", help="list every pin in the master XDC")
    pn = sub.add_parser("pins", parents=[common], help="list or add pin constraints")
    pn.add_argument("action", nargs="?", choices=["list", "add"], default="list")
    pn.add_argument("specs", nargs="*", help="<board port, bus or role>[=<your port name>]")
    pn.add_argument("--file", help="constraints file to append to (default: the project's first .xdc)")
    sub.add_parser("lib", parents=[common], help="list lib/ modules")
    sub.add_parser("templates", parents=[common], help="list project templates")
    n = sub.add_parser("new", parents=[common], help="create a project from a template")
    n.add_argument("--template", "-t", required=True)
    n.add_argument("--board", "-b", required=True)
    n.add_argument("--name", help="project name (default: the template name)")
    n.add_argument("--dir", help="where to create it (default: the repository root)")
    n.add_argument("--force", action="store_true", help="replace existing src/, tb/ and constraints/")
    st = sub.add_parser("setup", parents=[common], help="write forge.local.toml")
    st.add_argument("--vivado", help="path to vivado(.bat) or its install folder")
    st.add_argument("--detect", action="store_true", help="auto-detect Vivado and save it")
    st.add_argument("--build-dir", help="build folder for this machine, e.g. C:/fpga_build/{name}")
    t = sub.add_parser("selftest", parents=[common], help="test the repository itself")
    t.add_argument("--simulator", choices=["auto", "xsim", "iverilog"])
    t.add_argument("--quick", action="store_true", help="one board per template")
    return p


HANDLERS = {"info": cmd_info, "check": cmd_check, "sim": cmd_sim, "build": cmd_build, "report": cmd_report,
            "program": lambda a, o: _hardware(a, o, "program"), "flash": lambda a, o: _hardware(a, o, "flash"),
            "devices": lambda a, o: _hardware(a, o, "devices"), "open": cmd_open, "clean": cmd_clean,
            "boards": cmd_boards, "board": cmd_board, "pins": cmd_pins, "lib": cmd_lib,
            "templates": cmd_templates, "new": cmd_new, "setup": cmd_setup, "selftest": cmd_selftest}


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except AttributeError:
            pass
    parser = make_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    out = Out(json_mode=getattr(args, "json", False))
    try:
        return HANDLERS[args.command](args, out)
    except ForgeError as exc:
        if getattr(args, "json", False):
            print(json.dumps({"ok": False, "error": str(exc), "hint": exc.hint, "code": exc.code, **exc.details},
                             indent=2))
        else:
            print(f"error: {exc}", file=sys.stderr)
            if exc.hint:
                print(f"hint:  {exc.hint}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
