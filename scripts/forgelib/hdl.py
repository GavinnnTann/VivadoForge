"""Lightweight HDL scanning: module names, parameters and top-level ports.

This is not a full parser. It understands the common Verilog-2001 / SystemVerilog ANSI and
non-ANSI headers and simple VHDL entities, which is enough to check pin constraints before
Vivado runs. When it cannot work something out it says so instead of guessing.
"""

from __future__ import annotations

import ast
import math
import operator
import re
from dataclasses import dataclass, field
from pathlib import Path

DIRS = ("input", "output", "inout")
_NET_WORDS = {"wire", "reg", "logic", "var", "signed", "unsigned", "tri", "integer", "bit", "byte", "shortint",
              "int", "longint", "supply0", "supply1", "wand", "wor", "uwire"}


@dataclass
class Port:
    name: str
    direction: str
    msb: int | None = None
    lsb: int | None = None
    width_expr: str | None = None   # raw range text when it could not be evaluated

    @property
    def width(self) -> int | None:
        if self.msb is None and self.width_expr is None:
            return 1
        if self.msb is None:
            return None
        return abs(self.msb - self.lsb) + 1

    def bits(self) -> list[str] | None:
        """XDC names for each bit: 'led[0]', 'led[1]' ... or ['clk'] for scalars. None if unknown."""
        if self.msb is None and self.width_expr is None:
            return [self.name]
        if self.msb is None:
            return None
        lo, hi = sorted((self.msb, self.lsb))
        return [f"{self.name}[{i}]" for i in range(lo, hi + 1)]


@dataclass
class Module:
    name: str
    file: Path
    line: int
    language: str
    params: dict[str, str] = field(default_factory=dict)
    ports: list[Port] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------------------------
# Comment stripping and numbers
# ---------------------------------------------------------------------------------------------
def strip_verilog_comments(text: str) -> str:
    """Remove // and /* */ comments, keeping newlines so line numbers stay correct."""
    out = []
    i, n = 0, len(text)
    in_str = False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
        elif c == '"':
            in_str = True
            out.append(c)
            i += 1
        elif text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            seg = text[i:n if j < 0 else j + 2]
            out.append("\n" * seg.count("\n"))
            i = n if j < 0 else j + 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


_SIZED = re.compile(r"(\d+)?\s*'\s*[sS]?([bBoOdDhH])\s*([0-9a-fA-F_xXzZ?]+)")


def _verilog_numbers_to_python(expr: str) -> str:
    def conv(m: re.Match) -> str:
        base = {"b": 2, "o": 8, "d": 10, "h": 16}[m.group(2).lower()]
        digits = m.group(3).replace("_", "")
        if re.search(r"[xXzZ?]", digits):
            raise ValueError("x/z in constant")
        return str(int(digits, base))
    expr = _SIZED.sub(conv, expr)
    expr = re.sub(r"(?<=\d)_(?=\d)", "", expr)
    expr = expr.replace("$clog2", "clog2")
    return expr


_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.FloorDiv: operator.floordiv,
        ast.Div: operator.floordiv, ast.Mod: operator.mod, ast.LShift: operator.lshift, ast.RShift: operator.rshift,
        ast.Pow: operator.pow, ast.BitAnd: operator.and_, ast.BitOr: operator.or_, ast.BitXor: operator.xor}


def _clog2(x: int) -> int:
    return 0 if x <= 1 else math.ceil(math.log2(x))


def eval_int(expr: str, env: dict[str, int]) -> int:
    """Evaluate a Verilog constant expression made of integers, parameters and + - * / % << >> $clog2."""
    expr = _verilog_numbers_to_python(expr.strip())
    tree = ast.parse(expr, mode="eval")

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            return node.value
        if isinstance(node, ast.Name):
            if node.id in env:
                return env[node.id]
            raise ValueError(f"unknown name {node.id}")
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            v = ev(node.operand)
            return -v if isinstance(node.op, ast.USub) else v
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "clog2" and len(node.args) == 1:
            return _clog2(ev(node.args[0]))
        raise ValueError("unsupported expression")
    return int(ev(tree))


# ---------------------------------------------------------------------------------------------
# Verilog / SystemVerilog
# ---------------------------------------------------------------------------------------------
_MODULE_RE = re.compile(r"\b(module|macromodule)\s+(?:automatic\s+|static\s+)?([A-Za-z_][\w$]*)")


def _match_paren(text: str, start: int) -> int:
    """Index of the ')' that closes the '(' at text[start]."""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _split_top(text: str, sep: str = ",") -> list[str]:
    parts, depth, cur = [], 0, []
    for c in text:
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        if c == sep and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(c)
    if "".join(cur).strip():
        parts.append("".join(cur))
    return parts


def _parse_params(text: str, params: dict[str, str]) -> None:
    for item in _split_top(text):
        item = item.strip()
        item = re.sub(r"^\s*(parameter|localparam)\b", "", item).strip()
        m = re.match(r"^(?:[A-Za-z_]\w*\s+)*?(?:\[[^\]]*\]\s*)?([A-Za-z_]\w*)\s*=\s*(.+)$", item, re.S)
        if m:
            params[m.group(1)] = m.group(2).strip()


def _param_env(params: dict[str, str], overrides: dict[str, str] | None = None) -> dict[str, int]:
    raw = dict(params)
    raw.update(overrides or {})
    env: dict[str, int] = {}
    for _ in range(len(raw) + 1):  # resolve parameters that depend on other parameters
        progress = False
        for k, v in raw.items():
            if k in env:
                continue
            try:
                env[k] = eval_int(v, env)
                progress = True
            except (ValueError, SyntaxError, ZeroDivisionError, TypeError):
                pass
        if not progress:
            break
    return env


def _parse_range(rng: str | None, env: dict[str, int]) -> tuple[int | None, int | None, str | None]:
    if not rng:
        return None, None, None
    inner = rng.strip()[1:-1]
    parts = _split_top(inner, ":")
    if len(parts) != 2:
        return None, None, rng
    try:
        return eval_int(parts[0], env), eval_int(parts[1], env), None
    except (ValueError, SyntaxError, ZeroDivisionError, TypeError):
        return None, None, rng


def _decl_ports(decl: str, env: dict[str, int], state: dict) -> list[Port]:
    """Parse 'input wire [7:0] a, b' style text (one ANSI item or one non-ANSI statement)."""
    decl = re.sub(r"\(\*.*?\*\)", " ", decl, flags=re.S).strip()   # attributes
    toks = re.findall(r"\[[^\]]*\]|[A-Za-z_][\w$]*|=|,|\S", decl)
    ports: list[Port] = []
    i = 0
    if toks and toks[0] in DIRS:
        state["dir"] = toks[0]
        state["range"] = None
        i = 1
        while i < len(toks) and (toks[i] in _NET_WORDS or toks[i].startswith("[")):
            if toks[i].startswith("["):
                if state["range"] is None:
                    state["range"] = toks[i]
            i += 1
    def is_name(tok: str | None) -> bool:
        return bool(tok) and bool(re.match(r"^[A-Za-z_]", tok)) and tok not in _NET_WORDS

    while i < len(toks):
        t = toks[i]
        if is_name(t):
            nxt = toks[i + 1] if i + 1 < len(toks) else None
            if is_name(nxt) or (nxt and nxt.startswith("[") and is_name(toks[i + 2] if i + 2 < len(toks) else None)):
                # "my_type x" or "my_type [3:0] x": the first word is a user-defined type, not a port
                i += 1
                if nxt and nxt.startswith("["):
                    state["range"] = nxt
                    i += 1
                continue
            msb, lsb, expr = _parse_range(state.get("range"), env)
            ports.append(Port(name=t, direction=state.get("dir") or "?", msb=msb, lsb=lsb, width_expr=expr))
            i += 1
            while i < len(toks) and toks[i].startswith("["):  # unpacked dims: ignore
                i += 1
            if i < len(toks) and toks[i] == "=":
                while i < len(toks) and toks[i] != ",":
                    i += 1
        else:
            i += 1
    return ports


def parse_verilog_modules(path: Path, text: str | None = None) -> list[Module]:
    raw = text if text is not None else path.read_text(encoding="utf-8", errors="replace")
    src = strip_verilog_comments(raw)
    lang = "systemverilog" if path.suffix.lower() in (".sv", ".svh") else "verilog"
    modules: list[Module] = []
    for m in _MODULE_RE.finditer(src):
        name = m.group(2)
        end = src.find("endmodule", m.end())
        body_end = len(src) if end < 0 else end
        mod = Module(name=name, file=path, line=src.count("\n", 0, m.start()) + 1, language=lang)
        pos = m.end()
        # skip "import pkg::*;" lists
        while True:
            im = re.match(r"\s*import\s+[^;]+;", src[pos:])
            if not im:
                break
            pos += im.end()
        rest = src[pos:body_end]
        k = 0
        pm = re.match(r"\s*#\s*\(", rest)
        if pm:
            open_idx = pm.end() - 1
            close_idx = _match_paren(rest, open_idx)
            if close_idx < 0:
                mod.problems.append("unterminated parameter list")
                modules.append(mod)
                continue
            _parse_params(rest[open_idx + 1:close_idx], mod.params)
            k = close_idx + 1
        # body parameters (parameter X = ...; localparam is not overridable but may size ports in non-ANSI style)
        semi = rest.find(";", k)
        header = rest[k:semi if semi >= 0 else len(rest)]
        body = rest[semi + 1:] if semi >= 0 else ""
        for bm in re.finditer(r"\b(?:parameter|localparam)\b([^;]*);", body):
            _parse_params(bm.group(1), mod.params)
        env = _param_env(mod.params)
        hm = re.match(r"\s*\(", header)
        port_list_text = ""
        if hm:
            close_idx = _match_paren(header, hm.end() - 1)
            port_list_text = header[hm.end():close_idx if close_idx >= 0 else len(header)]
        items = [it.strip() for it in _split_top(port_list_text) if it.strip()]
        ansi = any(re.match(r"^(\(\*.*?\*\)\s*)?(input|output|inout)\b", it, re.S) for it in items)
        if ansi:
            state: dict = {"dir": None, "range": None}
            for it in items:
                if re.match(r"^(\(\*.*?\*\)\s*)?(input|output|inout)\b", it, re.S):
                    mod.ports.extend(_decl_ports(it, env, state))
                else:
                    # continuation of the previous declaration: "input [3:0] a, b"
                    mod.ports.extend(_decl_ports(it, env, dict(state)))
        elif items:
            order = [re.sub(r"[^\w$].*$", "", it.strip()) for it in items]
            found: dict[str, Port] = {}
            for dm in re.finditer(r"\b(input|output|inout)\b([^;]*);", body):
                for p in _decl_ports(dm.group(1) + " " + dm.group(2), env, {"dir": None, "range": None}):
                    found[p.name] = p
            for name_ in order:
                if name_ in found:
                    mod.ports.append(found[name_])
                else:
                    mod.problems.append(f"no direction found for port '{name_}'")
        modules.append(mod)
    return modules


# ---------------------------------------------------------------------------------------------
# VHDL (entities only)
# ---------------------------------------------------------------------------------------------
_VHDL_ENTITY = re.compile(r"\bentity\s+(\w+)\s+is\b(.*?)\bend\b", re.I | re.S)


def parse_vhdl_entities(path: Path, text: str | None = None) -> list[Module]:
    raw = text if text is not None else path.read_text(encoding="utf-8", errors="replace")
    src = re.sub(r"--[^\n]*", "", raw)
    mods = []
    for m in _VHDL_ENTITY.finditer(src):
        mod = Module(name=m.group(1), file=path, line=src.count("\n", 0, m.start()) + 1, language="vhdl")
        body = m.group(2)
        gm = re.search(r"\bgeneric\s*\(", body, re.I)
        env: dict[str, int] = {}
        if gm:
            close = _match_paren(body, gm.end() - 1)
            for item in _split_top(body[gm.end():close], ";"):
                im = re.match(r"\s*(\w+)\s*:\s*\w+[^:]*:=\s*(.+)", item, re.S)
                if im:
                    mod.params[im.group(1)] = im.group(2).strip()
            env = _param_env(mod.params)
        pm = re.search(r"\bport\s*\(", body, re.I)
        if pm:
            close = _match_paren(body, pm.end() - 1)
            for item in _split_top(body[pm.end():close], ";"):
                im = re.match(r"\s*([\w\s,]+?)\s*:\s*(in|out|inout|buffer)\s+(.+)", item, re.I | re.S)
                if not im:
                    continue
                names = [n.strip() for n in im.group(1).split(",") if n.strip()]
                direction = {"in": "input", "out": "output", "inout": "inout", "buffer": "output"}[im.group(2).lower()]
                typ = im.group(3)
                rm = re.search(r"\(\s*(.+?)\s+(downto|to)\s+(.+?)\s*\)", typ, re.I | re.S)
                for n in names:
                    if rm:
                        try:
                            a, b = eval_int(rm.group(1), env), eval_int(rm.group(3), env)
                            mod.ports.append(Port(n, direction, a, b))
                        except (ValueError, SyntaxError, ZeroDivisionError, TypeError):
                            mod.ports.append(Port(n, direction, width_expr=rm.group(0)))
                    else:
                        mod.ports.append(Port(n, direction))
        mods.append(mod)
    return mods


def scan_modules(files: list[Path]) -> list[Module]:
    mods: list[Module] = []
    for f in files:
        ext = f.suffix.lower()
        try:
            if ext in (".v", ".sv", ".vh", ".svh"):
                mods.extend(parse_verilog_modules(f))
            elif ext in (".vhd", ".vhdl"):
                mods.extend(parse_vhdl_entities(f))
        except OSError:
            continue
    return mods


def has_timescale(path: Path) -> bool:
    try:
        return "`timescale" in strip_verilog_comments(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return True
