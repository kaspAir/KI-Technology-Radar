"""Deterministische Unit-/Kontrakttests für den Kern-Mechanismus.

Materialisiert den Testfall-Katalog testing/cases/kern-mechanismus.yaml. Über
Pass/Fail entscheidet pytest (der Runner), nie ein Agent (ADR-T01). Läuft in
dev/test gegen Fixtures/Mocks (die synthetische Beispiel-Instanz).
"""
from __future__ import annotations

import datetime
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

CORE = Path(__file__).resolve().parents[2]
SAMPLE = CORE / "examples" / "sample-instance"


def _load_validate():
    spec = importlib.util.spec_from_file_location("validate", CORE / "src" / "validate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


validate = _load_validate()


def run_validate(instance: Path) -> tuple[int, str]:
    r = subprocess.run(
        [sys.executable, str(CORE / "src" / "validate.py"), "--instance", str(instance)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return r.returncode, r.stdout + r.stderr


# kern-datum-0004 -----------------------------------------------------------
def test_normalize_dates_to_iso():
    out = validate._normalize(
        {"since": datetime.date(2026, 7, 10), "at": datetime.datetime(2026, 7, 10, 12, 0)}
    )
    assert out["since"] == "2026-07-10"
    assert out["at"].startswith("2026-07-10T")


# kern-schema-0001 ----------------------------------------------------------
def test_term_schema_rejects_bad_id():
    v = validate.load_schema("term")
    bad = {"id": "Domain.Falsch", "taxonomy": "domain", "label": "x",
           "status": "active", "since": "2026-07-10"}
    assert list(v.iter_errors(bad)), "ungültige ID hätte scheitern müssen"
    good = {"id": "domain.gut", "taxonomy": "domain", "label": "Gut",
            "status": "active", "since": "2026-07-10"}
    assert not list(v.iter_errors(good))


# Positiv-Baseline: die Beispiel-Instanz ist valide --------------------------
def test_sample_instance_is_valid():
    rc, out = run_validate(SAMPLE)
    assert rc == 0, out


# kern-integritaet-0002 -----------------------------------------------------
def test_unknown_term_reference_fails(tmp_path):
    inst = tmp_path / "inst"
    shutil.copytree(SAMPLE, inst)
    entry = inst / "entries" / "beispiel" / "entry.yaml"
    entry.write_text(
        entry.read_text(encoding="utf-8").replace("tech_tag.llm", "tech_tag.nonexistent"),
        encoding="utf-8",
    )
    rc, out = run_validate(inst)
    assert rc == 1
    assert "unbekannter Term" in out


# kern-ring-0003 ------------------------------------------------------------
def test_inconsistent_current_ring_warns(tmp_path):
    inst = tmp_path / "inst"
    shutil.copytree(SAMPLE, inst)
    entry = inst / "entries" / "beispiel" / "entry.yaml"
    entry.write_text(
        entry.read_text(encoding="utf-8").replace("current_ring: Explore", "current_ring: Adopt"),
        encoding="utf-8",
    )
    rc, out = run_validate(inst)
    assert rc == 0                      # Warnung, kein Fehler
    assert "weicht vom" in out


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
