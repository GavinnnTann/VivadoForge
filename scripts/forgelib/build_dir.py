"""The build directory is disposable, so forge only ever writes to or deletes a folder it created."""

from __future__ import annotations

import os
import shutil
import stat
import sys
import time
from pathlib import Path

from .common import BUILD_MARKER, ForgeError, is_synced_folder


def remove_tree(path: Path, attempts: int = 6) -> None:
    """shutil.rmtree that survives Windows: clears read-only flags and retries briefly while
    OneDrive, an antivirus scanner or a closing viewer still holds a file."""
    def make_writable(func, p, *_):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except OSError:
            pass   # retried below
    last: Exception | None = None
    for i in range(attempts):
        if not Path(path).exists():
            return
        try:
            if sys.version_info >= (3, 12):
                shutil.rmtree(path, onexc=make_writable)
            else:
                shutil.rmtree(path, onerror=make_writable)
            if not Path(path).exists():
                return
        except OSError as exc:
            last = exc
        time.sleep(0.5 * (i + 1))
    hint = "Close Vivado, waveform viewers and terminals using files there, then retry."
    sync = is_synced_folder(Path(path))
    if sync:
        hint += f" The folder is inside {sync}, which locks files while syncing: set build_dir outside it."
    raise ForgeError(f"Could not delete {path}: a file is in use ({last}).", hint=hint)

MARKER_TEXT = ("Created by VivadoForge. Everything in this folder is generated;\n"
               "`python scripts/forge.py clean` deletes the whole folder.\n")


def ensure_build_dir(path: Path) -> Path:
    """Create the build folder (with a marker file) or check that an existing one is ours."""
    path = Path(path)
    marker = path / BUILD_MARKER
    if path.exists():
        if not path.is_dir():
            raise ForgeError(f"Build path {path} exists and is not a folder.")
        if marker.is_file():
            return path
        if any(p.is_file() for p in path.rglob("*")):   # only empty sub-folders is fine to adopt
            raise ForgeError(
                f"Build folder {path} already contains files that VivadoForge did not create.",
                hint="Pick an empty or new folder for [build].dir / build_dir (forge.local.toml), "
                     "e.g. C:/fpga_build/{name}. Forge refuses to mix its output with other files "
                     "because `clean` deletes the whole build folder.")
    path.mkdir(parents=True, exist_ok=True)
    marker.write_text(MARKER_TEXT, encoding="utf-8")
    return path


def clean_build_dir(path: Path) -> bool:
    """Delete the build folder if (and only if) forge created it. Returns True if something was deleted."""
    path = Path(path)
    if not path.exists():
        return False
    marker = path / BUILD_MARKER
    if not marker.is_file():
        if not any(p.is_file() for p in path.rglob("*")):   # leftover empty folders only
            remove_tree(path)
            return True
        raise ForgeError(f"Refusing to delete {path}: it has no {BUILD_MARKER} marker, so forge did not create it.")
    # Delete the contents first and the marker last, so an interrupted clean can be retried.
    for child in path.iterdir():
        if child.name == BUILD_MARKER:
            continue
        if child.is_dir() and not child.is_symlink():
            remove_tree(child)
        else:
            child.unlink()
    marker.unlink()
    remove_tree(path)
    return True
