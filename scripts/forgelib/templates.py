"""`forge.py new` (project from a template) and `forge.py pins` (copy pins from the board master)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .boards import Board, load_board
from .build_dir import remove_tree
from .common import CONFIG_NAME, REPO_ROOT, TEMPLATES_DIR, ForgeError, load_json, natural_key, rel
from .config import Config
from .xdc import XdcPort, clock_line, pin_line, read_xdc

PROJECT_DIRS = ("src", "tb", "constraints")


@dataclass
class Template:
    name: str
    dir: Path
    data: dict

    @property
    def description(self) -> str:
        return self.data.get("description", "")


def template_names() -> list[str]:
    if not TEMPLATES_DIR.is_dir():
        return []
    return sorted(p.parent.name for p in TEMPLATES_DIR.glob("*/template.json"))


def load_template(name: str) -> Template:
    d = TEMPLATES_DIR / name
    if not (d / "template.json").is_file():
        raise ForgeError(f"Unknown template '{name}'.", hint=f"Templates: {', '.join(template_names())}")
    return Template(name, d, load_json(d / "template.json"))


# ---------------------------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------------------------
def _param_value(expr: str, board: Board) -> int:
    parts = expr.split("|")
    head = parts[0].strip()
    if re.fullmatch(r"-?\d+", head):
        value = int(head)
    elif head == "clock_hz":
        value = board.clock_hz
    elif head.startswith("count:"):
        role = board.roles.get(head[6:])
        value = len(role.ports) if role else 0
    elif head.startswith("active_low:"):
        role = board.roles.get(head[11:])
        value = 1 if (role and role.active_low) else 0
    else:
        raise ForgeError(f"unknown template parameter expression '{expr}'")
    for mod in parts[1:]:
        op, _, num = mod.partition(":")
        if op == "max":
            value = min(value, int(num))
        elif op == "min":
            value = max(value, int(num))
    return value


def compatible(t: Template, board: Board) -> list[str]:
    """Reasons why template t cannot target board (empty list = compatible)."""
    problems = []
    for port, spec in t.data.get("ports", {}).items():
        role = board.roles.get(spec["role"])
        if role is None or not role.ports:
            problems.append(f"needs a '{spec['role']}' (for port {port})")
    for role_name, minimum in t.data.get("requires", {}).items():
        role = board.roles.get(role_name)
        have = len(role.ports) if role else 0
        if have < minimum:
            problems.append(f"needs at least {minimum} '{role_name}' ports (board has {have})")
    return problems


def _port_map(t: Template, board: Board, params: dict[str, int]) -> list[tuple[XdcPort, str]]:
    """(master port, design port bit name) pairs for every top-level port."""
    pairs = []
    for port, spec in t.data["ports"].items():
        role = board.roles[spec["role"]]
        if "width" in spec:
            width = params[spec["width"]] if isinstance(spec["width"], str) else int(spec["width"])
            if width > len(role.ports):
                raise ForgeError(f"port {port} needs {width} '{role.name}' pins; {board.id} has {len(role.ports)}")
            for i in range(width):
                pairs.append((board.master.ports[role.ports[i]], f"{port}[{i}]"))
        else:
            idx = int(spec.get("index", 0))
            pairs.append((board.master.ports[role.ports[idx]], port))
    return pairs


def xdc_header(title: str, board: Board) -> list[str]:
    lines = [f"## {title}",
             f"## Board: {board.name} ({board.part}). Pins copied from {rel(board.master_path)}.",
             "## Add pins with `python scripts/forge.py pins add <board port>=<your port>`; never type pin",
             "## numbers from memory. `python scripts/forge.py check` verifies this file against the board.",
             ""]
    if board.xdc_config:
        lines.append("## Board configuration")
        lines += board.xdc_config
        lines.append("")
    return lines


def render_xdc(board: Board, pairs: list[tuple[XdcPort, str]], title: str) -> str:
    lines = xdc_header(title, board)
    section = None
    for master, design in pairs:
        if master.section != section:
            section = master.section
            lines.append(f"## {section}")
        lines.append(pin_line(master, design))
        if master.name == board.clock_port:
            lines.append(clock_line(board.clock_period_ns, design))
    return "\n".join(lines) + "\n"


def _substitute(text: str, params: dict[str, int], path: Path) -> str:
    def rep(m: re.Match) -> str:
        key = m.group(1)
        if key not in params:
            raise ForgeError(f"{rel(path)} uses unknown template parameter {{{{{key}}}}}")
        return str(params[key])
    return re.sub(r"\{\{\s*([A-Za-z_]\w*)\s*\}\}", rep, text)


def render_config(name: str, top: str, board_id: str, lib: list[str], template: str) -> str:
    lib_text = ", ".join(f'"{x}"' for x in lib)

    def line(setting: str, comment: str = "") -> str:
        return f"{setting:<38}# {comment}" if comment else setting

    rows = [
        "# VivadoForge project configuration: the one file you edit.",
        "# Paths are relative to this file. Check it with: python scripts/forge.py check",
        f'# Created from template "{template}". Reference: docs/configuration.md',
        "",
        "[project]",
        line(f'name = "{name}"', "Vivado project name (letters, digits, _ and -)"),
        line(f'top = "{top}"', "top-level module: its ports are the FPGA pins"),
        line(f'board = "{board_id}"', "a folder in boards/ (list: python scripts/forge.py boards)"),
        'sources = ["src/**/*.v", "src/**/*.sv", "src/**/*.vhd", "src/**/*.mem"]',
        line(f"lib = [{lib_text}]", "tested modules from lib/ (list: python scripts/forge.py lib)"),
        'constraints = ["constraints/*.xdc"]',
        "",
        "[sim]",
        line('tests = ["tb/*_tb.v", "tb/*_tb.sv"]', "one testbench per file; module name = file name"),
        line("timeout = 300", "seconds per test before it is killed"),
        "",
        "[build]",
        line('dir = "build"', "per-machine override: build_dir in forge.local.toml"),
        line("jobs = 4", "parallel Vivado jobs"),
        line('timing = "error"', '"error": failed timing fails the build; "warn": report only'),
    ]
    return "\n".join(rows) + "\n"


def new_project(template_name: str, board_id: str, dest: Path, name: str | None, force: bool) -> dict:
    t = load_template(template_name)
    board = load_board(board_id)
    problems = compatible(t, board)
    if problems:
        ok = [b for b in _board_ids() if not compatible(t, load_board(b))]
        raise ForgeError(f"Template '{t.name}' does not fit {board.name}: " + "; ".join(problems),
                         hint=f"Boards that fit: {', '.join(ok) or 'none'}")
    dest = dest.resolve()
    existing = [p for d in PROJECT_DIRS if (dest / d).is_dir() for p in (dest / d).rglob("*") if p.is_file()]
    if existing and not force:
        listing = ", ".join(rel(p, dest) for p in existing[:6]) + (" ..." if len(existing) > 6 else "")
        raise ForgeError(f"{rel(dest)} already has project files ({listing}).",
                         hint="Re-run with --force to replace src/, tb/ and constraints/ (they are deleted first), "
                              "or use --dir to create the project somewhere else.")
    if force:
        # Empty the folders rather than deleting them: on Windows an editor or OneDrive often holds
        # a handle on the folder itself, which makes removing it fail.
        for d in PROJECT_DIRS:
            if (dest / d).is_dir():
                for child in (dest / d).iterdir():
                    if child.is_dir() and not child.is_symlink():
                        remove_tree(child)
                    else:
                        child.unlink()

    params = {k: _param_value(v, board) for k, v in t.data.get("params", {}).items()}
    top = t.data["top"]
    written = []
    for sub in ("src", "tb"):
        sdir = t.dir / sub
        if not sdir.is_dir():
            continue
        for f in sorted(sdir.rglob("*")):
            if f.is_file():
                out = dest / sub / f.relative_to(sdir)
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(_substitute(f.read_text(encoding="utf-8"), params, f), encoding="utf-8")
                written.append(out)
    pairs = _port_map(t, board, params)
    xdc = dest / "constraints" / f"{top}.xdc"
    xdc.parent.mkdir(parents=True, exist_ok=True)
    xdc.write_text(render_xdc(board, pairs, f"Pin constraints for {top} (template '{t.name}')"), encoding="utf-8")
    written.append(xdc)
    cfg_path = dest / CONFIG_NAME
    cfg_path.write_text(render_config(name or t.data.get("name", t.name), top, board.id,
                                      t.data.get("lib", []), t.name), encoding="utf-8")
    written.append(cfg_path)
    return {"template": t.name, "board": board.id, "project": rel(dest), "top": top, "params": params,
            "files": [rel(p) for p in written],
            "pins": [{"design": d, "board_port": m.name, "pin": m.pin} for m, d in pairs]}


def _board_ids() -> list[str]:
    from .boards import board_ids
    return board_ids()


# ---------------------------------------------------------------------------------------------
# pins
# ---------------------------------------------------------------------------------------------
def _resolve_spec(spec: str, board: Board) -> list[tuple[XdcPort, str]]:
    src, _, dst = spec.partition("=")
    src, dst = src.strip(), dst.strip()
    names = list(board.master.ports)
    if src in board.master.ports:
        chosen = [src]
    elif any(n.startswith(src + "[") for n in names):
        chosen = sorted((n for n in names if n.startswith(src + "[")), key=natural_key)
    elif src in board.roles:
        chosen = board.roles[src].ports
    else:
        close = [n for n in names if n.lower().startswith(src.lower()[:3])][:8]
        raise ForgeError(f"'{src}' is not a port or role on {board.name}.",
                         hint=("Similar: " + ", ".join(close) + ". " if close else "") + "List them with: python scripts/forge.py pins")
    if not dst:
        return [(board.master.ports[n], n) for n in chosen]
    if len(chosen) == 1:
        return [(board.master.ports[chosen[0]], dst)]
    base = dst.split("[")[0]
    return [(board.master.ports[n], f"{base}[{i}]") for i, n in enumerate(chosen)]


def pins_add(cfg: Config, board: Board, specs: list[str], target: Path | None) -> dict:
    pairs = [p for s in specs for p in _resolve_spec(s, board)]
    cons, _ = cfg.constraint_files()
    if target is None:
        target = cons[0] if cons else cfg.root / "constraints" / f"{cfg.top}.xdc"
    target = target if target.is_absolute() else cfg.root / target
    existing_ports: dict[str, str] = {}
    existing_pins: dict[str, str] = {}
    for c in cons + ([target] if target.is_file() and target not in cons else []):
        x = read_xdc(c)
        for p in x.ports.values():
            if p.pin:
                existing_ports[p.name] = p.pin.upper()
                existing_pins[p.pin.upper()] = p.name
    added, skipped = [], []
    lines: list[str] = []
    for master, design in pairs:
        pin = (master.pin or "").upper()
        if design in existing_ports:
            skipped.append(f"{design} already constrained (pin {existing_ports[design]})")
            continue
        if pin in existing_pins:
            raise ForgeError(f"pin {pin} ({master.name}) is already used by '{existing_pins[pin]}'")
        lines.append(pin_line(master, design))
        if master.name == board.clock_port:
            lines.append(clock_line(board.clock_period_ns, design))
        existing_ports[design] = pin
        existing_pins[pin] = design
        added.append({"design": design, "board_port": master.name, "pin": master.pin, "iostandard": master.iostandard})
    if lines:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_file():
            text = target.read_text(encoding="utf-8")
            if not text.endswith("\n"):
                text += "\n"
            text += "\n".join(lines) + "\n"
        else:
            text = "\n".join(xdc_header(f"Pin constraints for {cfg.top}", board) + lines) + "\n"
        target.write_text(text, encoding="utf-8")
    return {"file": rel(target), "added": added, "skipped": skipped}


def pins_table(cfg: Config | None, board: Board) -> list[dict]:
    used: dict[str, str] = {}
    if cfg is not None:
        cons, _ = cfg.constraint_files()
        for c in cons:
            for p in read_xdc(c).ports.values():
                if p.pin:
                    used[p.pin.upper()] = p.name
    role_of = {port: (r.name, r.active_low) for r in board.roles.values() for port in r.ports}
    rows = []
    for p in board.master.ports.values():
        role, active_low = role_of.get(p.name, ("", None))
        rows.append({"port": p.name, "pin": p.pin, "iostandard": p.iostandard, "section": p.section,
                     "role": role, "active_low": active_low, "used_by": used.get((p.pin or "").upper())})
    return rows
