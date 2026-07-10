# Reproduzierbares Testimage (Testkonzept: Ausführung Jenkins Build · Docker).
# Führt die schnelle deterministische Suite aus und erzeugt das Testprotokoll.
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Standard: schnelle Suite gegen die synthetische Beispiel-Instanz auf dev.
CMD ["python", "testing/run_suite.py", "--env", "dev", "--instance", "examples/sample-instance"]
