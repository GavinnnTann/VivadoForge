"""Shared paths, errors and small helpers."""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
BOARDS_DIR = REPO_ROOT / "boards"
LIB_DIR = REPO_ROOT / "lib"
TEMPLATES_DIR = REPO_ROOT / "templates"
FORGE_TCL = SCRIPTS_DIR / "forge.tcl"
TB_INCLUDE_DIR = LIB_DIR / "include"

CONFIG_NAME = "forge.toml"
LOCAL_CONFIG_NAME = "forge.local.toml"
BUILD_MARKER = ".forge-build"

HDL_EXTS = {".v": "verilog", ".sv": "systemverilog", ".vhd": "vhdl", ".vhdl": "vhdl"}
HEADER_EXTS = {".vh", ".svh"}
MEM_EXTS = {".mem", ".hex", ".dat", ".coe"}
IP_EXTS = {".xci"}


class ForgeError(Exception):
    """An error with a message meant for the user (no traceback)."""

    def __init__(self, message: str, hint: str | None = None):
        super().__init__(message)
        self.hint = hint


@dataclass
class Finding:
    """One result of a check: severity is 'error', 'warning' or 'info'."""

    severity: str
    code: str
    message: str
    file: str | None = None
    line: int | None = None
    hint: str | None = None

    def to_dict(self) -> dict:
        d = {"severity": self.severity, "code": self.code, "message": self.message}
        if self.file:
            d["file"] = self.file
        if self.line:
            d["line"] = self.line
        if self.hint:
            d["hint"] = self.hint
        return d

    def format(self) -> str:
        tag = {"error": "ERROR", "warning": "WARN ", "info": "INFO "}.get(self.severity, self.severity.upper())
        where = ""
        if self.file:
            where = f"  --> {self.file}" + (f":{self.line}" if self.line else "")
        text = f"  {tag} [{self.code}] {self.message}{where}"
        if self.hint:
            text += f"\n         hint: {self.hint}"
        return text


@dataclass
class Out:
    """Routes human-readable progress. In --json mode it goes to stderr so stdout stays pure JSON."""

    json_mode: bool = False
    quiet: bool = False
    lines: list[str] = field(default_factory=list)

    def __call__(self, text: str = "") -> None:
        if self.quiet:
            return
        stream = sys.stderr if self.json_mode else sys.stdout
        try:
            print(text, file=stream, flush=True)
        except UnicodeEncodeError:
            print(text.encode("ascii", "replace").decode("ascii"), file=stream, flush=True)


def rel(path: Path | str, base: Path | None = None) -> str:
    """Path relative to base (default: repo root) with forward slashes, or absolute if outside."""
    p = Path(path)
    base = base or REPO_ROOT
    try:
        return p.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return p.resolve().as_posix()


def natural_key(text: str):
    """Sort key so that led[2] < led[10] and pio3 < pio20."""
    return [int(tok) if tok.isdigit() else tok.lower() for tok in re.split(r"(\d+)", text)]


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ForgeError(f"{rel(path)} is not valid JSON: line {exc.lineno} column {exc.colno}: {exc.msg}")


def is_synced_folder(path: Path) -> str | None:
    """Return the name of a cloud-sync service if path is inside one (OneDrive, Dropbox, ...)."""
    text = str(path.resolve()).lower()
    for marker, name in (("onedrive", "OneDrive"), ("dropbox", "Dropbox"), ("google drive", "Google Drive"),
                         ("icloud", "iCloud Drive"), ("box sync", "Box")):
        if marker in text:
            return name
    return None


def python_cmd() -> str:
    """How to invoke Python in printed hints."""
    return "python" if os.name == "nt" else "python3"


def forge_cmd(args: str = "") -> str:
    return f"{python_cmd()} scripts/forge.py {args}".rstrip()
