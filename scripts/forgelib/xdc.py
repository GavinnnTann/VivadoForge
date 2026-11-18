"""Read and write the subset of XDC that pin constraints use.

Handles both Digilent master files (every line commented out) and project files:
  set_property -dict { PACKAGE_PIN L17 IOSTANDARD LVCMOS33 } [get_ports { sysclk }]; #comment
  set_property PACKAGE_PIN L17 [get_ports clk]
  set_property IOSTANDARD LVCMOS33 [get_ports {led[*]}]
  create_clock -add -name sys_clk_pin -period 83.33 -waveform {0 41.66} [get_ports {sysclk}];
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from pathlib import Path

_GET_PORTS = r"\[\s*get_ports\s+(\{[^}]*\}|[^\]\s]+)\s*\]"
_DICT_RE = re.compile(r"^\s*(#\s*)?set_property\s+-dict\s+\{([^}]*)\}\s*" + _GET_PORTS + r"\s*;?\s*(#.*)?$")
_PROP_RE = re.compile(r"^\s*(#\s*)?set_property\s+([A-Za-z_][\w.]*)\s+(\{[^}]*\}|\S+)\s*" + _GET_PORTS + r"\s*;?\s*(#.*)?$")
_CLOCK_RE = re.compile(r"^\s*(#\s*)?create_clock\s+(.*?)" + _GET_PORTS + r"\s*;?\s*(#.*)?$")
_SECTION_RE = re.compile(r"^\s*##+\s*(.*?)\s*$")


@dataclass
class XdcPort:
    name: str
    props: dict[str, str] = field(default_factory=dict)
    comment: str = ""
    section: str = ""
    lineno: int = 0
    commented: bool = False

    @property
    def pin(self) -> str | None:
        return self.props.get("PACKAGE_PIN")

    @property
    def iostandard(self) -> str | None:
        return self.props.get("IOSTANDARD")


@dataclass
class XdcClock:
    port: str
    period: float | None
    name: str | None
    waveform: str | None
    lineno: int
    commented: bool


@dataclass
class Xdc:
    path: Path | None
    ports: dict[str, XdcPort] = field(default_factory=dict)
    clocks: list[XdcClock] = field(default_factory=list)
    patterns: list[tuple[str, dict[str, str], int]] = field(default_factory=list)  # wildcard get_ports rules

    def prop_for(self, port: str, key: str) -> str | None:
        """Property for a port, falling back to wildcard rules such as [get_ports {led[*]}]."""
        p = self.ports.get(port)
        if p and key in p.props:
            return p.props[key]
        for pattern, props, _ in reversed(self.patterns):
            if key in props and fnmatch.fnmatchcase(port, _glob_escape(pattern)):
                return props[key]
        return None


def _glob_escape(pattern: str) -> str:
    # In XDC, led[*] means "any bit of led"; in fnmatch [..] is a character class, so make '[' literal.
    return pattern.replace("[", "[[]")


def _port_tokens(raw: str) -> list[str]:
    raw = raw.strip()
    if raw.startswith("{") and raw.endswith("}"):
        raw = raw[1:-1]
    return [t for t in raw.split() if t]


def _dict_pairs(body: str) -> dict[str, str]:
    toks = body.split()
    return {toks[i].upper(): toks[i + 1] for i in range(0, len(toks) - 1, 2)}


def parse_xdc(text: str, path: Path | None = None, include_commented: bool = False) -> Xdc:
    """Parse pin and clock constraints. include_commented=True also reads '#set_property' lines (masters)."""
    xdc = Xdc(path=path)
    section = ""
    for lineno, line in enumerate(text.splitlines(), start=1):
        m = _SECTION_RE.match(line)
        if m and not line.lstrip().startswith("#set_property") and not line.lstrip().startswith("#create_clock"):
            section = m.group(1)
            continue
        m = _DICT_RE.match(line)
        if m:
            commented = bool(m.group(1))
            if commented and not include_commented:
                continue
            props = _dict_pairs(m.group(2))
            comment = (m.group(4) or "").lstrip("#").strip()
            _add_ports(xdc, _port_tokens(m.group(3)), props, comment, section, lineno, commented)
            continue
        m = _PROP_RE.match(line)
        if m:
            commented = bool(m.group(1))
            if commented and not include_commented:
                continue
            key = m.group(2).upper()
            value = m.group(3).strip("{} ")
            comment = (m.group(5) or "").lstrip("#").strip()
            _add_ports(xdc, _port_tokens(m.group(4)), {key: value}, comment, section, lineno, commented)
            continue
        m = _CLOCK_RE.match(line)
        if m:
            commented = bool(m.group(1))
            if commented and not include_commented:
                continue
            opts = m.group(2)
            period = re.search(r"-period\s+([0-9.]+)", opts)
            name = re.search(r"-name\s+(\S+)", opts)
            wave = re.search(r"-waveform\s+(\{[^}]*\})", opts)
            for port in _port_tokens(m.group(3)):
                xdc.clocks.append(XdcClock(port=port, period=float(period.group(1)) if period else None,
                                           name=name.group(1) if name else None,
                                           waveform=wave.group(1) if wave else None,
                                           lineno=lineno, commented=commented))
    return xdc


def _add_ports(xdc: Xdc, names: list[str], props: dict[str, str], comment: str, section: str,
               lineno: int, commented: bool) -> None:
    for name in names:
        if "*" in name or "?" in name:
            xdc.patterns.append((name, dict(props), lineno))
            continue
        port = xdc.ports.get(name)
        if port is None:
            xdc.ports[name] = XdcPort(name=name, props=dict(props), comment=comment, section=section,
                                      lineno=lineno, commented=commented)
        else:
            port.props.update(props)
            port.comment = port.comment or comment


def read_xdc(path: Path, include_commented: bool = False) -> Xdc:
    return parse_xdc(path.read_text(encoding="utf-8", errors="replace"), path, include_commented)


def pin_line(port: XdcPort, design_name: str) -> str:
    """A constraint line for design port design_name using the master port's properties."""
    props = "  ".join(f"{k} {v}" for k, v in port.props.items())
    line = f"set_property -dict {{ {props} }} [get_ports {{ {design_name} }}];"
    if port.comment:
        line += f" #{port.comment}"
    return line


def clock_line(period_ns: float, design_name: str) -> str:
    half = period_ns / 2
    return (f"create_clock -add -name sys_clk_pin -period {period_ns:.3f} "
            f"-waveform {{0 {half:.3f}}} [get_ports {{ {design_name} }}];")
