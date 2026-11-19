"""Run self-checking testbenches with Vivado xsim or Icarus Verilog.

A test passes only when its log contains "TEST PASSED" and no "TEST FAILED", "CHECK FAILED",
"Error:" or "Fatal:" line. Neither simulator's exit code is trusted on its own: xsim exits 0
after $fatal.
"""

from __future__ import annotations

import json
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from .build_dir import ensure_build_dir, remove_tree
from .common import HDL_EXTS, HEADER_EXTS, LIB_DIR, MEM_EXTS, REPO_ROOT, TB_INCLUDE_DIR, ForgeError, Out, rel
from .hdl import parse_verilog_modules, parse_vhdl_entities
from .tools import NOISE, Icarus, Vivado, launch_detached, run

FAIL_RE = re.compile(r"^\s*(Fatal|FATAL|Error|ERROR)\s*:")
DEFAULT_TIMESCALE = "1ns/1ps"


@dataclass
class SimJob:
    name: str                 # testbench top module
    tb_file: Path
    files: list[Path]         # design + testbench files (any order; tb last)
    include_dirs: list[Path]
    defines: dict[str, str]
    mem_files: list[Path]
    work_dir: Path


@dataclass
class SimResult:
    name: str
    file: str
    simulator: str
    status: str               # passed | failed | error | timeout | no_verdict
    seconds: float
    log: str
    summary: str = ""
    failures: list[str] = field(default_factory=list)
    wave: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "passed"

    def to_dict(self) -> dict:
        return {"name": self.name, "file": self.file, "simulator": self.simulator, "status": self.status,
                "seconds": round(self.seconds, 2), "log": self.log, "summary": self.summary,
                "failures": self.failures[:50], "wave": self.wave}


# ---------------------------------------------------------------------------------------------
def testbench_module(path: Path) -> str | None:
    """The testbench's top module: the one named like the file, else the first one."""
    if path.suffix.lower() in (".vhd", ".vhdl"):
        mods = parse_vhdl_entities(path)
    else:
        mods = parse_verilog_modules(path)
    if not mods:
        return None
    for m in mods:
        if m.name == path.stem:
            return m.name
    return mods[0].name


def judge(output: str, returncode: int, timed_out: bool) -> tuple[str, list[str], str]:
    lines = output.splitlines()
    failures = [ln.strip() for ln in lines
                if FAIL_RE.match(ln) or "TEST FAILED" in ln or "CHECK FAILED" in ln]
    passed = [ln.strip() for ln in lines if "TEST PASSED" in ln]
    if timed_out:
        return "timeout", failures, "wall-clock timeout: the testbench never called $finish"
    if failures:
        return "failed", failures, failures[-1]
    if returncode != 0:
        return "failed", [], f"simulator exited with code {returncode}"
    if passed:
        return "passed", [], passed[-1]
    return "no_verdict", [], "the testbench ended without printing TEST PASSED (use `TEST_DONE from forge_tb.vh)"


def _error_lines(output: str, limit: int = 15) -> list[str]:
    errs = [ln.strip() for ln in output.splitlines()
            if re.match(r"^\s*(ERROR|CRITICAL WARNING)\s*:", ln) or re.search(r":\d+:\s*(syntax )?error", ln, re.I)]
    return errs[:limit]


# ---------------------------------------------------------------------------------------------
def project_jobs(cfg, names: list[str] | None, base: Path) -> list[SimJob]:
    tests, _ = cfg.test_files()
    groups = cfg.classified_sources()
    design = groups["verilog"] + groups["systemverilog"] + groups["vhdl"]
    tb_dirs = sorted({t.parent for t in tests})
    jobs = []
    for t in tests:
        mod = testbench_module(t)
        if mod is None:
            raise ForgeError(f"{rel(t)} contains no module/entity.")
        if names and t.stem not in names and mod not in names and t.name not in names:
            continue
        mem = list(groups["mem"]) + [f for d in tb_dirs for f in d.iterdir() if f.suffix.lower() in MEM_EXTS]
        jobs.append(SimJob(
            name=mod, tb_file=t,
            files=[f for f in design if f.resolve() != t.resolve()] + [t],
            include_dirs=list(dict.fromkeys(cfg.all_include_dirs() + tb_dirs + [TB_INCLUDE_DIR])),
            defines=dict(cfg.defines), mem_files=mem, work_dir=base / mod))
    if names:
        known = {t.stem for t in tests}
        unknown = [n for n in names if n not in known and not any(j.name == n for j in jobs)]
        if unknown:
            raise ForgeError(f"No testbench named {', '.join(unknown)}.",
                             hint=f"Tests found: {', '.join(sorted(known)) or 'none'} (from [sim].tests in forge.toml).")
    return jobs


def lib_modules() -> list[str]:
    if not LIB_DIR.is_dir():
        return []
    return sorted(d.name for d in LIB_DIR.iterdir() if d.is_dir() and any(d.glob(f"{d.name}_tb.*")))


def lib_jobs(names: list[str] | None, base: Path) -> list[SimJob]:
    available = lib_modules()
    chosen = names or available
    unknown = [n for n in chosen if n not in available]
    if unknown:
        raise ForgeError(f"No lib module test for: {', '.join(unknown)}", hint=f"Available: {', '.join(available)}")
    jobs = []
    for n in chosen:
        d = LIB_DIR / n
        tb = next(f for f in sorted(d.glob(f"{n}_tb.*")) if f.suffix in HDL_EXTS)
        rtl = [f for f in sorted(d.iterdir()) if f.suffix in HDL_EXTS and f != tb]
        mem = [f for f in d.iterdir() if f.suffix.lower() in MEM_EXTS]
        jobs.append(SimJob(name=testbench_module(tb) or tb.stem, tb_file=tb, files=rtl + [tb],
                           include_dirs=[d, TB_INCLUDE_DIR], defines={}, mem_files=mem, work_dir=base / n))
    return jobs


# ---------------------------------------------------------------------------------------------
def _prepare(job: SimJob) -> None:
    if job.work_dir.exists():
        remove_tree(job.work_dir)
    job.work_dir.mkdir(parents=True, exist_ok=True)
    for m in job.mem_files:
        shutil.copy2(m, job.work_dir / m.name)


def _xsim(job: SimJob, viv: Vivado, wave: bool, timeout: float, out: Out, verbose: bool) -> SimResult:
    start = time.monotonic()
    log_path = job.work_dir / "sim.log"
    log: list[str] = []

    def step(cmd: list, limit: float) -> tuple[int, str, bool]:
        r = run(cmd, cwd=job.work_dir, timeout=limit,
                on_line=(lambda s: out(f"    | {s}") if verbose and not NOISE.match(s) else None))
        log.append("$ " + " ".join(str(c) for c in cmd))
        log.append(r.output)
        return r.returncode, r.output, r.timed_out

    # Options go through "-f <file>": the Vivado .bat wrappers pass arguments through cmd.exe,
    # which splits on '=' (breaking -d NAME=VALUE) and mangles quotes.
    def q(p: Path | str) -> str:
        return '"' + (p.as_posix() if isinstance(p, Path) else p) + '"'

    def argfile(name: str, lines: list[str]) -> list:
        (job.work_dir / name).write_text("\n".join(lines) + "\n", encoding="utf-8")
        log.append(f"# {name}:\n#   " + "\n#   ".join(lines))
        return ["-f", name]

    defines = dict(job.defines)
    defines.setdefault("SIMULATION", "1")
    common = ["--relax"]
    for d in job.include_dirs:
        common.append(f"-i {q(d)}")
    for k, v in defines.items():
        common.append(f"-d {k}={v}")
    v_files = [q(f) for f in job.files if f.suffix.lower() == ".v"]
    sv_files = [q(f) for f in job.files if f.suffix.lower() == ".sv"]
    vhd_files = [q(f) for f in job.files if f.suffix.lower() in (".vhd", ".vhdl")]
    if viv.glbl.is_file():
        v_files.append(q(viv.glbl))

    def finish(status: str, summary: str, failures: list[str] | None = None, wave_path: str | None = None):
        log_path.write_text("\n".join(log), encoding="utf-8")
        return SimResult(job.name, rel(job.tb_file), "xsim", status, time.monotonic() - start, rel(log_path),
                         summary, failures or [], wave_path)

    compile_steps = []
    if v_files:
        compile_steps.append([viv.tool("xvlog"), *argfile("xvlog_v.args", common + v_files)])
    if sv_files:
        compile_steps.append([viv.tool("xvlog"), *argfile("xvlog_sv.args", ["-sv"] + common + sv_files)])
    if vhd_files:
        compile_steps.append([viv.tool("xvhdl"), *argfile("xvhdl.args", ["--2008", "--relax"] + vhd_files)])
    for cmd in compile_steps:
        rc, output, to = step(cmd, 300)
        if rc != 0 or to:
            errs = _error_lines(output)
            return finish("error", errs[0] if errs else "compile failed", errs)
    snap = f"{job.name}_snap"
    elab_opts = ["--relax", f"--timescale {DEFAULT_TIMESCALE}", f"--debug {'typical' if wave else 'off'}",
                 "-L unisims_ver", "-L unimacro_ver", "-L secureip", f"-s {snap}", f"work.{job.name}"]
    if viv.glbl.is_file():
        elab_opts.append("work.glbl")
    rc, output, to = step([viv.tool("xelab"), *argfile("xelab.args", elab_opts)], 300)
    if rc != 0 or to:
        errs = _error_lines(output)
        return finish("error", errs[0] if errs else "elaboration failed", errs)
    wave_path = None
    if wave:
        (job.work_dir / "run.tcl").write_text("log_wave -recursive *\nrun all\nquit\n", encoding="utf-8")
        sim_cmd = [viv.tool("xsim"), snap, "-tclbatch", "run.tcl", "-wdb", "waves.wdb"]
        wave_path = rel(job.work_dir / "waves.wdb")
    else:
        sim_cmd = [viv.tool("xsim"), snap, "-R"]
    rc, output, to = step(sim_cmd, timeout)
    body = "\n".join(ln for ln in output.splitlines() if not NOISE.match(ln))
    status, failures, summary = judge(body, rc, to)
    return finish(status, summary, failures, wave_path)


def _icarus(job: SimJob, ivl: Icarus, wave: bool, timeout: float, out: Out, verbose: bool) -> SimResult:
    start = time.monotonic()
    log_path = job.work_dir / "sim.log"
    log: list[str] = []
    if any(f.suffix.lower() in (".vhd", ".vhdl") for f in job.files):
        log_path.write_text("Icarus Verilog cannot simulate VHDL.", encoding="utf-8")
        return SimResult(job.name, rel(job.tb_file), "iverilog", "error", 0.0, rel(log_path),
                         "Icarus Verilog cannot simulate VHDL: use xsim (Vivado)")
    ts = job.work_dir / "forge_timescale.v"
    ts.write_text(f"`timescale {DEFAULT_TIMESCALE}\n", encoding="utf-8")
    roots = ["-s", job.name]
    extra: list[str] = []
    wave_path = None
    if wave:
        wf = job.work_dir / "forge_wave.v"
        wf.write_text(f'`timescale {DEFAULT_TIMESCALE}\nmodule forge_wave;\ninitial begin\n'
                      f'  $dumpfile("waves.vcd");\n  $dumpvars(0, {job.name});\nend\nendmodule\n', encoding="utf-8")
        roots += ["-s", "forge_wave"]
        extra.append(wf.as_posix())
        wave_path = rel(job.work_dir / "waves.vcd")
    # Plain Verilog files are compiled as Verilog-2005 so SystemVerilog keywords (logic, expect, ...)
    # stay usable as names; SystemVerilog mode only when the job has .sv files.
    gen = "-g2012" if any(f.suffix.lower() == ".sv" for f in job.files) else "-g2005"
    cmd = [ivl.iverilog, gen, "-Wimplicit", "-o", "sim.vvp", *roots]
    for d in job.include_dirs:
        cmd += ["-I", d.as_posix()]
    defines = dict(job.defines)
    defines.setdefault("SIMULATION", "1")
    for k, v in defines.items():
        cmd.append(f"-D{k}={v}")
    cmd += [ts.as_posix(), *[f.as_posix() for f in job.files], *extra]

    def finish(status: str, summary: str, failures: list[str] | None = None):
        log_path.write_text("\n".join(log), encoding="utf-8")
        return SimResult(job.name, rel(job.tb_file), "iverilog", status, time.monotonic() - start, rel(log_path),
                         summary, failures or [], wave_path)

    r = run(cmd, cwd=job.work_dir, timeout=300, on_line=(lambda s: out(f"    | {s}")) if verbose else None)
    log += ["$ " + " ".join(str(c) for c in cmd), r.output]
    if r.returncode != 0 or r.timed_out:
        errs = [ln.strip() for ln in r.output.splitlines() if "error" in ln.lower()][:15]
        return finish("error", errs[0] if errs else "compile failed", errs)
    r = run([ivl.vvp, "-n", "sim.vvp"], cwd=job.work_dir, timeout=timeout,
            on_line=(lambda s: out(f"    | {s}")) if verbose else None)
    log += ["$ vvp -n sim.vvp", r.output]
    status, failures, summary = judge(r.output, r.returncode, r.timed_out)
    return finish(status, summary, failures)


def run_jobs(jobs: list[SimJob], simulator: str, vivado: Vivado | None, icarus: Icarus | None, *,
             wave: bool = False, gui: bool = False, timeout: float = 300, out: Out, verbose: bool = False,
             build_root: Path) -> list[SimResult]:
    if simulator == "auto":
        simulator = "xsim" if vivado else ("iverilog" if icarus else "")
    if simulator == "xsim" and not vivado:
        raise ForgeError("Vivado (xsim) not found.", hint="Set 'vivado' in forge.local.toml or $VIVADO_PATH, "
                                                          "or simulate with --simulator iverilog.")
    if simulator == "iverilog" and not icarus:
        raise ForgeError("Icarus Verilog not found.", hint="Install it (https://bleyer.org/icarus/ on Windows, "
                                                           "'apt install iverilog' on Linux) or use xsim.")
    if not simulator:
        raise ForgeError("No simulator found (need Vivado or Icarus Verilog).")
    ensure_build_dir(build_root)
    results = []
    for job in jobs:
        _prepare(job)
        out(f"  RUN   {job.name}  [{simulator}]")
        if simulator == "xsim":
            res = _xsim(job, vivado, wave, timeout, out, verbose)
        else:
            res = _icarus(job, icarus, wave, timeout, out, verbose)
        tag = {"passed": "PASS", "failed": "FAIL", "error": "ERROR", "timeout": "TIMEOUT",
               "no_verdict": "NO VERDICT"}[res.status]
        out(f"  {tag:<5} {job.name}  ({res.seconds:.1f} s)  {res.summary}")
        if not res.ok:
            for ln in res.failures[:10]:
                out(f"        {ln}")
            out(f"        log: {res.log}")
        (job.work_dir / "result.json").write_text(json.dumps(res.to_dict(), indent=2), encoding="utf-8")
        results.append(res)
        if gui and res.wave:
            open_wave(job.work_dir / Path(res.wave).name, simulator, vivado, out)
    return results


def open_wave(path: Path, simulator: str, vivado: Vivado | None, out: Out) -> None:
    if simulator == "xsim" and vivado:
        launch_detached([vivado.tool("xsim"), "--gui", path.name], cwd=path.parent)
        out(f"  opened waveform viewer: {rel(path)}")
        return
    for viewer in ("surfer", "gtkwave"):
        exe = shutil.which(viewer)
        if exe:
            launch_detached([exe, str(path)])
            out(f"  opened {viewer}: {rel(path)}")
            return
    out(f"  waveform written to {rel(path)} (open it with GTKWave, Surfer or a VS Code VCD viewer)")
