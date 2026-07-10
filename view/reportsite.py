#!/usr/bin/env python3
"""reportsite.py — deploybare Bericht-Seite mit Zeitraum-Wähler (R7+).

Weil der Bericht eine Projektion über einen Zeitraum ist (E21), lässt sich der
Zeitpunkt frei wählen — auch in der Vergangenheit. Diese Seite erzeugt je Monat
mit Aktivität einen berechneten Bericht (plus 'Gesamt bis heute') und schaltet
per Dropdown clientseitig zwischen ihnen um. Read-only, selbstenthaltend.

  python view/reportsite.py --instance ../KI-Technology-Radar-Instanz --out bericht.html
"""
from __future__ import annotations

import argparse
import datetime
import html
import json
import re
import subprocess
import sys
from pathlib import Path

from _fmt import ch_date

CORE = Path(__file__).resolve().parent.parent
GOLD, INK, PAPER = "#C0851F", "#23262D", "#F8F6F2"
MONTHS = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
          "August", "September", "Oktober", "November", "Dezember"]

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def event_dates(inst: Path) -> list[str]:
    dates = []
    elog = inst / "events" / "events.log"
    if elog.exists():
        for line in elog.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                try:
                    dates.append(json.loads(line)["at"][:10])
                except Exception:
                    pass
    return sorted(dates)


def run_report(inst: Path, frm: str, to: str) -> str:
    r = subprocess.run(
        [sys.executable, str(CORE / "view" / "report.py"),
         "--instance", str(inst), "--from", frm, "--to", to],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout


def md_to_html(md: str) -> str:
    def inline(s: str) -> str:
        s = html.escape(s)
        s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"\*(.+?)\*", r"<em>\1</em>", s)
        return s
    out, in_list = [], False
    for raw in md.splitlines():
        line = raw.rstrip()
        if not line.strip():
            if in_list:
                out.append("</ul>"); in_list = False
            continue
        if line.startswith("## "):
            if in_list:
                out.append("</ul>"); in_list = False
            out.append(f"<h4>{inline(line[3:])}</h4>")
        elif line.startswith("# "):
            if in_list:
                out.append("</ul>"); in_list = False
            out.append(f"<h3>{inline(line[2:])}</h3>")
        elif line.startswith("- "):
            if not in_list:
                out.append("<ul>"); in_list = True
            out.append(f"<li>{inline(line[2:])}</li>")
        else:
            if in_list:
                out.append("</ul>"); in_list = False
            out.append(f"<p>{inline(line)}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="Bericht-Seite mit Zeitraum-Wähler.")
    ap.add_argument("--instance", required=True)
    ap.add_argument("--out", default="bericht.html")
    args = ap.parse_args()
    inst = Path(args.instance)
    if not inst.is_absolute():
        inst = (Path.cwd() / inst).resolve()

    dates = event_dates(inst)
    today = datetime.date.today().isoformat()
    periods = []  # (label, frm, to)
    if dates:
        months = sorted({d[:7] for d in dates})
        for ym in reversed(months):
            y, m = ym.split("-")
            periods.append((f"{MONTHS[int(m) - 1]} {y}", f"{ym}-01", f"{ym}-31"))
        to_total = max(dates[-1], today)   # deckt auch (synthetisch) zukünftige Daten ab
        periods.append((f"Gesamt (seit {ch_date(dates[0])})", dates[0], to_total))

    sections, options = [], []
    for i, (label, frm, to) in enumerate(periods):
        body = md_to_html(run_report(inst, frm, to))
        disp = "block" if i == 0 else "none"
        sections.append(f'<section data-period="{i}" style="display:{disp}">{body}</section>')
        options.append(f'<option value="{i}">{html.escape(label)} '
                       f'({ch_date(frm)} → {ch_date(to)})</option>')
    if not sections:
        sections = ["<p>Noch keine Ereignisse erfasst.</p>"]

    doc = f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>KI-Technology-Radar — Berichte</title>
<style>
  body{{margin:0;background:{PAPER};color:{INK};font-family:system-ui,-apple-system,sans-serif;padding:28px}}
  .wrap{{max-width:760px;margin:0 auto}}
  .sig{{font-size:12px;letter-spacing:.3em;text-transform:uppercase;color:{GOLD};margin:0}}
  h1{{font-size:26px;font-weight:600;margin:2px 0 10px}}
  a.back{{font-size:13px;color:{GOLD};text-decoration:none}}
  .bar{{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:14px 0 22px;font-size:13px;color:#6b6862}}
  select{{font:inherit;color:{INK};background:#fff;border:1px solid #e7e3da;border-radius:8px;padding:5px 9px}}
  h3{{font-size:20px;font-weight:600;margin:6px 0 10px}}
  h4{{font-size:16px;font-weight:600;margin:20px 0 8px}}
  p{{font-size:14px;line-height:1.6;margin:6px 0}}
  ul{{margin:6px 0 6px 0;padding-left:20px}}
  li{{font-size:14px;line-height:1.6;margin:3px 0}}
  em{{color:#6b6862}}
  .note{{font-size:12px;color:#8a867e;margin:24px 0 0}}
</style></head><body><div class="wrap">
<p class="sig">Aletheia · Radar</p>
<h1>Berichte</h1>
<a class="back" href="index.html">← zum Radar</a>
<div class="bar"><label>Zeitraum&nbsp;
<select id="psel">{''.join(options)}</select></label>
<span>frei wählbar — auch in der Vergangenheit</span></div>
{''.join(sections)}
<p class="note">Interne Ansicht — enthält private Wertung (E25). Jeder Bericht ist
eine Projektion über das Ereignisprotokoll (E21), berechnet mit view/report.py.</p>
</div>
<script>
  var sel=document.getElementById('psel');
  if(sel){{sel.addEventListener('change',function(e){{
    var k=e.target.value;
    document.querySelectorAll('[data-period]').forEach(function(s){{
      s.style.display=(s.getAttribute('data-period')===k)?'block':'none';}});
  }});}}
</script>
</body></html>"""

    out = Path(args.out)
    if not out.is_absolute():
        out = (Path.cwd() / out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    print(f"Geschrieben: {out}  ({len(periods)} Zeiträume)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
