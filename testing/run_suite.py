#!/usr/bin/env python3
"""run_suite.py — schnelle deterministische Testsuite + Testprotokoll.

Umsetzung von Testkonzept Kap. 9/12 (Schritt 2 des Rollouts, Kap. 16): Bei jedem
Build läuft die schnelle, deterministische Suite; jeder Lauf erzeugt EIN
reproduzierbares, versioniertes Testprotokoll (§12) auf dem Governance-Mixin.

Über Pass/Fail entscheidet dieser Runner deterministisch (ADR-T01) — nie ein
Agent. Die schweren Suiten (Systemintegration, Performance, dynamische
Sicherheit) laufen NICHT hier, sondern erst auf int (ADR-T02/T06); sie erscheinen
im Protokoll als 'nicht_ausgefuehrt', damit keine Scheinsicherheit entsteht.

Aufruf:
    python testing/run_suite.py --env dev --instance examples/sample-instance
"""
from __future__ import annotations

import argparse
import datetime
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker

# Konsolenausgabe plattformunabhängig auf UTF-8 (Windows-Konsole ist cp1252).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

CORE = Path(__file__).resolve().parent.parent
SUITE_NAME = "radar-fast-suite"
SUITE_VERSION = "0.1.0"


def now_iso() -> str:
    return datetime.datetime.now().astimezone().replace(microsecond=0).isoformat()


def git_commit() -> str | None:
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                           cwd=CORE, capture_output=True, text=True)
        return r.stdout.strip() or None
    except Exception:
        return None


def run_pytest() -> dict:
    """Fährt pytest, liest Zähler aus dem JUnit-XML."""
    xml = CORE / "testing" / ".pytest-report.xml"
    r = subprocess.run(
        [sys.executable, "-m", "pytest", str(CORE / "testing" / "tests"),
         "-q", f"--junitxml={xml}"],
        cwd=CORE, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    anzahl = fehler = 0
    dauer = 0.0
    if xml.exists():
        root = ET.parse(xml).getroot()
        suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
        for s in suites:
            anzahl += int(s.get("tests", 0))
            fehler += int(s.get("failures", 0)) + int(s.get("errors", 0))
            dauer += float(s.get("time", 0.0))
        xml.unlink(missing_ok=True)
    else:
        fehler = 1  # pytest konnte nicht laufen
    return {
        "art": "unit", "stufe": "unit", "schnittstellen": "mock",
        "ergebnis": "bestanden" if r.returncode == 0 and fehler == 0 else "fehlgeschlagen",
        "anzahl": anzahl, "fehler": fehler, "dauer_s": round(dauer, 3),
        "details": "pytest: Unit-/Kontrakttests des Kern-Mechanismus",
    }


def run_validate(instance: Path) -> dict:
    """Schema- und Integritätsvalidierung der Instanz (validate.py)."""
    t0 = datetime.datetime.now()
    r = subprocess.run(
        [sys.executable, str(CORE / "src" / "validate.py"), "--instance", str(instance)],
        cwd=CORE, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    dauer = (datetime.datetime.now() - t0).total_seconds()
    return {
        "art": "kontrakt", "stufe": "kontrakt", "schnittstellen": "mock",
        "ergebnis": "bestanden" if r.returncode == 0 else "fehlgeschlagen",
        "anzahl": None, "fehler": 0 if r.returncode == 0 else 1,
        "dauer_s": round(dauer, 3),
        "details": "validate.py: Schema- und Integritätsvalidierung der Instanz",
    }


def run_sast() -> dict:
    """Statische Sicherheit (SAST/Dependency-Scan) — bereits auf dev (Kap. 4)."""
    if shutil.which("pip-audit"):
        r = subprocess.run(["pip-audit", "-r", str(CORE / "requirements.txt")],
                           cwd=CORE, capture_output=True, text=True)
        return {
            "art": "sicherheit-statisch", "schnittstellen": "na",
            "ergebnis": "bestanden" if r.returncode == 0 else "fehlgeschlagen",
            "anzahl": None, "fehler": None, "dauer_s": None,
            "details": "pip-audit (Dependency-Scan)",
        }
    return {
        "art": "sicherheit-statisch", "schnittstellen": "na",
        "ergebnis": "nicht_ausgefuehrt", "anzahl": None, "fehler": None, "dauer_s": None,
        "details": "pip-audit nicht installiert — Scan übersprungen (TODO CI)",
    }


# Schwere Suiten laufen erst auf int (ADR-T02/T06). Auf dev/test ehrlich als
# 'nicht_ausgefuehrt' ausweisen statt zu verschweigen.
HEAVY_ARTEN = ["systemintegration", "performance", "sicherheit-dynamisch"]


def main() -> int:
    ap = argparse.ArgumentParser(description="Schnelle deterministische Testsuite + Protokoll.")
    ap.add_argument("--env", default="dev", choices=["dev", "test", "int", "prod"])
    ap.add_argument("--interfaces", default="mock", choices=["mock", "real"])
    ap.add_argument("--instance", default=str(CORE / "examples" / "sample-instance"))
    ap.add_argument("--out", default=str(CORE / "testing" / "protocols"))
    args = ap.parse_args()

    if args.interfaces == "real" and args.env != "int":
        sys.exit("interfaces=real ist nur auf int zulässig (ADR-T02).")

    testarten = [run_pytest(), run_validate(Path(args.instance)), run_sast()]
    for art in HEAVY_ARTEN:
        testarten.append({
            "art": art, "schnittstellen": "real", "ergebnis": "nicht_ausgefuehrt",
            "anzahl": None, "fehler": None, "dauer_s": None,
            "details": f"läuft erst auf int (ADR-T02/T06) — hier ({args.env}) nicht ausgeführt",
        })

    ausgefuehrt = [t for t in testarten if t["ergebnis"] != "nicht_ausgefuehrt"]
    status = "bestanden" if all(t["ergebnis"] == "bestanden" for t in ausgefuehrt) else "fehlgeschlagen"

    ts = now_iso()
    protokoll = {
        "id": f"protokoll-{args.env}-{ts}",
        "created_at": ts, "updated_at": ts,
        "version": SUITE_VERSION, "created_by": "runner:validate-suite",
        "status": status,
        "suite": {"name": SUITE_NAME, "version": SUITE_VERSION},
        "commit": git_commit(),
        "environment": args.env, "interfaces": args.interfaces,
        "testarten": testarten,
        "triage": None, "signatur": None,
    }

    # Protokoll gegen sein Schema validieren (das Protokoll selbst muss valide sein).
    schema = yaml.safe_load((CORE / "testing" / "schema" / "protocol.schema.yaml").read_text(encoding="utf-8"))
    errs = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(protokoll))
    if errs:
        for e in errs:
            print(f"PROTOKOLL-SCHEMAFEHLER: {'/'.join(str(p) for p in e.path)}: {e.message}")
        return 2

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    safe_ts = ts.replace(":", "").replace("+", "p")
    outfile = outdir / f"protokoll-{args.env}-{safe_ts}.yaml"
    outfile.write_text(yaml.safe_dump(protokoll, allow_unicode=True, sort_keys=False), encoding="utf-8")

    print(f"Umgebung: {args.env} · Schnittstellen: {args.interfaces} · Commit: {protokoll['commit']}")
    for t in testarten:
        n = "" if t["anzahl"] is None else f" ({t['anzahl']} Tests, {t['fehler']} Fehler)"
        print(f"  {t['ergebnis']:16} {t['art']}{n} — {t['details']}")
    print(f"\nGesamt: {status.upper()}  →  Protokoll: {outfile.relative_to(CORE)}")
    return 0 if status == "bestanden" else 1


if __name__ == "__main__":
    raise SystemExit(main())
