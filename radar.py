#!/usr/bin/env python3
"""radar — Ziel-Tooling-CLI (R7). Bündelt die read-only Werkzeuge des Kerns.

  python radar.py validate --instance <pfad>
  python radar.py render   --instance <pfad> [--mode internal|public] [--out ...]
  python radar.py report   --instance <pfad> [--from YYYY-MM-DD] [--to YYYY-MM-DD] [--out ...]

Bewusst schlank: ein Einstiegspunkt, aber KEIN zentraler Runner, durch den alles
zwingend laufen muss — die einzelnen Werkzeuge bleiben eigenständig aufrufbar.
"""
import subprocess
import sys
from pathlib import Path

CORE = Path(__file__).resolve().parent
CMDS = {
    "validate": CORE / "src" / "validate.py",
    "render": CORE / "view" / "render.py",
    "report": CORE / "view" / "report.py",
}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in CMDS:
        print(__doc__)
        return 2
    return subprocess.run([sys.executable, str(CMDS[sys.argv[1]]), *sys.argv[2:]]).returncode


if __name__ == "__main__":
    raise SystemExit(main())
