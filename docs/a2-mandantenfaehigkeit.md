# A2 — Mandantenfähigkeit, Benutzerverwaltung & dauerhafter Speicher (Design)

> Plan, nicht Code. Zweck: die Ausbaustufe A2 sauber sequenzieren, bevor wir bauen.
> Bezug: `docs/design-entscheidungen.md` (Ausblick A2), Zwei-Repo-Modell (E23/E25),
> Event-Sourcing (E21).

## 1. Das tragende Bild: zwei Schichten

Der entscheidende Einsicht (im Betrieb bestätigt): es gibt **zwei Schichten mit
unterschiedlicher Mandantenfähigkeit**.

```
  Quellen ─▶ [ SAMMELN (geteilt) ] ─▶ gemeinsamer, DAUERHAFTER Beleg-Pool
                                              │
                        ┌─────────────────────┼─────────────────────┐
                        ▼                     ▼                      ▼
              [ VERDICHTEN+WERTEN ]  [ VERDICHTEN+WERTEN ]   [ VERDICHTEN+WERTEN ]
                Mandant A (privat)     Mandant B (privat)      Mandant C (privat)
                = Radar A               = Radar B               = Radar C
```

- **Sammeln** ist generisch: dieselben KI-Entwicklungen betreffen alle. Einmal
  sammeln (teuer: API), in einen **dauerhaften, deduplizierten Beleg-Pool** legen.
- **Verdichten + Werten** (Themen bilden, Ring, `relevance_org`, Kompetenz-
  Kritikalität) ist **pro Mandant** — hier lebt die Identität der Organisation (E25).
  Das ist das eigentliche Produkt: geteilte Sammel-Maschine + kuratierter Radar je Kunde.

## 2. Was heute fehlt (Ist → Soll)

| | Heute | Soll (A2) |
|---|---|---|
| Beleg-Speicher | Eingangskorb = **rollierendes Fenster** (jeden Lauf geleert), nicht archiviert | **Dauerhafter, deduplizierter Pool** (hält „alles" — Voraussetzung für 10-Jahres-Historie & Lernen) |
| Mandanten | 1 (Datei-Instanz) | N Instanzen, aus dem geteilten Pool kuratiert |
| Auth | keine (offene dev-URL, synthetische Daten) | Login + Rollen; **Pflicht, bevor echte private Wertung auf offener URL liegt** |
| Verdichten | halb-manuell (Agent schlägt vor, Mensch bündelt) | Agent clustert zu Themen-Vorschlägen; Mensch ratifiziert |

## 3. Bausteine

**a) Dauerhafter Beleg-Pool (geteilt).** Append-only, dedupliziert per URL/Inhalt.
Quelle der Wahrheit bleibt versioniert (Event-Log/YAML, E21); eine DB kommt als
**Projektion/Index** dazu (Testkonzept ADR-T08: DB als Projektion, nie als Quelle),
sobald das Volumen es verlangt. Trägt die Vision „im Hintergrund hält der Radar alles".

**b) Identität & Auth.** Benutzer, Mandanten, Rollen (mind. *Kurator* = ratifiziert,
*Betrachter* = liest). Login statt URL-Rate. Datenresidenz beachten (CH/EU).

**c) Mandanten-Isolation.** Das Repo-/Instanz-Modell garantiert sie heute (private
Wertung verlässt das private Repo nie, E23/E25). In der DB-Projektion setzt sich das
als `tenant_id`-Trennung fort — dasselbe Prinzip: private Kuratierung bleibt beim Mandanten.

**d) Serving pro Mandant.** Nach Login sieht der Nutzer den Radar *seines* Mandanten
(Auswahl über Identität, nicht über die URL). Der geteilte Pool speist alle.

## 4. Phasen (inkrementell, nicht als Big Bang)

- **P0 — heute:** 1 Mandant, statisch, keine Auth (synthetische/gering sensible Daten). ✓
- **P1 — Dauerhafter Pool:** Eingangskorb aufhören zu leeren; akkumulieren + deduplizieren.
  Ergebnis: „alles gefunden" bleibt erhalten → 10-Jahres-Historie & Lernen werden möglich.
  *(Kleinster, wertvollster Schritt — unabhängig von Auth.)*
- **P2 — Auth & Identität:** Login + Rollen. **Tor** vor echter privater Wertung auf
  offener URL.
- **P3 — Mehr-Mandanten-Serving:** N Instanzen, Mandant per Login; geteilter Pool speist alle.
- **P4 — Interaktive App:** die DB-Projektion mit Reinklicken/Live-Kuratierung ersetzt
  die statische Site für angemeldete Nutzer.

## 5. Ehrliche Sequenzierung (Rat)

- **Kundensignal vor Infrastruktur.** Der heutige Ein-Mandanten-Radar ist vorzeigbar.
  Bevor viel in Tenancy-Technik fliesst: **einem echten Interessenten zeigen.** Das
  validiert die Nachfrage *und* formt, was Mandantenfähigkeit konkret können muss —
  sonst bauen wir Annahmen.
- **P1 lohnt sich unabhängig davon** (dauerhafter Pool = besseres Produkt, mehr Daten,
  Lernen) und ist technisch klein. Guter erster Schritt, auch ohne Kunden.
- **„10 Jahre auf einen Schlag" geht nicht als Rundumschlag** (Feeds reichen nicht
  zurück; arXiv = Millionen Paper ohne Wichtigkeitssortierung). Historie = **kuratierte
  Meilensteine + gezielte Datumsbereich-Läufe**; das Nächtliche-Inkrement ist schon richtig.

## 6. Offene Entscheide

- Auth-Mechanismus (eigenes Login vs. SSO/OIDC; Datenresidenz CH).
- DB-Technologie der Projektion (MariaDB als Index; Vektor-Store fürs RAG-Grounding).
- Bleibt die statische Site pro Mandant (P3) oder direkt die interaktive App (P4)?
- Preis-/Betriebsmodell je Mandant (Sammeln geteilt, Kuratieren pro Kunde).
