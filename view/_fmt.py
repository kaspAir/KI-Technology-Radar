"""_fmt.py — kleine, geteilte Formatierhelfer für die Ansichten.

Liegt im view/-Ordner; da Python das Skriptverzeichnis auf sys.path legt, ist
`from _fmt import ch_date` aus jedem view/-Skript importierbar (auch als Subprozess).
"""
from __future__ import annotations

import re

_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


def ch_date(v) -> str:
    """ISO-Datum (yyyy-mm-dd…) → Schweizer Schreibweise dd.mm.yyyy.

    Nur der Datumsteil wird umgestellt; alles andere bleibt unverändert
    zurückgegeben (leere/None-Werte als leerer String, damit die Ansicht robust ist).
    """
    if not v:
        return ""
    s = str(v)
    m = _ISO.match(s)
    return f"{m.group(3)}.{m.group(2)}.{m.group(1)}" if m else s
