# ClimaGuard AI — backend

Dengue early-warning pipeline and API for Tamil Nadu's 38 districts. Outputs are population-level risk estimates, not diagnoses.

## Setup

Needs Python 3.10+ and a local PostgreSQL.

```bash
pip install -r requirements.txt
cp .env.example .env          # edit DATABASE_URL if your Postgres needs a password
createdb -U postgres climaguard
```

## Data (`../dataset/`)

| File | Source |
|---|---|
| `TAMIL NADU_DISTRICTS.geojson`, `TAMILNADU_SUBDISTRICTS.geojson` | [datta07/INDIAN-SHAPEFILES](https://github.com/datta07/INDIAN-SHAPEFILES/tree/master/STATES/TAMIL%20NADU) |
| `idsp_weekly/<year>/*.pdf` | [NCDC IDSP weekly outbreak reports](https://ncdc.mohfw.gov.in/includes/WeeklyOutbreaks.php) |
| `idsp_tn_dengue_outbreaks.csv` | written by `import-idsp`: every Tamil Nadu dengue row parsed (with the block named in the report), for audit |
| `census/PCA_TV_3301…3332.xlsx` | [Census 2011 PCA, town/village/ward level](https://censusindia.gov.in/nada/index.php/catalog/6794), one file per 2011 district |

Weather comes from Open-Meteo through the pipeline; no download needed.

## Risk engine

`RISK_ENGINE` in `climaguard/config.py`:

- **`index`** (default): a weather suitability index built from Aedes biology (temperature band, rain 3–8 weeks back, rainy days, humidity). It's scored as a percentile against the same district and month in 2017–2025. Levels: Low < 50th percentile, Moderate 50–80th, High 80–95th, Very high ≥ 95th. It is *not* fitted to case data and does not forecast cases. Checked against IDSP outbreaks it shows no agreement (AUC 0.49, `models/index_validation.json`); those reports are sparse (~9 per year) and reporting-driven.
- **`model`**: XGBoost on case labels with PRD probability levels. On IDSP outbreak labels it reached only AUC ~0.58, so it stays off until real monthly case counts (Indiastat or IHIP) are imported with `import-cases` and `LABEL = "counts"`.

## Pipeline

```bash
python -m climaguard.cli init-db                           # tables + 38 districts from the boundaries file
python -m climaguard.cli fetch-history --end 2026-10-25    # Open-Meteo daily weather from 2017-01
python -m climaguard.cli import-idsp --end 2026-07         # parse IDSP PDFs -> monthly outbreak grid
python -m climaguard.cli load-blocks                       # 216 sub-districts: census + past outbreaks -> vulnerability
python -m climaguard.cli calibrate-index                   # district-month climatology + validation report
python -m climaguard.cli run-live                          # live forecast -> risk for 7/14 days -> alerts
# with real case counts instead:  import-cases FILE.csv --source "..."  then  train
```

## Daily run

A Windows scheduled task, **ClimaGuard daily run**, calls `run_live.cmd` every day at 06:00. If the PC was off, it runs at the next logon; it retries twice, 15 minutes apart. Output goes to `logs/run-live.log`.

- One live run per day: running it again the same day (by hand or a late catch-up) replaces that day's run.
- Alerts compare with the previous days' runs of the same engine version, and fire once per High streak.
- If a run fails, the API keeps serving the last good run, and the web app warns when the outlook is more than a day old.
- The task runs only while you're logged on (no stored password). For a server, recreate it with "Run whether user is logged on or not".

```powershell
Get-ScheduledTaskInfo -TaskName 'ClimaGuard daily run'   # last result (0 = ok), next run
Start-ScheduledTask   -TaskName 'ClimaGuard daily run'   # run now
```

## API

```bash
uvicorn api.main:app --reload     # http://localhost:8000/docs
```

| Endpoint | Story |
|---|---|
| `GET /api/risk?horizon=7\|14` | E2-S1, E2-S2, E2-S3 |
| `GET /api/districts/{id}?horizon=7\|14` | E3-S1, E3-S2 |
| `GET /api/districts/{id}/priority?horizon=7\|14` | E4-S1 |
| `GET /api/districts/{id}/whatif?horizon=&rain=&humidity=` (−50…+50 %) | E5-S1 |
| `GET /api/alerts` | E4-S2 (district alerts) |
| `GET /api/outbox` | E4-S2 (one simulated SMS per nurse in an alerted district, ≤ 160 chars) |
| `GET /api/blocks?district_id=` · `GET /api/staff` · `POST /api/staff` | E1-S2 |
| `GET /api/me/blocks?horizon=7\|14` | E4-S3 |
| `POST /api/signup` · `GET /api/public/districts` · `GET /api/public/blocks` | self sign-up (no session) |
| `GET /api/requests` · `POST /api/requests/{id}/approve\|reject` | approving sign-ups |

## Accounts and sign-in

Create the first state admin yourself. The command prints a one-time password once:

```bash
python -m climaguard.cli create-admin --name "Your Name" --email you@tn.gov.in
```

The admin creates Deputy Director accounts; each Deputy Director creates the nurses for their own district. Every new account gets a one-time password, shown once, which must be replaced at first sign-in.

**Self sign-up:** the sign-in page also has **Create account**. A person picks a role and sets their own password. The request is saved with status `pending` and can't sign in until approved: the state admin approves Deputy Directors and admins (and nurses, if a district has no officer yet), and a Deputy Director approves nurses for their own district. Requests appear under **Account requests** on the Users and Staff screens. Rejected requests are kept on record, and the person may apply again.

| Role | Signs in with | Lands on | Can use |
|---|---|---|---|
| State admin | email | Users | user management, the outlook, alerts |
| Deputy Director | email | Outlook (own district open) | outlook, priority list, own district's staff and outbox |
| Village Health Nurse | mobile number | My blocks | own blocks only |

- **Passwords:** hashed with scrypt; at least 10 characters.
- **Lockout:** 5 wrong attempts lock an account for 15 minutes.
- **Sessions:** last 12 hours, in an HttpOnly cookie; only the token's SHA-256 is stored.
- **Behind HTTPS:** set `COOKIE_SECURE=true`.
- **Password reset:** the state admin resets Deputy Directors (and other admins, not themselves); a Deputy Director resets nurses in their own district (**Reset password** on the Users / Staff screens). A reset gives a new one-time password, clears any lockout and signs the person out on every device.
| `GET /api/backtest` | E1-S4 (index validation, or model backtest) |
| `GET /api/feedback?district_id=` | E5-S2 (last complete season replayed, month by month; built by `calibrate-index`) |
| `GET /api/geo/districts` | map boundaries |

## Tests

```bash
python -m pytest -q
```

`test_pipeline_db.py` creates and drops a throwaway `climaguard_test` database.
