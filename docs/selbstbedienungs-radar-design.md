# Selbstbedienungs-Radar für viele Mitglieder — Design (MVP)

> Ziel (Nutzer): den Radar **gratis** vielen Mitgliedern (z. B. Swiss AI Association)
> zur Verfügung stellen. **Jedes Mitglied ein eigener Mandant**, der **selbst
> kuratiert** — aus den Vorschlägen des geteilten Radars. Passt zur Phronesis-Strategie
> (Beitrag/Wirkung statt Umsatz).

## 1. Der ehrliche Sprung

Die heutige Architektur (statisches HTML + git + `ratify.py` auf der Kommandozeile)
trägt **einen technischen Kurator**. Sie skaliert **nicht** auf viele nicht-technische
Selbst-Kuratoren — man kann Vereinsmitgliedern kein git-Repo + Python-CLI in die Hand
geben. Für „viele Mitglieder, jeder kuratiert selbst" brauchen wir die **App-Schicht**:
Web-App + Datenbank + Login + Kuratierung im Browser. Das ist P2+P3+P4 zusammen —
die interaktive App. Ein echtes Software-Produkt, kein Skript mehr.

## 2. Was BLEIBT (nichts war umsonst)

- **Kern-Mechanismus:** Ringe, Muster, Kompetenz-/Erosionsmodell, E4/E25-Prinzipien.
- **Geteilte Sammel-Schicht:** Ingestion-Pipeline + Pool (P1) = genau die „Vorschläge",
  aus denen jeder Mandant kuratiert. **Einmal sammeln, für alle.**
- **Render-/Dossier-Logik:** wird von „statisch je Instanz" zu „dynamisch je Nutzer".
- **Bewertungsraster, Schema, Validierung.**

## 3. Ziel-Architektur (zwei Schichten, jetzt als App)

```
  Ingestion ─▶ POOL (geteilt: Belege/Vorschläge)         [DB: proposals]
                     │
        ┌────────────┼────────────┐   Login pro Mitglied
        ▼            ▼            ▼
   Kuratierung   Kuratierung   Kuratierung                [DB: tenant_id + Auswahl/Ring]
   = Radar 1     = Radar 2     = Radar N                  (privat, E25)
```

- **Geteilt:** der Pool (Vorschläge). Kostet einmal (API), nicht pro Nutzer.
- **Pro Mandant:** Auswahl + Wertung (welcher Vorschlag auf MEIN Radar, welcher Ring,
  Relevanz). Privat je `tenant_id`.
- **Web-App:** Login → „Vorschläge" (Pool, nach Branche filterbar) → „auf mein Radar" +
  Ring → dein Radar (dynamisch gerendert).
- **Event-Log/YAML bleibt als Audit/Export-Prinzip** (E21); die App-DB ist die
  Projektion (Testkonzept ADR-T08: DB als Projektion, nie als alleinige Quelle).

## 4. Empfohlener, schlanker Stack (passt zu deinem Host)

- **Python-Web-App** (FastAPI oder Flask) — du fährst schon Gunicorn/Python auf Infomaniak.
- **DB:** SQLite für den MVP → MariaDB, wenn es wächst (hast du bereits).
- **Auth:** E-Mail/Passwort oder Magic-Link; **CH-Datenresidenz + revDSG** ernst nehmen
  (kein Fremd-Cloud-Login ohne Prüfung). SSO später.
- **Wiederverwendung:** die vorhandene render/detail-Logik → serverseitig je Nutzer.

## 5. MVP — bewusst brutal dünn (ein vertikaler Schnitt)

Das Kleinste, das echtes Feedback bringt:

1. **Signup/Login.**
2. **„Vorschläge"** = der geteilte Pool, nach Branche filterbar (Logik haben wir aus `kandidaten.html`).
3. Pro Vorschlag: **„auf mein Radar"** + Ring wählen (Watch default).
4. **„Mein Radar"** = die eigene Auswahl, gerendert (render.py-Logik dynamisch).

Kein Divergenzprotokoll-UI, keine Kompetenz-Panels, keine Zeitreise, keine Berichte —
alles später. Nur: **sehen · wählen · eigenen Radar haben.**
→ 5–10 Swiss-AI-Mitglieder ausprobieren lassen → Feedback → dann ausbauen.

## 6. Ehrliche Einordnung

- **Umfang:** realistisch **mehrere Wochen** bis zum brauchbaren MVP. Das ist ok, aber
  kein Wochenende — und deutlich mehr als die bisherigen Tages-Schritte.
- **Gratis-Modell:** keine Einnahmen → Infra billig halten; die Kosten liegen im
  **geteilten Sammeln** (einmal für alle), nicht pro Nutzer. Deckel bleiben wichtig.
- **Zwischenlösung (empfohlen):** den **bestehenden** (öffentlichen) Radar den
  Swiss-AI-Mitgliedern **jetzt schon zum Anschauen** geben (Interesse/Feedback sammeln),
  *während* der MVP entsteht. So entkoppeln wir „etwas zeigen" von „Plattform bauen".

## 7. Offene Entscheide (bevor Code)

- Stack bestätigen (FastAPI + SQLite→MariaDB?).
- Hosting: trägt der Infomaniak-Host eine dynamische App + DB, oder braucht es einen
  kleinen eigenen Server/VPS?
- Auth-Weg (eigenes Login vs. Magic-Link vs. SSO), Datenresidenz CH.
- Bleibt der statische Ein-Mandanten-Radar (dein heutiger) parallel bestehen?

## 8. Nächster Schritt

Wenn das Bild passt: MVP **Stück für Stück** — (1) Auth + DB-Grundgerüst, (2)
„Vorschläge"-Ansicht aus dem Pool, (3) „auf mein Radar" + eigenes Radar. Vorher:
Stack + Hosting bestätigen.
