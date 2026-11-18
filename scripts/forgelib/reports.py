"""Turn Vivado reports and logs into structured data (build/reports/summary.json)."""

from __future__ import annotations

import re
from pathlib import Path

MSG_RE = re.compile(r"^(ERROR|CRITICAL WARNING|WARNING):\s*\[([^\]]+)\]\s*(.*?)\s*(?:\[([^\[\]]+?):(\d+)\])?\s*$")
TIMING_COLS = ["wns", "tns", "tns_failing", "tns_total", "whs", "ths", "ths_failing", "ths_total",
               "wpws", "tpws", "tpws_failing", "tpws_total"]


def _num(text: str):
    text = text.strip()
    if text.lower() in ("inf", "nan", "-inf", ""):
        return None
    try:
        return int(text) if re.fullmatch(r"-?\d+", text) else float(text)
    except ValueError:
        return None


def parse_timing_summary(text: str) -> dict:
    """Design Timing Summary numbers plus the check_timing counts (no_clock, no_input_delay, ...)."""
    out: dict = {"met": None, "constrained": True}
    idx = text.find("Design Timing Summary")
    if idx >= 0:
        block = text[idx:idx + 4000].splitlines()
        for i, line in enumerate(block):
            if "WNS(ns)" in line:
                for cand in block[i + 1:i + 5]:
                    # skip the "-------" ruler (but not a negative WNS like "-0.412")
                    if cand.strip() and not re.fullmatch(r"[-\s]+", cand):
                        vals = cand.split()
                        if len(vals) >= len(TIMING_COLS):
                            for k, v in zip(TIMING_COLS, vals):
                                out[k] = _num(v)
                        break
                break
    if "All user specified timing constraints are met" in text:
        out["met"] = True
    elif "Timing constraints are not met" in text:
        out["met"] = False
    if "There are no user specified timing constraints" in text:
        out["constrained"] = False
        out["met"] = None
    checks = {}
    for m in re.finditer(r"^\s*\d+\.\s+checking\s+(\w+)\s+\((\d+)\)", text, re.M):
        checks.setdefault(m.group(1), int(m.group(2)))
    out["checks"] = checks
    return out


UTIL_ROWS = {
    "Slice LUTs": "lut", "CLB LUTs": "lut",
    "Slice Registers": "ff", "CLB Registers": "ff",
    "Block RAM Tile": "bram",
    "DSPs": "dsp",
    "Bonded IOB": "io",
    "BUFGCTRL": "bufg",
    "MMCME2_ADV": "mmcm",
    "PLLE2_ADV": "pll",
}


def parse_utilization(text: str) -> dict:
    out: dict = {}
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            continue
        key = UTIL_ROWS.get(re.sub(r"\*+$", "", cells[0]).strip())
        if not key or key in out:
            continue
        used, avail, util = _num(cells[1]), _num(cells[-2]), _num(cells[-1])
        if used is None:
            continue
        out[key] = {"used": used, "available": avail, "percent": util}
    return out


def parse_rule_table(text: str) -> list[dict]:
    """DRC / methodology summary table rows: rule, severity, description, count."""
    rows = []
    for line in text.splitlines():
        m = re.match(r"^\|\s*([A-Z][A-Z0-9_]*-\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*(\d+)\s*\|", line)
        if m:
            rows.append({"rule": m.group(1), "severity": m.group(2), "description": m.group(3),
                         "count": int(m.group(4))})
    return rows


def parse_messages(text: str, source: str = "") -> list[dict]:
    msgs = []
    seen = set()
    for line in text.splitlines():
        m = MSG_RE.match(line.strip())
        if not m:
            continue
        sev = {"ERROR": "error", "CRITICAL WARNING": "critical_warning", "WARNING": "warning"}[m.group(1)]
        key = (sev, m.group(2), m.group(3))
        if key in seen:
            continue
        seen.add(key)
        d = {"severity": sev, "id": m.group(2), "text": m.group(3)}
        if m.group(4):
            d["file"] = m.group(4)
            d["line"] = int(m.group(5))
        if source:
            d["stage"] = source
        msgs.append(d)
    return msgs


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
