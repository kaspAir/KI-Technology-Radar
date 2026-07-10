# Beispiel-Instanz (öffentlich, synthetisch)

Diese Instanz enthält **keine echten Organisationsdaten**, sondern ein
synthetisches Beispiel. Sie dient zwei Zwecken:

1. **Selbsttest des Kerns:** Die Kern-CI validiert diese Instanz bei jedem Build
   (die *private* echte Instanz liegt in einem separaten Repo und ist der CI des
   Kerns nicht zugänglich — E23). So prüft der Kern seinen Mechanismus an einem
   vollständigen Fall, ohne je private Daten zu berühren.
2. **Referenz für Adopter:** ein lauffähiges Minimalbeispiel des Schemas.

```bash
python src/validate.py --instance examples/sample-instance
```

Alle Werte hier sind erfunden und bewusst neutral.
