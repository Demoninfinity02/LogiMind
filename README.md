# Predictive Logistics LogiMind (Near Real-Time)

This is a lightweight Django demo that *feels* real-time using polling (no websockets).

## What’s included

- Live weather integration (OpenWeatherMap if `OPENWEATHER_API_KEY` is set; otherwise Open-Meteo fallback)
- Simulated external disruptions (geopolitical / congestion / strike)
- Dynamic risk + ETA computation (weather + disruptions + transport mode)
- JS polling endpoint: `GET /live-updates/` (HTML partial)
- Lightweight background refresh via management command (cron-friendly)

## Local run

1) Create a venv and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2) Configure env:

```bash
cp .env.example .env
```

`manage.py` automatically loads `.env` for local runs.

Additional env templates:
- `.env` -> local editable keys file (already gitignored)
- `.env.render` -> copy values into Render environment variable panel

3) Initialize DB + seed demo data:

```bash
python manage.py migrate
python manage.py seed_demo
```

4) Start the web server:

```bash
python manage.py runserver
```

5) (Optional but recommended) Run the lightweight refresher in another terminal:

```bash
python manage.py refresh_live_data --loop --interval 180
```

If you see an import error running the refresher, make sure you’re using the venv Python (either `source .venv/bin/activate` first, or run `./.venv/bin/python manage.py refresh_live_data ...`).

Open: http://127.0.0.1:8000/

## Demo flow

- Start with seeded shipments (low risk baseline).
- Run `refresh_live_data` to pull live weather snapshots and update stored risk/ETA.
- Create/activate a disruption in Django admin (`/admin/`) and watch the dashboard auto-refresh.

## Render deployment notes

- This repo now includes `render.yaml` with:
  - a Django web service,
  - a Postgres database,
  - and a cron service that runs `refresh_live_data --once` every 5 minutes.
- Deploy on Render by creating a **Blueprint** from this repository.
- Keep `DEBUG=0` in Render, and use a real `SECRET_KEY` (auto-generated in `render.yaml`).
- `RENDER_EXTERNAL_HOSTNAME` is automatically supported in `ALLOWED_HOSTS` and CSRF trusted origins.
- Database uses `DATABASE_URL` (Postgres) and enables SSL in production by default.
