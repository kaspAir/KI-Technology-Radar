"""gunicorn_conf.py — Produktionsprozess des Selbstbedienungs-Radars.

Start (auf dem Host):  gunicorn -c app/gunicorn_conf.py app.main:app
Gunicorn läuft lokal an 127.0.0.1:$RADAR_PORT; der Webserver (bzw. der PHP-Proxy
im Docroot, wie bei hermespia.ch) leitet die öffentliche Domain darauf um.
"""
import os

_port = os.environ.get("RADAR_PORT", "8030")
bind = f"127.0.0.1:{_port}"
worker_class = "uvicorn.workers.UvicornWorker"
workers = int(os.environ.get("RADAR_WORKERS", "2"))
timeout = int(os.environ.get("RADAR_TIMEOUT", "60"))
graceful_timeout = 30
keepalive = 5
# Managed Hosting: Prozess soll nach Deploy/Neustart sauber wieder hochkommen.
max_requests = 1000
max_requests_jitter = 100
accesslog = os.environ.get("RADAR_ACCESSLOG", "-")   # "-" = stdout (Cron leitet in Logdatei)
errorlog = os.environ.get("RADAR_ERRORLOG", "-")
proc_name = "ki-radar-mvp"
