"""Find Vivado / Icarus Verilog and run external processes with streaming output and timeouts."""

from __future__ import annotations

import glob
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

IS_WINDOWS = os.name == "nt"
EXE = ".bat" if IS_WINDOWS else ""

# Lines the Vivado .bat wrappers print that carry no information.
NOISE = re.compile(r"^(ECHO is off\.|\*{4,}.*|\s*\*\*.*|Copyright .*|# .*source .*|\s*)$")


@dataclass
class Vivado:
    bin_dir: Path
    version: str

    @property
    def root(self) -> Path:
        return self.bin_dir.parent

    def tool(self, name: str) -> Path:
        return self.bin_dir / f"{name}{EXE}"

    @property
    def vivado(self) -> Path:
        return self.tool("vivado")

    @property
    def glbl(self) -> Path:
        return self.root / "data" / "verilog" / "src" / "glbl.v"

    def to_dict(self) -> dict:
        return {"path": self.vivado.as_posix(), "version": self.version}


def _version_of(bin_dir: Path) -> str:
    for part in reversed(bin_dir.parts):
        if re.match(r"^\d{4}\.\d+(\.\d+)?$", part):
            return part
    return "unknown"


def _version_key(v: Vivado):
    nums = re.findall(r"\d+", v.version)
    return tuple(int(n) for n in nums) if nums else (0,)


def _bin_dir_from(path_text: str) -> Path | None:
    p = Path(path_text.strip().strip('"'))
    if p.is_file():
        return p.parent
    for cand in (p / "bin", p):
        if (cand / f"vivado{EXE}").is_file():
            return cand
    return None


def find_vivado(hint: str | None = None) -> Vivado | None:
    """Search: forge.local.toml 'vivado', $VIVADO_PATH, $XILINX_VIVADO, PATH, then standard install folders."""
    for source in (hint, os.environ.get("VIVADO_PATH"), os.environ.get("XILINX_VIVADO")):
        if source:
            b = _bin_dir_from(source)
            if b:
                return Vivado(b, _version_of(b))
    on_path = shutil.which("vivado")
    if on_path:
        b = Path(on_path).resolve().parent
        return Vivado(b, _version_of(b))
    patterns = []
    if IS_WINDOWS:
        for drive in ("C:", "D:", "E:"):
            patterns += [f"{drive}/Xilinx/Vivado/*/bin", f"{drive}/AMD/Vivado/*/bin",
                         f"{drive}/AMDDesignTools/*/Vivado/bin", f"{drive}/Xilinx/*/Vivado/bin"]
    else:
        home = str(Path.home())
        for base in ("/tools/Xilinx", "/opt/Xilinx", f"{home}/Xilinx", "/tools/AMD", "/opt/AMD", "/opt/amd"):
            patterns += [f"{base}/Vivado/*/bin", f"{base}/*/Vivado/bin"]
    found = []
    for pat in patterns:
        for d in glob.glob(pat):
            b = Path(d)
            if (b / f"vivado{EXE}").is_file():
                found.append(Vivado(b, _version_of(b)))
    if not found:
        return None
    return max(found, key=_version_key)


@dataclass
class Icarus:
    iverilog: Path
    vvp: Path
    version: str

    def to_dict(self) -> dict:
        return {"path": self.iverilog.as_posix(), "version": self.version}


def find_iverilog(hint: str | None = None) -> Icarus | None:
    cands = []
    if hint:
        h = Path(hint)
        cands.append(h if h.is_file() else h / ("iverilog.exe" if IS_WINDOWS else "iverilog"))
        cands.append(h / "bin" / ("iverilog.exe" if IS_WINDOWS else "iverilog"))
    w = shutil.which("iverilog")
    if w:
        cands.append(Path(w))
    if IS_WINDOWS:
        cands += [Path("C:/iverilog/bin/iverilog.exe"), Path("C:/Program Files/iverilog/bin/iverilog.exe")]
    for c in cands:
        if c.is_file():
            vvp = c.with_name("vvp.exe" if IS_WINDOWS else "vvp")
            if not vvp.is_file():
                continue
            version = "unknown"
            try:
                r = subprocess.run([str(c), "-V"], capture_output=True, text=True, timeout=20)
                m = re.search(r"version\s+(\S+)", r.stdout + r.stderr)
                version = m.group(1) if m else version
            except (OSError, subprocess.TimeoutExpired):
                pass
            return Icarus(c, vvp, version)
    return None


@dataclass
class RunResult:
    returncode: int
    output: str
    timed_out: bool
    seconds: float


def _kill_tree(proc: subprocess.Popen) -> None:
    try:
        if IS_WINDOWS:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, timeout=30)
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (OSError, subprocess.TimeoutExpired, ProcessLookupError):
        try:
            proc.kill()
        except OSError:
            pass


def run(cmd: list[str | Path], cwd: Path | None = None, timeout: float | None = None,
        on_line: Callable[[str], None] | None = None, log_file: Path | None = None,
        env: dict | None = None) -> RunResult:
    """Run cmd, streaming each output line to on_line, enforcing a wall-clock timeout on the whole tree."""
    args = [str(c) for c in cmd]
    start = time.monotonic()
    kwargs: dict = {}
    if IS_WINDOWS:
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    try:
        proc = subprocess.Popen(args, cwd=str(cwd) if cwd else None, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=env,
                                text=True, encoding="utf-8", errors="replace", bufsize=1, **kwargs)
    except OSError as exc:
        return RunResult(127, f"failed to start {args[0]}: {exc}", False, 0.0)
    timed_out = threading.Event()
    timer = None
    if timeout:
        def expire():
            timed_out.set()
            _kill_tree(proc)
        timer = threading.Timer(timeout, expire)
        timer.daemon = True
        timer.start()
    lines: list[str] = []
    log = open(log_file, "w", encoding="utf-8") if log_file else None
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip("\r\n")
            lines.append(line)
            if log:
                log.write(line + "\n")
            if on_line:
                on_line(line)
        proc.wait()
    except KeyboardInterrupt:
        _kill_tree(proc)
        raise
    finally:
        if timer:
            timer.cancel()
        if log:
            log.close()
    return RunResult(proc.returncode if proc.returncode is not None else -1, "\n".join(lines),
                     timed_out.is_set(), time.monotonic() - start)


def launch_detached(cmd: list[str | Path], cwd: Path | None = None) -> None:
    """Start a GUI program and return immediately."""
    args = [str(c) for c in cmd]
    kwargs: dict = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "stdin": subprocess.DEVNULL}
    if IS_WINDOWS:
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "DETACHED_PROCESS", 0)
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(args, cwd=str(cwd) if cwd else None, **kwargs)


def tool_summary(vivado: Vivado | None, icarus: Icarus | None) -> dict:
    return {
        "vivado": vivado.to_dict() if vivado else None,
        "iverilog": icarus.to_dict() if icarus else None,
        "python": sys.version.split()[0],
    }
