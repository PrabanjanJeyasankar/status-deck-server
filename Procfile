release: python -m prisma generate

web: uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
auto_incident_monitor: python -m app.monitors.auto_incident_monitor