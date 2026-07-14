#!/usr/bin/env python3
"""profilsite.py — Selbstbedienungs-Formular für das Mandanten-Profil (pro Mandant).

Erzeugt profil.html: ein Formular, in dem ein Mandant seine strategischen
Eigenschaften selbst erfasst (Schwerpunkte, Wunschbranchen, Risikofreudigkeit,
KPIs, …). Vorbelegt aus <instance>/mandant.yaml (falls vorhanden). Der Knopf
erzeugt/lädt die aktualisierte mandant.yaml (E24 Konfiguration, tenant-privat) —
gleiche Selbstbedienungs-Mechanik wie der Eingangskorb-Download. Im MVP speichert
dasselbe Formular direkt je tenant_id. lagebild.py liest das Profil und schärft
damit die Strategie. Nur internal (E25/E26).

  python view/profilsite.py --instance ../KI-Technology-Radar-Instanz --out profil.html
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

import yaml

GOLD, INK, PAPER = "#C0851F", "#23262D", "#F8F6F2"

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# Feld-Spezifikation: (key, label, typ, optionen/hinweis)
#   typ: text | textarea | list (Komma-getrennt -> YAML-Liste) | select
SPEC = [
    ("§", "Identität & Mandat", None, None),
    ("name", "Name der Organisation", "text", ""),
    ("typ", "Organisationstyp", "select", ["Behörde", "Kompetenzzentrum", "Verband-Mitglied", "KMU", "Grossunternehmen", "Andere"]),
    ("mandat", "Mandat / Auftrag (1–2 Sätze)", "textarea", ""),
    ("groesse_reife", "Grösse & technische Reife", "text", "z.B. 12 Personen, mittlere KI-Reife"),
    ("§", "Strategische Ausrichtung", None, None),
    ("schwerpunkte", "Schwerpunkte / Fokusthemen", "list", "Komma-getrennt"),
    ("aktuelle_branchen", "Aktuelle Branchen", "list", "Komma-getrennt"),
    ("wunschbranchen", "Wunsch-/Zielbranchen", "list", "Komma-getrennt"),
    ("nicht_ziele", "Bewusste Nicht-Ziele / Scope-Grenzen", "list", "Komma-getrennt"),
    ("zeithorizont", "Zeithorizont", "select", ["operativ (≈1 Jahr)", "mittelfristig (2–3 Jahre)", "strategisch (5+ Jahre)"]),
    ("§", "Wertungs-Parameter (steuern die Empfehlungen)", None, None),
    ("risikofreudigkeit", "Risikofreudigkeit", "select", ["konservativ", "ausgewogen", "früh-adoptierend"]),
    ("souveraenitaet", "Souveränität / Datenresidenz-Priorität", "select", ["hoch", "mittel", "tief"]),
    ("compliance_strenge", "Compliance-/Governance-Strenge", "select", ["hoch", "mittel", "tief"]),
    ("make_vs_buy", "Make-vs-Buy-Neigung", "select", ["selbst aufbauen", "ausgewogen", "einkaufen"]),
    ("budget_rahmen", "Budget-/Investitionsrahmen (grob)", "text", ""),
    ("§", "Ziele & Messung", None, None),
    ("kpis", "KPIs / Erfolgskriterien", "list", "Komma-getrennt"),
    ("ziele", "Strategische Ziele (1–3)", "list", "Komma-getrennt"),
    ("§", "Kompetenz-Kontext", None, None),
    ("staerken", "Vorhandene Stärken", "list", "Komma-getrennt"),
    ("kompetenz_luecken", "Kompetenz-Lücken / Aufbau-Ziele", "list", "Komma-getrennt"),
]


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def main() -> int:
    ap = argparse.ArgumentParser(description="Selbstbedienungs-Formular Mandanten-Profil.")
    ap.add_argument("--instance", required=True)
    ap.add_argument("--mode", choices=["internal", "public"], default="internal")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    if args.mode == "public":
        print("Profil ist tenant-privat (E25/E26) — nur internal."); return 0
    inst = Path(args.instance)
    if not inst.is_absolute():
        inst = (Path.cwd() / inst).resolve()

    cur = {}
    mf = inst / "mandant.yaml"
    if mf.exists():
        with mf.open(encoding="utf-8") as fh:
            cur = yaml.safe_load(fh) or {}

    def val(k):
        v = cur.get(k)
        if isinstance(v, list):
            return ", ".join(str(x) for x in v)
        return "" if v is None else str(v)

    # Formular-Felder + JS-Feldliste (welche sind Listen).
    fields_html, jsfields = [], []
    for key, label, typ, opt in SPEC:
        if key == "§":
            fields_html.append(f'<h2>{esc(label)}</h2>')
            continue
        jsfields.append({"k": key, "list": typ == "list"})
        v = esc(val(key))
        hint = f'<span class="hint">{esc(opt)}</span>' if isinstance(opt, str) and opt else ''
        if typ == "text" or typ == "list":
            ph = esc(opt) if isinstance(opt, str) else ""
            fields_html.append(
                f'<label class="f"><span>{esc(label)}</span>{hint}'
                f'<input id="f_{key}" value="{v}" placeholder="{ph}"></label>')
        elif typ == "textarea":
            fields_html.append(
                f'<label class="f"><span>{esc(label)}</span>'
                f'<textarea id="f_{key}" rows="2">{v}</textarea></label>')
        elif typ == "select":
            opts = ['<option value=""></option>'] + [
                f'<option{" selected" if val(key) == o else ""}>{esc(o)}</option>' for o in (opt or [])]
            fields_html.append(
                f'<label class="f"><span>{esc(label)}</span>'
                f'<select id="f_{key}">{"".join(opts)}</select></label>')

    jsfields_json = json.dumps(jsfields, ensure_ascii=False)
    doc = f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mandanten-Profil — KI-Radar</title>
<style>
  body{{margin:0;background:{PAPER};color:{INK};font-family:system-ui,-apple-system,sans-serif;padding:28px}}
  .wrap{{max-width:720px;margin:0 auto}}
  a.back{{font-size:13px;color:{GOLD};text-decoration:none}}
  .sig{{font-size:12px;letter-spacing:.3em;text-transform:uppercase;color:{GOLD};margin:8px 0 0}}
  h1{{font-size:26px;font-weight:600;margin:4px 0 2px}}
  .sub{{color:#6b6862;font-size:14px;margin:0 0 14px;line-height:1.5}}
  h2{{font-size:16px;font-weight:600;margin:22px 0 8px;color:{GOLD}}}
  .f{{display:flex;flex-direction:column;gap:3px;margin:0 0 11px}}
  .f>span{{font-size:13.5px;font-weight:500}}
  .hint{{font-size:12px;color:#8a867e}}
  input,textarea,select{{font:inherit;font-size:14px;color:{INK};background:#fff;border:1px solid #e7e3da;border-radius:9px;padding:8px 10px}}
  input:focus,textarea:focus,select:focus{{outline:none;border-color:{GOLD}}}
  .bar{{position:sticky;bottom:0;background:{PAPER};padding:12px 0;display:flex;gap:10px;flex-wrap:wrap;align-items:center;border-top:1px solid #e7e3da;margin-top:12px}}
  .btn{{font:inherit;font-size:14px;font-weight:600;border:1px solid {GOLD};background:{GOLD};color:#fff;border-radius:9px;padding:9px 16px;cursor:pointer}}
  .btn.sec{{background:#fff;color:{GOLD}}}
  .prev{{white-space:pre-wrap;background:#fff;border:1px solid #e7e3da;border-radius:10px;padding:12px 14px;font:12px/1.5 ui-monospace,monospace;color:#3a3833;max-height:260px;overflow:auto;margin-top:10px}}
  .note{{font-size:12px;color:#8a867e;margin:14px 0 0;line-height:1.5}}
</style></head><body><div class="wrap">
<a class="back" href="index.html">← zum Radar</a>
<p class="sig">Aletheia · Radar · Mandanten-Profil</p>
<h1>Mandanten-Profil</h1>
<p class="sub">Erfasse die strategischen Eigenschaften deiner Organisation — das
schärft dein Lagebild und die Empfehlungen (pro Mandant, privat, E25). Ausfüllen →
<b>mandant.yaml herunterladen</b> → committen → Radar neu bauen.</p>
{''.join(fields_html)}
<div class="bar">
  <button class="btn" onclick="dl()">⤓ mandant.yaml herunterladen</button>
  <button class="btn sec" onclick="cp()">Kopieren</button>
  <button class="btn sec" onclick="pv()">Vorschau</button>
</div>
<pre id="prev" class="prev" style="display:none"></pre>
<p class="note">Selbstbedienung: das Formular läuft im Browser, es wird nichts
serverseitig gespeichert. Im MVP speichert dasselbe Formular direkt je Mandant.
Nur interne, private Konfiguration (E25/E26).</p>
<script>
var FIELDS={jsfields_json};
function q(s){{return String(s==null?'':s).replace(/"/g,'\\\\"');}}
function buildYaml(){{
  var out=['# mandant.yaml — Mandanten-Profil (E24 Konfiguration, tenant-privat).',
           '# Selbst erfasst über profil.html. Steuert lagebild.py / Empfehlungen.'];
  FIELDS.forEach(function(f){{
    var el=document.getElementById('f_'+f.k); var v=el?el.value.trim():'';
    if(f.list){{
      var items=v.split(',').map(function(x){{return x.trim();}}).filter(Boolean);
      if(!items.length){{out.push(f.k+': []');}}
      else{{out.push(f.k+':'); items.forEach(function(it){{out.push('  - "'+q(it)+'"');}});}}
    }} else {{
      out.push(f.k+': "'+q(v)+'"');
    }}
  }});
  return out.join('\\n')+'\\n';
}}
function pv(){{var p=document.getElementById('prev');p.style.display='block';p.textContent=buildYaml();}}
function dl(){{
  var blob=new Blob([buildYaml()],{{type:'text/yaml'}});
  var a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='mandant.yaml';
  document.body.appendChild(a);a.click();a.remove();
}}
function cp(){{navigator.clipboard&&navigator.clipboard.writeText(buildYaml());pv();}}
</script>
</div></body></html>"""

    out = Path(args.out)
    if not out.is_absolute():
        out = (Path.cwd() / out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    print(f"Profil-Formular: {out}" + (" (vorbelegt aus mandant.yaml)" if cur else " (leer)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
