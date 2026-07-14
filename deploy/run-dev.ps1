# run-dev.ps1 — Radar-MVP lokal starten (Entwicklung), ohne env-Zeilen zu tippen.
#   .\deploy\run-dev.ps1
# Optional: -AdminEmail / -AdminPw / -Port überschreiben die Defaults.
param(
  [string]$AdminEmail = "k.broennimann@gmail.com",
  [string]$AdminPw    = "dev-admin-123",
  [int]$Port          = 8794,
  [string]$Db         = "sqlite:///./radar.db",
  [string]$Instance   = "C:/Projekte/KI-Technology-Radar-Instanz"
)
$ErrorActionPreference = "Stop"
$repo = Split-Path $PSScriptRoot -Parent
Set-Location $repo

$env:RADAR_DB           = $Db
$env:RADAR_SECRET       = "dev-only-secret"
$env:RADAR_ADMIN_EMAIL  = $AdminEmail
$env:RADAR_ADMIN_PW     = $AdminPw
$env:RADAR_INSTANCE     = $Instance

Write-Host "Radar-MVP -> http://127.0.0.1:$Port   (Login: $AdminEmail)" -ForegroundColor Green
& "$repo\app\venv\Scripts\python.exe" -m uvicorn app.main:app --port $Port --reload
