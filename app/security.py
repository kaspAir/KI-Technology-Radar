"""security.py — Passwort-Hashing ohne native Abhängigkeiten (PBKDF2, stdlib).

Sicher genug fürs MVP und plattformunabhängig (kein bcrypt-Wheel nötig). Für
CH-Datenresidenz/revDSG: Passwörter nur gehasht speichern (hier), Session-Secret
aus der Umgebung (RADAR_SECRET), HTTPS im Betrieb.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os

_ITER = 200_000


def hash_pw(pw: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, _ITER)
    return "pbkdf2$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(dk).decode()


def verify_pw(pw: str, stored: str) -> bool:
    try:
        scheme, s, d = stored.split("$")
        if scheme != "pbkdf2":
            return False
        salt, dk = base64.b64decode(s), base64.b64decode(d)
        test = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, _ITER)
        return hmac.compare_digest(dk, test)
    except Exception:
        return False
