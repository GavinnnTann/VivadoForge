"""Project configuration: forge.toml (committed) + forge.local.toml (per machine, git-ignored)."""

from __future__ import annotations

import glob
import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .common import (CONFIG_NAME, HDL_EXTS, HEADER_EXTS, IP_EXTS, LIB_DIR, LOCAL_CONFIG_NAME, MEM_EXTS,
                     REPO_ROOT, TB_INCLUDE_DIR, ForgeError, natural_key, rel)

SCHEMA = {
    "project": {"name": str, "top": str, "board": str, "sources": list, "lib": list, "constraints": list,
                "include_dirs": list, "defines": dict, "generics": dict},
    "sim": {"tests": list, "timeout": int, "simulator": str},
    "build": {"dir": str, "jobs": int, "synth_strategy": str, "impl_strategy": str, "timing": str},
}
LOCAL_SCHEMA = {"vivado": str, "iverilog": str, "build_dir": str, "jobs": int, "simulator": str}
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")


@dataclass
class Config:
    root: Path
    file: Path
    name: str
    top: str
    board_id: str
    source_patterns: list[str]
    lib: list[str]
    constraint_patterns: list[str]
    include_dirs: list[Path]
    defines: dict[str, str]
    generics: dict[str, str]
    test_patterns: list[str]
    sim_timeout: int
    simulator: str
    build_dir: Path
    jobs: int
    synth_strategy: str
    impl_strategy: str
    timing_policy: str
    vivado_hint: str | None = None
    iverilog_hint: str | None = None
    warnings: list[str] = field(default_factory=list)

    # ---- resolved file sets -------------------------------------------------------------------
    def _glob(self, patterns: list[str]) -> tuple[list[Path], list[str]]:
        """Files matching the patterns, plus literal (wildcard-free) paths that do not exist.

        A wildcard pattern that matches nothing is fine (e.g. src/**/*.sv in a Verilog-only project).
        """
        files: list[Path] = []
        unmatched: list[str] = []
        for pat in patterns:
            full = pat if os.path.isabs(pat) else str(self.root / pat)
            hits = [Path(h) for h in glob.glob(full, recursive=True) if Path(h).is_file()]
            if not hits and not any(ch in pat for ch in "*?["):
                unmatched.append(pat)
            for h in sorted(hits, key=lambda p: natural_key(p.as_posix())):
                if h.resolve() not in {f.resolve() for f in files}:
                    files.append(h)
        return files, unmatched

    def lib_files(self) -> tuple[list[Path], list[str]]:
        """RTL files of the lib/ modules named in [project].lib (testbenches excluded)."""
        files, missing = [], []
        for name in self.lib:
            d = LIB_DIR / name
            if not d.is_dir():
                missing.append(name)
                continue
            for f in sorted(d.iterdir(), key=lambda p: p.name):
                if f.suffix in HDL_EXTS and not f.stem.endswith("_tb"):
                    files.append(f)
        return files, missing

    def source_files(self) -> tuple[list[Path], list[str]]:
        files, unmatched = self._glob(self.source_patterns)
        lib_files, missing = self.lib_files()
        return files + lib_files, unmatched + [f"lib:{m}" for m in missing]

    def constraint_files(self) -> tuple[list[Path], list[str]]:
        return self._glob(self.constraint_patterns)

    def test_files(self) -> tuple[list[Path], list[str]]:
        return self._glob(self.test_patterns)

    def classified_sources(self) -> dict[str, list[Path]]:
        """Split sources into compile groups: verilog, systemverilog, vhdl, header, mem, ip, other."""
        files, _ = self.source_files()
        out: dict[str, list[Path]] = {"verilog": [], "systemverilog": [], "vhdl": [], "header": [],
                                      "mem": [], "ip": [], "other": []}
        for f in files:
            ext = f.suffix.lower()
            if ext in HDL_EXTS:
                out[HDL_EXTS[ext]].append(f)
            elif ext in HEADER_EXTS:
                out["header"].append(f)
            elif ext in MEM_EXTS:
                out["mem"].append(f)
            elif ext in IP_EXTS:
                out["ip"].append(f)
            else:
                out["other"].append(f)
        return out

    def all_include_dirs(self) -> list[Path]:
        dirs: list[Path] = []
        groups = self.classified_sources()
        for f in groups["header"] + groups["verilog"] + groups["systemverilog"]:
            if f.parent not in dirs:
                dirs.append(f.parent)
        for d in self.include_dirs:
            if d not in dirs:
                dirs.append(d)
        return dirs

    @property
    def bitstream(self) -> Path:
        return self.build_dir / "vivado" / f"{self.name}.runs" / "impl_1" / f"{self.top}.bit"

    @property
    def xpr(self) -> Path:
        return self.build_dir / "vivado" / f"{self.name}.xpr"

    @property
    def summary_file(self) -> Path:
        return self.build_dir / "reports" / "summary.json"

    def to_dict(self) -> dict:
        srcs, _ = self.source_files()
        cons, _ = self.constraint_files()
        tests, _ = self.test_files()
        return {
            "root": rel(self.root),
            "config": rel(self.file),
            "name": self.name,
            "top": self.top,
            "board": self.board_id,
            "sources": [rel(p) for p in srcs],
            "lib": self.lib,
            "constraints": [rel(p) for p in cons],
            "tests": [rel(p) for p in tests],
            "include_dirs": [rel(p) for p in self.include_dirs],
            "defines": self.defines,
            "generics": self.generics,
            "build_dir": self.build_dir.as_posix(),
            "jobs": self.jobs,
            "synth_strategy": self.synth_strategy,
            "impl_strategy": self.impl_strategy,
            "timing_policy": self.timing_policy,
            "sim": {"timeout": self.sim_timeout, "simulator": self.simulator},
        }


def find_config(start: Path | None) -> Path:
    """Locate forge.toml: a given file, a given directory, or the repo root."""
    if start is None:
        start = Path.cwd()
        for d in [start, *start.parents]:
            if (d / CONFIG_NAME).is_file():
                return d / CONFIG_NAME
        if (REPO_ROOT / CONFIG_NAME).is_file():
            return REPO_ROOT / CONFIG_NAME
        raise ForgeError(f"No {CONFIG_NAME} found.", hint="Create one with: python scripts/forge.py new --template blink --board <board>")
    start = Path(start)
    if start.is_dir():
        start = start / CONFIG_NAME
    if not start.is_file():
        raise ForgeError(f"{start} not found.")
    return start


def _check_types(table: dict, schema: dict, where: str, warnings: list[str]) -> None:
    for key, value in table.items():
        if key not in schema:
            close = [k for k in schema if k[:3] == key[:3]]
            warnings.append(f"unknown key '{where}.{key}' is ignored" + (f" (did you mean '{close[0]}'?)" if close else ""))
            continue
        expected = schema[key]
        if isinstance(expected, dict):
            if not isinstance(value, dict):
                raise ForgeError(f"[{key}] must be a table in {CONFIG_NAME}")
            _check_types(value, expected, key, warnings)
        elif expected is int and isinstance(value, bool) or not isinstance(value, expected):
            raise ForgeError(f"'{where}.{key}' must be a {expected.__name__} in {CONFIG_NAME} (got {type(value).__name__})")


def load_config(path: Path | None = None) -> Config:
    file = find_config(path)
    root = file.parent
    try:
        data = tomllib.loads(file.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ForgeError(f"{rel(file)} is not valid TOML: {exc}")
    warnings: list[str] = []
    _check_types(data, SCHEMA, "", warnings)
    warnings = [w.replace("'.", "'") for w in warnings]

    local: dict = {}
    local_file = root / LOCAL_CONFIG_NAME
    if local_file.is_file():
        try:
            local = tomllib.loads(local_file.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            raise ForgeError(f"{rel(local_file)} is not valid TOML: {exc}")
        for key, value in local.items():
            if key not in LOCAL_SCHEMA:
                warnings.append(f"unknown key '{key}' in {LOCAL_CONFIG_NAME} is ignored")
            elif not isinstance(value, LOCAL_SCHEMA[key]):
                raise ForgeError(f"'{key}' in {LOCAL_CONFIG_NAME} must be a {LOCAL_SCHEMA[key].__name__}")

    project = data.get("project", {})
    sim = data.get("sim", {})
    build = data.get("build", {})
    for key in ("name", "top", "board"):
        if not project.get(key):
            raise ForgeError(f"[project].{key} is required in {rel(file)}")
    name, top = project["name"], project["top"]
    if not NAME_RE.match(name):
        raise ForgeError(f"[project].name '{name}' must start with a letter and use only letters, digits, '_' or '-'.")
    if not IDENT_RE.match(top):
        raise ForgeError(f"[project].top '{top}' is not a valid HDL identifier.")

    def as_str_dict(d: dict, what: str) -> dict[str, str]:
        out = {}
        for k, v in d.items():
            if not IDENT_RE.match(k):
                raise ForgeError(f"{what} key '{k}' is not a valid identifier")
            out[k] = str(int(v)) if isinstance(v, bool) else str(v)
        return out

    build_dir_text = os.environ.get("FORGE_BUILD_DIR") or local.get("build_dir") or build.get("dir", "build")
    build_dir_text = build_dir_text.replace("{name}", name)
    build_dir = Path(build_dir_text)
    if not build_dir.is_absolute():
        build_dir = root / build_dir

    timing = build.get("timing", "error")
    if timing not in ("error", "warn"):
        raise ForgeError("[build].timing must be \"error\" or \"warn\"")
    simulator = local.get("simulator") or sim.get("simulator", "auto")
    if simulator not in ("auto", "xsim", "iverilog"):
        raise ForgeError("[sim].simulator must be \"auto\", \"xsim\" or \"iverilog\"")

    include_dirs = [(root / d) if not os.path.isabs(d) else Path(d) for d in project.get("include_dirs", [])]
    include_dirs.append(TB_INCLUDE_DIR)

    cfg = Config(
        root=root,
        file=file,
        name=name,
        top=top,
        board_id=project["board"],
        source_patterns=[str(s) for s in project.get("sources", ["src/**/*.v", "src/**/*.sv"])],
        lib=[str(s) for s in project.get("lib", [])],
        constraint_patterns=[str(s) for s in project.get("constraints", ["constraints/*.xdc"])],
        include_dirs=include_dirs,
        defines=as_str_dict(project.get("defines", {}), "[project].defines"),
        generics=as_str_dict(project.get("generics", {}), "[project].generics"),
        test_patterns=[str(s) for s in sim.get("tests", ["tb/*_tb.v", "tb/*_tb.sv"])],
        sim_timeout=int(sim.get("timeout", 300)),
        simulator=simulator,
        build_dir=build_dir,
        jobs=int(local.get("jobs", build.get("jobs", 4))),
        synth_strategy=build.get("synth_strategy", "Vivado Synthesis Defaults"),
        impl_strategy=build.get("impl_strategy", "Vivado Implementation Defaults"),
        timing_policy=timing,
        vivado_hint=local.get("vivado"),
        iverilog_hint=local.get("iverilog"),
        warnings=warnings,
    )
    return cfg


def write_local_setting(root: Path, key: str, value: str) -> Path:
    """Set one key in forge.local.toml, keeping the other lines."""
    if key not in LOCAL_SCHEMA:
        raise ForgeError(f"'{key}' is not a {LOCAL_CONFIG_NAME} setting")
    path = root / LOCAL_CONFIG_NAME
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else [
        "# Per-machine VivadoForge settings. Git-ignored: do not commit.",
    ]
    if LOCAL_SCHEMA[key] is str:
        # Forward slashes: backslashes would be escape characters in a TOML string.
        safe = str(value).replace("\\", "/").replace('"', '\\"')
        rendered = f'{key} = "{safe}"'
    else:
        rendered = f"{key} = {int(value)}"
    for i, line in enumerate(lines):
        if re.match(rf"^\s*{re.escape(key)}\s*=", line):
            lines[i] = rendered
            break
    else:
        lines.append(rendered)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
