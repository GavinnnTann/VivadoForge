"""What a bitstream was built from, so program/flash refuse one that no longer matches the design.

A build that writes a bitstream also writes <build>/reports/manifest.json: the content hash of
every input (RTL, memory files, headers, constraints), the settings that change the result
(part, top, defines, generics, strategies) and the hash of the bitstream itself. Before
programming, forge.py recomputes the inputs and compares. Any difference means the bitstream
on disk is not the design in the sources, which stops "edit the RTL, forget to rebuild,
program the old design" (an easy mistake for a person and an easier one for an agent).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import __version__
from .boards import Board
from .common import HEADER_EXTS, ForgeError, forge_cmd, natural_key, rel
from .config import Config

MAX_LISTED = 15


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _headers(cfg: Config) -> list[Path]:
    """Header files in the include path: `include can pull them into the design."""
    out: list[Path] = []
    for d in cfg.all_include_dirs():
        if d.is_dir():
            out += sorted(p for p in d.iterdir() if p.is_file() and p.suffix.lower() in HEADER_EXTS)
    return out


def collect_inputs(cfg: Config, board: Board) -> dict:
    """Everything that decides the bitstream: settings plus a content hash of every input file."""
    srcs, _ = cfg.source_files()
    cons, _ = cfg.constraint_files()
    files: dict[str, str] = {}
    for p in srcs + cons + _headers(cfg):
        key = rel(p)
        if key in files:
            continue
        try:
            files[key] = sha256_file(p)
        except OSError:
            files[key] = "unreadable"
    settings = {
        "board": board.id,
        "part": board.part,
        "name": cfg.name,
        "top": cfg.top,
        "defines": dict(sorted(cfg.defines.items())),
        "generics": dict(sorted(cfg.generics.items())),
        "synth_strategy": cfg.synth_strategy,
        "impl_strategy": cfg.impl_strategy,
    }
    return {"settings": settings, "files": dict(sorted(files.items(), key=lambda kv: natural_key(kv[0])))}


def fingerprint(inputs: dict) -> str:
    return hashlib.sha256(json.dumps(inputs, sort_keys=True).encode("utf-8")).hexdigest()


def compare(old: dict, new: dict) -> list[str]:
    """Readable differences between two collect_inputs() results; an empty list means identical."""
    changes: list[str] = []
    os_, ns = old.get("settings", {}), new.get("settings", {})
    for k in sorted(set(os_) | set(ns)):
        if os_.get(k) != ns.get(k):
            changes.append(f"setting {k}: {os_.get(k)!r} -> {ns.get(k)!r}")
    of, nf = old.get("files", {}), new.get("files", {})
    for f in sorted(set(of) | set(nf), key=natural_key):
        if f not in nf:
            changes.append(f"removed {f}")
        elif f not in of:
            changes.append(f"added {f}")
        elif of[f] != nf[f]:
            changes.append(f"changed {f}")
    return changes


def write(cfg: Config, inputs: dict, bitstream: Path, summary: dict) -> dict:
    data = {
        "forge_version": __version__,
        "built": summary.get("finished"),
        "build_status": summary.get("status"),
        "vivado": summary.get("vivado"),
        "bitstream": {"path": bitstream.as_posix(), "sha256": sha256_file(bitstream)},
        "inputs_sha256": fingerprint(inputs),
        "inputs": inputs,
    }
    cfg.manifest_file.parent.mkdir(parents=True, exist_ok=True)
    cfg.manifest_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def load(cfg: Config) -> dict | None:
    try:
        data = json.loads(cfg.manifest_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) and "inputs" in data and "bitstream" in data else None


def _listed(changes: list[str]) -> list[str]:
    extra = len(changes) - MAX_LISTED
    return changes[:MAX_LISTED] + ([f"... and {extra} more"] if extra > 0 else [])


def freshness(cfg: Config, board: Board) -> dict | None:
    """Does the last bitstream still match the design? None when no build has produced one."""
    man = load(cfg)
    if man is None:
        return None
    changes = compare(man["inputs"], collect_inputs(cfg, board))
    bit = cfg.bitstream
    if not bit.is_file():
        changes.append(f"bitstream missing: {bit.as_posix()}")
    elif sha256_file(bit) != man["bitstream"].get("sha256"):
        changes.append("bitstream replaced after the build (regenerated outside forge?)")
    return {"up_to_date": not changes, "built": man.get("built"), "changes": _listed(changes)}


def verify_bitstream(cfg: Config, board: Board) -> dict:
    """The manifest of the bitstream about to be programmed; raises if it does not match the design."""
    rebuild = f"Run {forge_cmd('build')}, check the result, then program."
    man = load(cfg)
    if man is None:
        raise ForgeError("No bitstream from a forge build of the current project is on record.",
                         hint=rebuild, code="no_build")
    bit = cfg.bitstream
    if not bit.is_file():
        raise ForgeError(f"No bitstream at {bit.as_posix()}.", hint=rebuild, code="no_build")
    if sha256_file(bit) != man["bitstream"].get("sha256"):
        raise ForgeError("The bitstream on disk is not the one the last forge build produced "
                         "(was it regenerated in the Vivado GUI?).", hint=rebuild, code="stale_bitstream")
    changes = compare(man["inputs"], collect_inputs(cfg, board))
    if changes:
        raise ForgeError("The bitstream is out of date: the design changed after it was built:\n    "
                         + "\n    ".join(_listed(changes)),
                         hint=rebuild, code="stale_bitstream", details={"changes": changes})
    return man
