# ClimaGuard AI — Build Design

Date: 2026-11-01 · Source documents: `documents/` (MRD, PRD, Solution and overview, Epics and User Stories, project deck, hackathon kickoff).

This document says how the prototype gets built. It does not restate the *what*; the PRD and the backlog are the spec, and every story ID below refers to `ClimaGuard_AI_Epics_and_User_Stories.docx`.

## 0. Revision — 2026-11-01, decisions from the user

These override anything below that conflicts.
- **A live product, not a demo.** A scheduled job pulls the live Open-Meteo forecast (with the last 60 days observed) and scores all 38 districts, and the API serves the latest run. NF1's "offline at demo" no longer applies; a cached last run is still served if Open-Meteo is down.
- **Database: the user's local PostgreSQL 18** (no PostGIS installed). Boundaries are served as GeoJSON files, since no spatial queries are needed. `DATABASE_URL` lives in `.env`, which the user fills in.
- **Real data only.** The user downloads the datasets the builder links into `data/raw/`; nothing is simulated. Influenza (C1) stays out until a real source exists.
- **Order:** backend and ML first, frontend after.
- **No live case feed exists publicly.** Historic monthly cases (Indiastat, 2017-18 to 2020-21) train the model. Live risk is driven by weather plus each district's historic normal level for that month. Last month's case count is *not* a model feature, because it would be unknown at run time. New case files (IHIP, when available) are re-imported through the same loader, followed by a retrain.
- **New districts** (Chengalpattu, Ranipet, Tirupathur, Kallakurichi, Tenkasi, Mayiladuthurai) borrow their parent district's case history for the normal level, until their own history exists.
- **Above-normal label:** cases above mean + 2 SD of the *other* years for the same district and month (leave-one-year-out, because only four years exist), and at least 5 cases, so 0-vs-1 noise isn't flagged. Both numbers are in config.
- **Training examples:** one per district per weekly run date in history. Observed archive weather stands in for the forecast window (a perfect-forecast assumption, stated in the backtest).
- **The demo storyline goes:** only districts the model really flags are shown; no pinned results.

### Revision 2 — 2026-11-01, data reality

- **Indiastat is subscription-only**, and the user couldn't download it. The free real source used instead is NCDC's IDSP weekly outbreak reports (498 PDFs, 2017 to week 34 of 2026). They yield 89 Tamil Nadu dengue outbreaks: 82 positive district-months out of 3,680.
- **The XGBoost model trained on outbreak labels didn't beat chance**: AUC 0.49–0.70 by season, about 0.58 on average, and 0 of 8 held-out outbreak months detected. It stays in the code but is switched off (`RISK_ENGINE = "model"`).
- **Live engine, chosen by the user: a weather suitability index** (`climaguard/index.py`). It combines four biology-based components (temperature band 0.35, rain 3–8 weeks back 0.35, rainy days 0.15, humidity 0.15), scored as a percentile against the same district and calendar month in 2017–2025. Index levels: Low < 50th, Moderate 50–80th, High 80–95th, Very high ≥ 95th. *This replaces the PRD's probability thresholds for the index*, because a percentile isn't a probability. The PRD thresholds still apply to the model.
- **Driver cards compare with the usual for that month** ("More rain than usual 3–8 weeks ago → more breeding sites now"). Contributions are exact: weight × (component − normal).
- **API**: `probability` is renamed `score`, and each response carries a `score_meaning`, so screens can't present the index as a case forecast.
- **Known limitation**: the index shows no agreement with IDSP outbreak reports (AUC 0.49). It's an explainable climate signal, not a validated predictor. The PRD's "beats the baseline" metric can't be met until real monthly case counts exist.

### Revision 3 — 2026-11-01, field priority (E4-S1)

- **Units are Census 2011 sub-districts (216 taluks), not health blocks**: no free block boundaries exist. Each taluk is assigned to its current district by its centroid, so the 2019-20 districts get their taluks. Chennai is one census unit, plus Madhavaram, which now falls inside Chennai.
- **Vulnerability** = equal mix of within-district percentile ranks of population density, share of children 0–6, and past IDSP dengue outbreaks. An outbreak is matched to a taluk by the block named in its report: 41 of 67 matched; the rest name blocks that aren't taluk names. **Older adults are left out**: Census age bands exist only per district, so they can't rank taluks within one.
- **Priority** = district score × vulnerability, shown only when the district is High or Very high. It covers **all districts**, not just the five spotlight districts (PRD R2's limit was about time, and the data covers the whole state).
- **Actions** are rule-based (past outbreak → revisit; dense → tanks, construction sites, tyres; many children → schools and anganwadis; always → stored-water check). The text still needs review by a public health official before real use, as the Solution doc requires.

### Revision 4 — 2026-11-01, nurses (E1-S2, E4-S2, E4-S3)

- **Staff are entered by the district officer** on the Staff screen (name, mobile, blocks within the district). Nothing is seeded, and no fictional people exist in the data. Lists show only the last 4 digits of a mobile number.
- **Outbox**: after each run, every nurse with blocks in an alerted district gets one message, from the 7-day outlook if both outlooks alerted, naming their top block and its first action. It's at most 160 characters, enforced in code and by a DB check, with no names or numbers. Nothing is sent.
- **My blocks**: only High or Very high assigned blocks, ranked, with the latest message on top and advice for children 0–12, adults 13–64 and older adults 65+ (Solution doc guidance cards, draft for official review). Otherwise it shows "No priority visits this week".
- **Until sign-in (E1-S1, E1-S3)**, a "Viewing as" switch picks the officer or a nurse. The API has no authentication yet.
- **Alerts fire once per High streak**: on the run where a district reaches its second High+ run in a row, or on a two-level jump. A district that stays High keeps its level on the map and in My blocks, but it gets no new alert or SMS each day (alert fatigue, MRD risk log). After it drops below High, a new streak alerts again.
- **Daily schedule**: Windows task "ClimaGuard daily run" at 06:00 (`backend/run_live.cmd`, log in `backend/logs/`). It catches up if missed and retries twice. There's **one live run per day**: a same-day re-run replaces that day's run, so "two runs in a row" always means two days. The web app warns when the outlook is more than a day old.
- **`load-blocks` now upserts on the census code**, so block ids, and the nurse assignments that point at them, survive a reload.

### Revision 5 — 2026-11-01, sign-in and roles (E1-S1, E1-S3)

- **The staff table is the user table.** Roles are admin, officer (Deputy Director) and nurse. Admins and officers sign in with an email, nurses with their mobile. The first admin comes from `cli create-admin`; the admin creates officers, officers create nurses in their own district only (the district comes from the session, never the request).
- **Passwords:** scrypt (standard library), at least 10 characters. A one-time password is shown once at creation, never stored in plain text, and must be replaced at first sign-in; every endpoint returns 403 until then.
- **Sessions:** random token in an HttpOnly, SameSite=Lax cookie, 12 hours, with only its SHA-256 stored in `sessions`. Sign-in failures show one message for unknown user and wrong password. Five failures lock the account for 15 minutes.
- **Every endpoint except health and sign-in needs a session**, checked by role. The "Viewing as" switch is gone. PRD W4 ("login and roles: Won't") is now superseded, as the backlog's E1-S1 to S3 asked.
- **Password reset** follows the creation chain: the admin resets officers and other admins (never themselves), and an officer resets nurses in their own district. A reset issues a new one-time password, clears the lockout and deletes all of the person's sessions.
- **Not built:** sign-in through a government identity provider, and a voluntary "change my password" screen (only the forced first-time change exists).

### Revision 6 — 2026-11-01, what-if (E5-S1)

- The sliders scale **forecast days only** (after the run date, up to the target date); observed weather is never changed. Humidity is capped at 100%.
- The district is re-scored by the same engine as the live run (`model.score_weather`). Forecast and scenario are both recomputed from the same weather, so the difference comes only from the sliders. It takes about 0.2 s server-side and 0.55 s end to end in the browser.
- Because breeding-site rain is lagged 3–8 weeks, rain sliders move a 7- or 14-day outlook only slightly (via rainy days); the screen says so instead of exaggerating. A district already at the top of its record (score 1.0) cannot go higher.

### Revision 7 — 2026-11-01, feedback panel (E5-S2)

- `calibrate-index` replays the index over the **latest season with all 12 months of outbreak data** (now 2025-26) at weekly run dates, both horizons, and writes `models/index_feedback.json`.
- **Per district and month** it records the highest outlook, whether a run *before the month began* already said High+ (warned in advance) with the lead in weeks, and whether IDSP reported an outbreak. Newer districts show their parent's record, which is counted once (under the parent) in the totals.
- **2025-26 result:** 3 of 8 outbreak months warned in advance (38%), against 0 of 8 for "same month last year". The median lead is 1.7 weeks, but 86 of 89 warned months (97%) had no outbreak reported. That's shown as-is on "How far to trust it".

### Revision 8 — 2026-11-02, self sign-up (requested by the user)

- The sign-in page has a **Create account** tab: name, role, district (officers and nurses), blocks (nurses), email or mobile, and their own password.
- **The user chose approval:** a request is saved with `status = 'pending'` and can't sign in until approved. The admin approves officers and admins, and can also approve nurses; a district officer approves nurses of their own district only. This stops a stranger making themselves State admin.
- Pending or rejected status is revealed only after the right password. Only `active` staff have sessions or receive outbox messages. Rejected rows stay on record, but are cleared when the same email or mobile applies again.
- No rate limit on sign-ups yet; it's needed before exposure beyond a trusted network.

## 1. Intent

Tamil Nadu's district health officers learn about dengue surges after they happen. ClimaGuard AI gives a Deputy Director of Health Services a 7/14-day, explained outlook of which districts will have an above-normal dengue month. It then turns that outlook into a ranked block list and a field message for the Village Health Nurse. The end-to-end journey to demo is **map → reason → priority list → field message** (PRD §1, §8).

The hackathon judges trace every demo step to a story, an epic, a PRD feature and an MRD need. A screen that can't be traced loses marks, so traceability is a build constraint, not an afterthought.

## 2. Goals, non-goals, anti-goals

**Goals**
- All Must-Have stories pass their acceptance criteria: E1-S4, E2-S1–S3, E3-S1–S2, E4-S1–S3.
- On a held-out season, the model beats the "same month last year" baseline on detection rate and Brier score, and the backtest reports lead time (PRD §4).
- A stranger can run the repo from the README in under 5 minutes, fully offline (NF1).

**Should, in this order once every Must passes:** E1-S1–S3 (sign-in and roles), E5-S1 (what-if), E5-S2 (predicted vs reported). **Could:** E4-S4 (mark visited), C1 influenza, C2 Tamil messages, C3 trend chart.

**Non-goals (PRD Won'ts):** native mobile app, live SMS, COVID-19, states other than Tamil Nadu.

**Anti-goals (a failure even if it technically works)**
- Anything that reads as a diagnosis or ranks individual households or people.
- Personal or patient data anywhere in data, code or messages (NF2).
- A colour-only risk display (NF5).
- A feature that's demoed but not in the backlog.
- Claiming true case counts.

## 3. Constraints

- Offline at demo time: cached CSV/GeoJSON only, no live API calls (NF1).
- "Risk estimate, not a diagnosis" on every screen (NF3).
- Responsive web app, usable at 360 px (NF4). The nurse's "My blocks" screen is designed phone-first.
- Every screen and endpoint carries its story ID (NF6), as a code comment and in the QA checklist.
- Risk levels: Low < 25%, Moderate 25–50%, High 50–75%, Very high > 75%. The target is an above-normal month, meaning cases above that district's mean + 2 SD for that month in earlier years.
- Alert rule: High or above on two consecutive runs, or a jump of two levels at once.
- Outbox messages are 160 characters or fewer and name the block and the first action.

## 4. Approaches considered

| | Approach | Trade-off | Decision |
|---|---|---|---|
| A | Documented stack (Python + XGBoost + SHAP → FastAPI → React/Leaflet on SQLite + GeoJSON). Must-Haves first; a role switcher stands in for login until E1-S1–S3 are built. | Login may slip, which the PRD allows because it's a Should-Have. | **Chosen by the user.** It's the only option that matches all five documents and starts the riskiest work (the model) first. |
| B | Same stack, login first (E1-S1–S3), following deck slide 8's order. | Hours spent on Should-Haves before any Must works; this is the kickoff's "everything is a Must" trap. | Rejected |
| C | No backend; the model writes static JSON for React. | Removes the FastAPI layer shown on deck slides 5 and 7 (breaks traceability); what-if and alert runs have to be precomputed. | Rejected |

## 5. Decided parts of the how

### 5.1 Platform
One web app, responsive (decided by PRD W3 and NF4). No native mobile build.

### 5.2 Repository layout
```
data/raw/          downloaded source files, untouched
data/processed/    cleaned tables, features, model outputs (SQLite db lives here)
pipeline/          Python: ingest, features, train, backtest, score, explain, alerts
api/               FastAPI app reading the SQLite db
web/               React (Vite) + Leaflet + Recharts
tests/             pytest for pipeline rules and API
docs/              this design, QA checklist, AI log
```

### 5.3 Data (E1-S4)
| Data | Source | Fallback |
|---|---|---|
| Monthly district dengue cases | Indiastat (2017-18 onward), Plan A | Dataful HMIS 2020-21 (train) and 2021-22 (test) — PRD R1, with weak validation stated openly |
| Block (sub-district) dengue | Dataful HMIS sub-district | Krishnagiri only (PRD R2) |
| Weather history | Open-Meteo archive, daily, at each district's centroid | — |
| Forecast | One Open-Meteo 16-day forecast snapshot, saved to `data/raw` | — |
| Population, age, density | Census 2011, district and sub-district | — |
| Boundaries | District and block GeoJSON (e.g. DataMeet), reconciled to the 38 current districts | — |

A one-time `pipeline/fetch.py` downloads everything. After that, nothing touches the network.

### 5.4 Risk engine (E1-S4)
- Features: rainfall lagged 1–8 weeks, consecutive rainy days, mean temperature, days in the Aedes transmission temperature band, mean humidity, season terms, last month's cases, population density.
- Model: one XGBoost classifier pooled across all districts. Baselines: logistic regression and "same month last year".
- Backtest: the latest full season is held out and never trained on. It reports detection rate, lead time, Brier score and false-alarm rate against the baseline, written to `data/processed/backtest.json`.
- Scoring: each run combines observed recent weather with the 7-day or 14-day forecast window and stores one row per district, horizon and run: probability, level, and the top three SHAP drivers.
- Explanations: a lookup table maps each feature to a plain-language sentence with direction and lag (E3-S2). A test fails if any model feature lacks a sentence.

### 5.5 "Runs" and alerts (E4-S2)
A run is one weekly scoring pass, stored in a `runs` table. The alert rule compares each district's current run with its previous one. For the demo, the pipeline replays the held-out season as weekly runs (deck demo step 1), then adds the cached live-forecast run as the latest (demo step 2). The alert rule has unit tests for: two consecutive High runs → fires; one High run → doesn't fire; two-level jump → fires.

### 5.6 Field priority (E4-S1, E4-S3)
Applies only to the five spotlight districts (Chennai, Coimbatore, Krishnagiri, Madurai, The Nilgiris) at High or Very high. Block priority = district probability × vulnerability index. The index is a normalised mix of density, share of children, share of older adults, and past hotspot frequency. Each block shows the factors behind its rank, plus at least one "what to check" action and age-banded advice from the Solution doc's guidance cards.

### 5.7 People without login (until E1-S1–S3)
A seed file `data/seed/staff.csv` holds fictional staff: Dr. S. Kavitha (Krishnagiri Deputy Director), R. Selvi (Village Health Nurse, Shoolagiri) and a few more. Phone numbers are obviously fake. A header role switcher picks who you are, and "My blocks" reads that person's block assignments. Once E1-S1–S3 are built, real sign-in replaces the switcher; the same staff table becomes the user table, with hashed passwords.

### 5.8 API (FastAPI)
`/risk?horizon=7|14`, `/districts/{id}` (level, probability, drivers), `/priority/{district}`, `/alerts` (outbox), `/staff/{id}/blocks`. Added with the Shoulds: `/whatif`, `/feedback`, `/auth/*`, `/users`. The API only reads precomputed tables, except `/whatif`, which re-scores one district using the saved model.

### 5.9 Screens → stories
| Screen | Stories |
|---|---|
| State risk map with 7/14 toggle and needs-attention list | E2-S1, E2-S2, E2-S3 |
| District detail with three driver cards | E3-S1, E3-S2 |
| Block priority list | E4-S1 |
| Alert outbox | E4-S2 |
| My blocks (phone-first) | E4-S3 |
| What-if, feedback panel, sign-in, user admin | E5-S1, E5-S2, E1-S1–S3 (later) |

### 5.10 Testing and QA
pytest covers the level thresholds, the alert rule, message length and content (no personal data), driver-lookup coverage, and the API's response shapes. `docs/qa-checklist.md` lists every acceptance criterion with pass/fail; it's a hackathon deliverable.

### 5.11 Run
The README gives one command per part (`pipeline`, `api`, `web`) plus a `docker compose up` path. Processed outputs are committed, so a stranger doesn't need to retrain.

### 5.12 Settled during review (builder's calls, open to correction)
- **Weekly run vs monthly label.** A run on date *d* with horizon *h* predicts whether the calendar month containing *d + h* will be above normal. Lead time is the number of weekly runs between the first High flag for a month and that month's first day.
- **Scope when data runs short.** The PRD decides: R2 allows a Krishnagiri-only priority list, and what-if and feedback stay Should-Haves even though the Solution doc's success table lists them.
- **Source documents.** The builder flags the fixes in §6 and doesn't edit the .docx files. The BA owns those documents.

## 6. Traceability fixes needed in the documents
- E1-S1–S3 trace to "PRD S4" and E4-S4 traces to "PRD C4"; neither exists in the PRD feature table. Either add S4 (sign-in and roles) and C4 (visit tracking) to the PRD, or re-point the stories. PRD W4 ("User login and roles: Won't") also conflicts with E1-S1–S3 and needs editing.
- PRD §7's Stories column is still "TBD"; fill it from the backlog.

## 7. Left to the builder
- Exact feature set and hyperparameters, as long as the backtest reports the PRD metrics.
- Vulnerability index weights (equal by default, stated in the UI).
- How district boundaries get reconciled when the GeoJSON predates the newer districts.
- Visual design, within NF3–NF5.
- Exact schema and file names inside `data/processed`.
