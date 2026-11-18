#!/usr/bin/env python3
"""VivadoForge command line: check, simulate, build and program Vivado FPGA projects.

    python scripts/forge.py info        # what is this project, which board, which tools
    python scripts/forge.py check       # catch pin/clock/config mistakes in seconds
    python scripts/forge.py sim         # run the self-checking testbenches
    python scripts/forge.py build       # synthesis + implementation + bitstream + summary
    python scripts/forge.py program     # load the FPGA (asks first)

Add --json to any command for machine-readable output. Python 3.11+, standard library only.
"""

import sys
from pathlib import Path

if sys.version_info < (3, 11):
    sys.exit(f"VivadoForge needs Python 3.11 or newer (this is {sys.version.split()[0]}).")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from forgelib.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
