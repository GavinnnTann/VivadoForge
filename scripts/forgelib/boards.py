"""Board definitions: boards/<id>/board.json plus the board's master XDC (the pin authority)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .common import BOARDS_DIR, ForgeError, load_json, natural_key, rel
from .xdc import Xdc, XdcPort, read_xdc

REQUIRED_KEYS = ("name", "part", "master_xdc", "clock", "roles")


@dataclass
class Role:
    name: str
    ports: list[str]
    dir: str = "inout"
    active_low: bool | None = None
    note: str = ""

    def to_dict(self) -> dict:
        d = {"ports": self.ports, "dir": self.dir, "note": self.note}
        if self.active_low is not None:
            d["active_low"] = self.active_low
        return d


@dataclass
class Board:
    id: str
    dir: Path
    data: dict
    master: Xdc
    roles: dict[str, Role] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.data["name"]

    @property
    def part(self) -> str:
        return self.data["part"]

    @property
    def clock_port(self) -> str:
        return self.data["clock"]["port"]

    @property
    def clock_hz(self) -> int:
        return int(self.data["clock"]["freq_hz"])

    @property
    def clock_period_ns(self) -> float:
        return 1e9 / self.clock_hz

    @property
    def clock_pin(self) -> str | None:
        port = self.master.ports.get(self.clock_port)
        return port.pin if port else None

    @property
    def flash(self) -> dict:
        return self.data.get("flash", {})

    @property
    def xdc_config(self) -> list[str]:
        return list(self.data.get("xdc_config", []))

    @property
    def master_path(self) -> Path:
        return self.dir / self.data["master_xdc"]

    def roles_of(self, master_port: str) -> list[Role]:
        """The roles (led, button, uart_rx, ...) that a master XDC port belongs to."""
        return [r for r in self.roles.values() if master_port in r.ports]

    def pins_by_package_pin(self) -> dict[str, list[XdcPort]]:
        """Package pin -> master ports. A pin can have several names (e.g. Arduino A6 is also XADC vaux12)."""
        out: dict[str, list[XdcPort]] = {}
        for p in self.master.ports.values():
            if p.pin:
                out.setdefault(p.pin.upper(), []).append(p)
        return out

    def summary(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "vendor": self.data.get("vendor", ""),
            "part": self.part,
            "clock": {"port": self.clock_port, "pin": self.clock_pin, "freq_hz": self.clock_hz,
                      "period_ns": round(self.clock_period_ns, 3)},
            "master_xdc": rel(self.master_path),
            "reference_manual": self.data.get("reference_manual", ""),
            "flash": self.flash,
            "roles": {k: v.to_dict() for k, v in self.roles.items()},
            "notes": self.data.get("notes", []),
        }


def _expand(pattern: str, names: list[str]) -> list[str]:
    """Expand 'led[*]' or 'pio*' against master port names (natural order)."""
    if "*" not in pattern:
        return [pattern]
    regex = re.compile("^" + re.escape(pattern).replace(r"\*", r"[^\s]*") + "$")
    return sorted((n for n in names if regex.match(n)), key=natural_key)


def board_ids() -> list[str]:
    if not BOARDS_DIR.is_dir():
        return []
    return sorted(p.parent.name for p in BOARDS_DIR.glob("*/board.json"))


def load_board(board_id: str) -> Board:
    bdir = BOARDS_DIR / board_id
    bfile = bdir / "board.json"
    if not bfile.is_file():
        raise ForgeError(f"Unknown board '{board_id}'.",
                         hint=f"Known boards: {', '.join(board_ids()) or 'none'}. "
                              "Add one with boards/<id>/board.json + master.xdc (see docs/boards.md).", code="board")
    try:
        data = load_json(bfile)
    except ForgeError as exc:
        exc.code = "board"
        raise
    missing = [k for k in REQUIRED_KEYS if k not in data]
    if missing:
        raise ForgeError(f"{rel(bfile)} is missing keys: {', '.join(missing)}", code="board")
    master_path = bdir / data["master_xdc"]
    if not master_path.is_file():
        raise ForgeError(f"{rel(bfile)}: master_xdc '{data['master_xdc']}' not found.", code="board")
    master = read_xdc(master_path, include_commented=True)
    board = Board(id=board_id, dir=bdir, data=data, master=master)
    names = list(master.ports)
    for rname, rdata in data["roles"].items():
        ports: list[str] = []
        for pat in rdata.get("ports", []):
            ports.extend(_expand(pat, names))
        board.roles[rname] = Role(name=rname, ports=ports, dir=rdata.get("dir", "inout"),
                                  active_low=rdata.get("active_low"), note=rdata.get("note", ""))
    return board


def validate_board(board: Board) -> list[str]:
    """Problems with a board definition (empty list when it is consistent)."""
    problems = []
    if not re.match(r"^xc\d", board.part, re.I):
        problems.append(f"part '{board.part}' does not look like a Xilinx part number")
    if board.clock_port not in board.master.ports:
        problems.append(f"clock port '{board.clock_port}' is not in {board.data['master_xdc']}")
    if board.clock_hz <= 0:
        problems.append("clock freq_hz must be positive")
    for role in board.roles.values():
        if not role.ports:
            problems.append(f"role '{role.name}' matches no ports in the master XDC")
        for p in role.ports:
            if p not in board.master.ports:
                problems.append(f"role '{role.name}' names port '{p}', which is not in the master XDC")
            elif not board.master.ports[p].pin:
                problems.append(f"role '{role.name}' port '{p}' has no PACKAGE_PIN in the master XDC")
    for port in board.master.ports.values():
        if not port.pin:
            problems.append(f"master port '{port.name}' has no PACKAGE_PIN")
        elif not port.iostandard:
            problems.append(f"master port '{port.name}' has no IOSTANDARD")
    return problems
