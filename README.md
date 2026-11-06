# ClimaGuard AI

Climate-based dengue early warning for Tamil Nadu's 38 districts. It shows district health officers where weather is favouring dengue in the next 7 or 14 days, explains why, ranks the sub-districts to visit first, and sends each Village Health Nurse a short alert. Outputs are population-level risk estimates, **not diagnoses**.

| Folder | What's in it |
|---|---|
| [`backend/`](backend/README.md) | Python pipeline (weather, outbreak data, risk index, alerts) and the FastAPI API, on PostgreSQL |
| [`web/`](web/README.md) | React + Leaflet web app, phone-friendly |
| `dataset/` | Downloaded source data: district and sub-district boundaries, Census 2011 tables, IDSP weekly outbreak reports |
| `documents/` | MRD, PRD, solution overview, epics and user stories, project deck |
| [`docs/`](docs/qa-checklist.md) | Design decisions (`superpowers/specs/`) and the QA checklist |

## Run it locally

Needs Python 3.10+, Node 20+ and PostgreSQL.

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env               # set DATABASE_URL
createdb -U postgres climaguard
python -m climaguard.cli init-db
python -m climaguard.cli fetch-history --end 2026-10-25
python -m climaguard.cli import-idsp --end 2026-07
python -m climaguard.cli load-blocks
python -m climaguard.cli calibrate-index
python -m climaguard.cli run-live
python -m climaguard.cli create-admin --name "Your Name" --email you@example.com
python -m uvicorn api.main:app --port 8000
```

```bash
cd web
npm install
npm run dev                        # http://localhost:5173
```

See [backend/README.md](backend/README.md) for roles, sign-in, the daily schedule and the API.
