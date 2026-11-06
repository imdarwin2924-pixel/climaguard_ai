# ClimaGuard AI — web

React + Leaflet officer dashboard. It reads the FastAPI backend (`../backend`) through the Vite proxy on `/api`.

```bash
npm install
npm run dev        # http://localhost:5173  (start the API first: uvicorn api.main:app --app-dir ../backend)
# API elsewhere? CG_API=http://localhost:8001 npm run dev
```

| Screen | Stories |
|---|---|
| Outlook: risk map, 7/14-day toggle, labels, legend | E2-S1, E2-S2 |
| Needs attention list | E2-S3 |
| District panel with three driver cards | E3-S1, E3-S2 |
| "Where to go first": ranked sub-districts with factors and actions | E4-S1 |
| "What if the weather changes?": rainfall and humidity sliders, scenario vs forecast | E5-S1 |
| Staff: add Village Health Nurses, assign blocks | E1-S2 |
| Alerts: outbox messages and district alerts | E4-S2 |
| Sign in, set your password on first sign-in, role-based home | E1-S3 |
| Create account: request an account with a role; waits for approval (Account requests on Users / Staff) | beyond the backlog |
| Users (state admin): create Deputy Director accounts | E1-S1 |
| My blocks (nurse): latest alert, ranked blocks, age-specific advice | E4-S3 |
| How far to trust it: validation, plus the last season replayed month by month per district | E5-S2, MRD N6 |

Every screen shows "Risk estimate, not a diagnosis." (NF3). Levels always appear as colour plus text (NF5), and the layout works at 360 px (NF4).
