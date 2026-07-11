# Selbstbedienungs-Radar (MVP)

Mandantenfähige Web-App: jedes Mitglied ein eigener Radar, selbst kuratiert aus dem
geteilten Vorschlags-Pool. Erster vertikaler Schnitt (Signup → Vorschläge → mein Radar).
Design: `docs/selbstbedienungs-radar-design.md`.

## Lokal starten

```bash
python -m venv app/venv
app/venv/Scripts/pip install -r app/requirements.txt      # Windows; sonst app/venv/bin/pip
app/venv/Scripts/python -m app.seed ../KI-Technology-Radar-Instanz/inbox/pool.yaml
RADAR_SECRET=<zufall> app/venv/Scripts/python -m uvicorn app.main:app --reload
# -> http://127.0.0.1:8000  (Registrieren, dann Vorschläge kuratieren)
```

## Umgebung

- `RADAR_DB` — Default `sqlite:///./radar.db`. Produktion (MariaDB):
  `mysql+pymysql://user:pw@host/db` (zusätzlich `pip install pymysql`).
- `RADAR_SECRET` — Session-Schlüssel (im Betrieb setzen, nicht der Default).
- Betrieb: hinter HTTPS; CH-Datenresidenz/revDSG beachten (echte Nutzerkonten).

## Struktur

- `db.py` — Modelle: User, Proposal (geteilter Pool), Curation (private Wertung je user_id).
- `security.py` — PBKDF2-Passwort-Hashing (stdlib, keine native Abhängigkeit).
- `seed.py` — importiert `inbox/pool.yaml` → Proposals.
- `main.py` — FastAPI-Routen (Auth, /proposals, /add, /radar, /remove).
- `templates/` — Jinja2 (gleiche Ästhetik wie der statische Radar).

## Noch nicht (bewusst): SVG-Radar-Ansicht, Kompetenz-Panels, Zeitreise, Berichte,
Divergenzprotokoll-UI, Rollen, Magic-Link/SSO. Kommt nach erstem Nutzer-Feedback.
