"""chat.py — Radar-Berater: geerdetes Strategiegespräch pro Mandant.

Der Berater bezieht sich AUSSCHLIESSLICH auf zwei Quellen des eingeloggten
Mandanten: sein **Profil** (inkl. geerbter Vorgaben) und die **von ihm gewählten
Radar-Inhalte** (effektive Kuratierung). Kein Allgemeinwissen als Tatsache, keine
fremden Mandantendaten (E23/E25), nichts erfunden (E8).

Er **schlägt vor** und **denkt mit** — er **entscheidet nie** (E4: KI entwirft,
Mensch ratifiziert).

Datenresidenz: `_outbound`/`_inbound` sind die vorgesehene Naht für eine
vorgeschaltete Pseudonymisierungsschicht (nur pseudonymisierte Daten nach
aussen, Rück-Ersetzung bei der Antwort). Aktuell Durchreiche.
"""
from __future__ import annotations

import os

MODEL = os.environ.get("RADAR_CHAT_MODEL", "claude-opus-4-8")
MAX_TOKENS = int(os.environ.get("RADAR_CHAT_MAX_TOKENS", "8000"))
# „medium" hält den Chat antwortfreudig; für tiefere Analysen auf „high" stellen.
EFFORT = os.environ.get("RADAR_CHAT_EFFORT", "medium")
MAX_TURNS = int(os.environ.get("RADAR_CHAT_MAX_TURNS", "40"))   # Verlauf, den wir mitsenden
# Obergrenze für den mitgesendeten Verlauf. Wird sie überschritten, fallen die
# ÄLTESTEN Nachrichten weg (die jüngsten bleiben immer) — sonst wächst jede
# Antwort langsamer und teurer als die vorige.
HISTORY_BUDGET = int(os.environ.get("RADAR_CHAT_BUDGET_CHARS", "120000"))
KEEP_LAST = int(os.environ.get("RADAR_CHAT_KEEP_LAST", "6"))    # nie wegkürzen

RING_MEAN = {"Adopt": "produktiv nutzen", "Pilot": "real erproben",
             "Explore": "aktiv erkunden", "Watch": "beobachten",
             "Reject": "bewusst verworfen"}

RULES = """\
Du bist der Berater des KI-Technology-Radars — ein Gesprächspartner für die
strategische Entwicklung der unten genannten Organisation.

DEINE QUELLEN — ausschliesslich diese:
1. Das Mandanten-Profil (unten).
2. Die vom Mandanten gewählten Radar-Inhalte (unten).
3. Dokumente, die der Mandant in DIESEM Gespräch hochgeladen hat (im Verlauf als
   „DOKUMENT: <Dateiname>" gekennzeichnet).
Ausserhalb dieser drei hast du KEINE Faktenbasis.

HARTE REGELN:
- Erfinde nichts. Keine Zahlen, Namen, Studien, Fristen oder Quellen, die unten
  oder in einem hochgeladenen Dokument nicht stehen. Lieber sagen „dazu steht
  nichts im Radar und in keinem Dokument" als raten.
- Wenn eine Frage über alle drei Quellen hinausgeht: sage das ausdrücklich und
  benenne, was fehlen würde, um sie zu beantworten.
- Belege jede inhaltliche Aussage und **nenne dabei immer die Quelle**: entweder
  den Radar-Eintrag (mit Ring), das Profil-Feld — oder den Dateinamen des
  Dokuments. Der Leser muss jederzeit erkennen, woher eine Aussage stammt.
- Halte Radar und Dokumente auseinander: Radar-Einträge sind vom Mandanten
  kuratiert (teils ratifiziert), hochgeladene Dokumente sind ungeprüfter Input.
  Behandle sie nie als gleichwertig belegt und stelle Widersprüche zwischen
  beiden ausdrücklich fest, statt sie stillschweigend aufzulösen.
- Du machst VORSCHLÄGE und bringst IDEEN ein. Du ENTSCHEIDEST NIE. Formuliere als
  Optionen, Abwägungen und Rückfragen — nicht als Anweisung. Die Entscheidung
  trifft immer der Mensch.
- Keine Anlage-, Finanz- oder Rechtsberatung. Marktthemen darfst du strategisch
  einordnen (Abhängigkeit, Belastbarkeit), aber niemals als Empfehlung zu
  Investitionen oder Timing.
- Sprich Deutsch (Schweizer Kontext, „ss" statt „ß").

HALTUNG:
Fordere die Organisation fachlich heraus, statt nur zuzustimmen: benenne Lücken,
Spannungen zwischen Profil und Kuratierung und blinde Flecken — immer belegt aus
den Quellen unten. Sei knapp und konkret; stelle am Ende höchstens eine
weiterführende Rückfrage.

RINGE: Adopt = produktiv nutzen · Pilot = real erproben · Explore = aktiv
erkunden · Watch = beobachten · Reject = bewusst verworfen.
"""


def _outbound(text: str) -> str:
    """Naht für die Pseudonymisierung (vor dem Versand nach aussen)."""
    return text


def _inbound(text: str) -> str:
    """Naht für die Rück-Ersetzung (nach Erhalt der Antwort)."""
    return text


def build_context(tenant_name: str, profile: dict, blips: list, field_labels: dict) -> str:
    """Erzeugt den Erdungs-Kontext aus Profil + gewählten Inhalten."""
    out = [f"# Mandant\n{tenant_name}", "\n# Mandanten-Profil"]
    if profile:
        for key, val in profile.items():
            if val in (None, "", [], {}):
                continue
            v = ", ".join(str(x) for x in val) if isinstance(val, list) else str(val)
            out.append(f"- {field_labels.get(key, key)}: {v}")
    else:
        out.append("- (noch nicht ausgefüllt — das ist selbst ein Befund)")

    out.append("\n# Gewählte Radar-Inhalte (die Sicht dieses Mandanten)")
    if not blips:
        out.append("- (noch nichts kuratiert)")
    else:
        by_ring: dict = {}
        for b in blips:
            by_ring.setdefault(b["ring"], []).append(b)
        for ring in ("Adopt", "Pilot", "Explore", "Watch", "Reject"):
            group = by_ring.get(ring) or []
            if not group:
                continue
            out.append(f"\n## Ring {ring} ({RING_MEAN.get(ring, '')}) — {len(group)}")
            for b in group:
                p = b["prop"]
                herkunft = "geerbter Grundstock" if b["origin"] != "own" else "selbst aufgenommen"
                line = f"- **{p.title}** ({herkunft}"
                if p.branchen:
                    line += f"; Branchen: {p.branchen}"
                if p.providers:
                    line += f"; Anbieter-Abhängigkeit: {p.providers}"
                line += ")"
                if p.summary:
                    line += f"\n  {p.summary[:400]}"
                out.append(line)
    return "\n".join(out)


def fit_history(history: list):
    """Kürzt den Verlauf auf das Budget: die jüngsten KEEP_LAST Nachrichten bleiben
    immer, davor fallen die ältesten weg. Rückgabe: (behalten, weggelassen).
    Bewusst deterministisch und sichtbar — nichts wird stillschweigend verdichtet."""
    hist = history[-MAX_TURNS:]
    dropped = len(history) - len(hist)
    while len(hist) > KEEP_LAST and sum(len(m["content"]) for m in hist) > HISTORY_BUDGET:
        hist = hist[1:]
        dropped += 1
    return hist, dropped


def ask(context: str, history: list) -> str:
    """Stellt die Frage an das Modell. history = [{'role':..., 'content':...}, ...].
    Rückgabe: Antworttext (oder eine ehrliche Fehlermeldung)."""
    try:
        import anthropic
    except ImportError:
        return ("Der Berater ist nicht verfügbar: das Paket anthropic fehlt in der "
                "Umgebung (app/requirements.txt installieren).")
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        return "Der Berater ist nicht verfügbar: kein ANTHROPIC_API_KEY in der Umgebung."

    system = [{"type": "text", "text": _outbound(RULES + "\n\n" + context),
               "cache_control": {"type": "ephemeral"}}]
    kept, dropped = fit_history(history)
    if dropped:
        kept = [{"role": "user", "content":
                 f"(Hinweis: die {dropped} ältesten Beiträge dieses Gesprächs sind aus "
                 "Platzgründen nicht mehr enthalten. Der Radar-Kontext oben ist vollständig. "
                 "Frage nach, falls dir etwas Vorheriges fehlt.)"}] + kept
    msgs = [{"role": m["role"], "content": _outbound(m["content"])} for m in kept]
    try:
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            thinking={"type": "adaptive"},
            output_config={"effort": EFFORT},
            # Verlauf zwischenspeichern: Folgeantworten lesen ihn, statt ihn neu
            # zu verarbeiten — deutlich schneller und günstiger.
            cache_control={"type": "ephemeral"},
            system=system,
            messages=msgs,
        )
        if resp.stop_reason == "refusal":
            return "Diese Anfrage wurde aus Sicherheitsgründen abgelehnt. Bitte formuliere sie anders."
        text = next((b.text for b in resp.content if b.type == "text"), "")
        return _inbound(text) or "(keine Antwort erhalten)"
    except anthropic.RateLimitError:
        return "Zu viele Anfragen — bitte kurz warten und erneut senden."
    except anthropic.AuthenticationError:
        return "Der API-Schlüssel wurde abgelehnt. Bitte ANTHROPIC_API_KEY prüfen."
    except anthropic.APIStatusError as e:
        return f"Der Berater ist gerade nicht erreichbar (Status {e.status_code})."
    except anthropic.APIConnectionError:
        return "Keine Verbindung zum Modell-Dienst. Bitte später erneut versuchen."
