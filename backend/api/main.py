"""ClimaGuard AI API. Run from backend/:  uvicorn api.main:app --reload

Every endpoint except health and sign-in needs a session (E1-S3). Roles: admin (user management),
officer (Deputy Director: map, explanations, priority, own district's staff and outbox),
nurse (own blocks only).
"""
import json
import os
import re

from fastapi import Cookie, Depends, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from climaguard import auth, index, staff
from climaguard.config import HORIZONS, RISK_ENGINE
from climaguard.db import connect
from climaguard.districts import GEOJSON
from climaguard.model import META_FILE, what_if

DISCLAIMER = "Risk estimate, not a diagnosis."  # NF3: every response carries it for every screen
COOKIE = "cg_session"
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "false").lower() == "true"  # set true behind HTTPS

app = FastAPI(title="ClimaGuard AI")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["GET", "POST"], allow_headers=["*"])


# --- Sessions and roles -------------------------------------------------------------------------

def signed_in(cg_session: str | None = Cookie(default=None)):
    with connect() as conn:
        user = auth.user_for_session(conn, cg_session)
    if not user:
        raise HTTPException(401, "Please sign in.")
    return user


def role(*allowed):
    """Dependency: a signed-in user with one of the allowed roles who has set their own password."""
    def check(user=Depends(signed_in)):
        if user["must_change_password"]:
            raise HTTPException(403, "Set a new password first.")
        if user["role"] not in allowed:
            raise HTTPException(403, "Your role cannot open this page.")
        return user
    return check


OFFICER = role("officer", "admin")
ADMIN = role("admin")
NURSE = role("nurse")


def public_user(user):
    return {"id": user["id"], "name": user["name"], "role": user["role"], "role_label": auth.ROLES[user["role"]],
            "district_id": user["district_id"], "district": user["district"],
            "must_change_password": user["must_change_password"], "home": auth.HOME[user["role"]]}


class Login(BaseModel):
    login: str
    password: str


class NewPassword(BaseModel):
    current: str
    new: str


@app.post("/api/auth/login")  # E1-S3
def login(body: Login, response: Response):
    with connect() as conn:
        user_id, error = auth.check_login(conn, body.login, body.password)
        if error:
            conn.commit()  # keep the failed-attempt count even though we raise
            raise HTTPException(429 if "Too many" in error else 403 if "request" in error else 401, error)
        token = auth.new_session(conn, user_id)
        user = auth.user_for_session(conn, token)
    response.set_cookie(COOKIE, token, httponly=True, samesite="lax", secure=COOKIE_SECURE,
                        max_age=auth.SESSION_HOURS * 3600, path="/")
    return public_user(user)


@app.post("/api/auth/logout")
def logout(response: Response, cg_session: str | None = Cookie(default=None)):
    with connect() as conn:
        auth.end_session(conn, cg_session)
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@app.get("/api/auth/me")
def me(user=Depends(signed_in)):
    return public_user(user)


@app.post("/api/auth/password")  # E1-S3: first sign-in must set a new password
def change_password(body: NewPassword, user=Depends(signed_in)):
    with connect() as conn:
        stored = conn.execute("SELECT password_hash FROM staff WHERE id = %s", (user["id"],)).fetchone()[0]
        if not auth.verify_password(body.current, stored):
            raise HTTPException(422, "Your current password is not right.")
        problem = auth.password_problem(body.new, body.current)
        if problem:
            raise HTTPException(422, problem)
        conn.execute("UPDATE staff SET password_hash = %s, must_change_password = FALSE WHERE id = %s",
                     (auth.hash_password(body.new), user["id"]))
    return public_user({**user, "must_change_password": False})


# --- Outlook (officer and admin) ---------------------------------------------------------------

def score_meaning(version):
    if version.startswith("weather-index"):
        return ("Weather suitability for dengue compared with this district's usual for this month "
                "(0 = least suitable, 1 = most suitable on record). Not a case forecast.")
    return "Probability that this district has an above-normal dengue month."


def check_horizon(horizon):
    if horizon not in HORIZONS:
        raise HTTPException(422, f"horizon must be one of {HORIZONS}")


def latest_run(conn, kind="live"):
    row = conn.execute("SELECT id, run_date, model_version, created_at FROM runs WHERE kind = %s "
                       "ORDER BY run_date DESC, id DESC LIMIT 1", (kind,)).fetchone()
    if not row:
        raise HTTPException(503, "No risk run yet: run `python -m climaguard.cli run-live`")
    return row


@app.get("/api/health")
def health():
    with connect() as conn:
        conn.execute("SELECT 1")
    return {"ok": True}


@app.get("/api/risk")  # E2-S1, E2-S2, E2-S3
def risk(horizon: int = 7, user=Depends(OFFICER)):
    check_horizon(horizon)
    with connect() as conn:
        run_id, run_date, version, created = latest_run(conn)
        rows = conn.execute(
            "SELECT d.id, d.name, r.probability, r.level FROM risk r JOIN districts d ON d.id = r.district_id "
            "WHERE r.run_id = %s AND r.horizon = %s ORDER BY d.name", (run_id, horizon)).fetchall()
    districts = [{"id": i, "name": n, "score": round(p, 3), "level": lvl} for i, n, p, lvl in rows]
    attention = sorted((d for d in districts if d["level"] in ("High", "Very high")),
                       key=lambda d: d["score"], reverse=True)
    return {"run_date": run_date, "computed_at": created, "model_version": version, "horizon": horizon,
            "score_meaning": score_meaning(version),
            "title": f"Dengue outlook, next {horizon} days", "disclaimer": DISCLAIMER,
            "districts": districts, "needs_attention": attention,
            "needs_attention_empty_text": "No districts need attention this week"}


@app.get("/api/districts/{district_id}")  # E3-S1, E3-S2
def district(district_id: int, horizon: int = 7, user=Depends(OFFICER)):
    check_horizon(horizon)
    with connect() as conn:
        run_id, run_date, version, _ = latest_run(conn)
        row = conn.execute(
            "SELECT d.name, r.probability, r.level, r.drivers FROM risk r JOIN districts d ON d.id = r.district_id "
            "WHERE r.run_id = %s AND r.district_id = %s AND r.horizon = %s", (run_id, district_id, horizon)).fetchone()
        alerts = conn.execute("SELECT reason, created_at FROM district_alerts WHERE district_id = %s AND horizon = %s "
                              "ORDER BY created_at DESC LIMIT 5", (district_id, horizon)).fetchall()
    if not row:
        raise HTTPException(404, "Unknown district")
    name, p, level, drivers = row
    return {"id": district_id, "name": name, "run_date": run_date, "horizon": horizon, "score": round(p, 3),
            "score_meaning": score_meaning(version),
            "level": level, "drivers": [{k: v for k, v in c.items() if k != "contribution"} for c in drivers],
            "recent_alerts": [{"reason": r, "at": t} for r, t in alerts], "disclaimer": DISCLAIMER}


@app.get("/api/districts/{district_id}/priority")  # E4-S1
def priority(district_id: int, horizon: int = 7, user=Depends(OFFICER)):
    check_horizon(horizon)
    with connect() as conn:
        run_id, run_date, _, _ = latest_run(conn)
        row = conn.execute("SELECT d.name, r.probability, r.level FROM risk r JOIN districts d ON d.id = r.district_id "
                           "WHERE r.run_id = %s AND r.district_id = %s AND r.horizon = %s",
                           (run_id, district_id, horizon)).fetchone()
        if not row:
            raise HTTPException(404, "Unknown district")
        name, score, level = row
        units = [] if level not in ("High", "Very high") else conn.execute(
            "SELECT name, vulnerability, population, density, child_share, past_outbreaks, factor_pct, actions "
            "FROM blocks WHERE district_id = %s ORDER BY vulnerability DESC, population DESC", (district_id,)).fetchall()
    base = {"district": name, "level": level, "horizon": horizon, "run_date": run_date, "disclaimer": DISCLAIMER,
            "unit": "Census 2011 sub-district (taluk)",
            "method": "Priority = district score × vulnerability. Vulnerability = equal mix of population density, "
                      "share of children 0–6 and past dengue outbreaks, ranked within the district."}
    if level not in ("High", "Very high"):
        return {**base, "units": [], "message": f"No priority list: {name} is {level}, below High."}
    return {**base, "message": None, "units": [
        {"rank": i + 1, "name": n, "priority": round(score * v, 3), "vulnerability": round(v, 3), "population": pop,
         "density_per_km2": round(dens), "children_0_6_pct": round(child * 100, 1), "past_outbreaks": past,
         "factor_pct": pct, "actions": acts}
        for i, (n, v, pop, dens, child, past, pct, acts) in enumerate(units)]}


@app.get("/api/districts/{district_id}/whatif")  # E5-S1
def whatif(district_id: int, horizon: int = 7, rain: int = 0, humidity: int = 0, user=Depends(OFFICER)):
    check_horizon(horizon)
    if not (-50 <= rain <= 50 and -50 <= humidity <= 50):
        raise HTTPException(422, "Rainfall and humidity changes must be between -50% and +50%.")
    with connect() as conn:
        _, run_date, _, _ = latest_run(conn)
    try:
        result = what_if(district_id, run_date, horizon, rain, humidity)
    except RuntimeError as e:
        raise HTTPException(404, str(e))
    changed = rain != 0 or humidity != 0
    return {**result, "district_id": district_id, "horizon": horizon, "rain_pct": rain, "humidity_pct": humidity,
            "label": "Scenario, not forecast" if changed else "Forecast",
            "note": f"Only the {result['forecast_days_changed']} forecast days up to the target date change; observed "
                    "weather stays as it was. Rain mostly affects breeding sites 3–8 weeks later, so a wetter forecast "
                    "moves this outlook less than it will move later ones.",
            "disclaimer": DISCLAIMER}


@app.get("/api/alerts")  # E4-S2: district alerts across the state
def alerts(limit: int = Query(50, le=500), user=Depends(OFFICER)):
    with connect() as conn:
        rows = conn.execute(
            "SELECT a.id, d.name, a.horizon, a.reason, a.created_at, r.run_date FROM district_alerts a "
            "JOIN districts d ON d.id = a.district_id JOIN runs r ON r.id = a.run_id "
            "ORDER BY a.created_at DESC LIMIT %s", (limit,)).fetchall()
    return {"alerts": [{"id": i, "district": n, "horizon": h, "reason": rs, "created_at": c, "run_date": rd}
                       for i, n, h, rs, c, rd in rows], "disclaimer": DISCLAIMER}


@app.get("/api/backtest")  # E1-S4, feeds E5-S2
def backtest(user=Depends(OFFICER)):
    if RISK_ENGINE == "index":
        if not index.VALIDATION_FILE.exists():
            raise HTTPException(503, "Index not calibrated yet")
        return {**json.loads(index.VALIDATION_FILE.read_text()), "disclaimer": DISCLAIMER}
    if not META_FILE.exists():
        raise HTTPException(503, "Model not trained yet")
    meta = json.loads(META_FILE.read_text())
    return {"model_version": meta["version"], **meta["backtest"], "disclaimer": DISCLAIMER}


@app.get("/api/feedback")  # E5-S2: last complete season, outlook vs reported outbreaks, month by month
def feedback(district_id: int | None = None, user=Depends(OFFICER)):
    if RISK_ENGINE != "index" or not index.FEEDBACK_FILE.exists():
        raise HTTPException(503, "No season replay yet: run `python -m climaguard.cli calibrate-index`")
    fb = json.loads(index.FEEDBACK_FILE.read_text())
    district_id = district_id or user["district_id"] or min(fb["districts"], key=lambda k: fb["districts"][k]["name"])
    chosen = fb["districts"].get(str(district_id))
    if not chosen:
        raise HTTPException(404, "Unknown district")
    return {"season": fb["season"], "against": fb["against"], "engine": fb["engine"], "state": fb["state"],
            "district_id": int(district_id), "district": chosen,
            "districts": sorted(({"id": int(k), "name": v["name"]} for k, v in fb["districts"].items()), key=lambda d: d["name"]),
            "disclaimer": DISCLAIMER}


@app.get("/api/geo/districts")
def geo_districts(user=Depends(OFFICER)):
    return FileResponse(GEOJSON, media_type="application/geo+json")


# --- Accounts: admin creates officers (E1-S1), officers create nurses (E1-S2) -------------------

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class NewOfficer(BaseModel):
    name: str
    email: str
    district_id: int


class NewStaff(BaseModel):
    name: str
    mobile: str
    block_ids: list[int]


@app.get("/api/districts")
def district_list(user=Depends(ADMIN)):
    with connect() as conn:
        return {"districts": [{"id": i, "name": n} for i, n in conn.execute("SELECT id, name FROM districts ORDER BY name")]}


@app.get("/api/users")  # E1-S1: user list with role and district
def users(user=Depends(ADMIN)):
    with connect() as conn:
        rows = conn.execute("SELECT s.id, s.name, s.role, s.email, s.mobile, d.name, s.must_change_password "
                            "FROM staff s LEFT JOIN districts d ON d.id = s.district_id WHERE s.status = 'active' "
                            "ORDER BY s.role, d.name NULLS FIRST, s.name").fetchall()
    return {"users": [{"id": i, "name": n, "role": auth.ROLES[r], "sign_in": e or ("••••••" + m[-4:] if m else ""),
                       "district": d, "password_set": not must, "can_reset": r != "nurse" and i != user["id"]}
                      for i, n, r, e, m, d, must in rows]}


@app.post("/api/users", status_code=201)  # E1-S1
def create_officer(body: NewOfficer, user=Depends(ADMIN)):
    name, email = re.sub(r"\s+", " ", body.name).strip(), body.email.strip().lower()
    if not name:
        raise HTTPException(422, "Enter the officer's name.")
    if not EMAIL_RE.match(email):
        raise HTTPException(422, "Enter a valid official email.")
    temporary = auth.temporary_password()
    with connect() as conn:
        if not conn.execute("SELECT 1 FROM districts WHERE id = %s", (body.district_id,)).fetchone():
            raise HTTPException(422, "Choose a district.")
        if conn.execute("SELECT 1 FROM staff WHERE email = %s", (email,)).fetchone():
            raise HTTPException(409, "An account with this email already exists")
        new_id = conn.execute("INSERT INTO staff (name, email, role, district_id, password_hash) "
                              "VALUES (%s, %s, 'officer', %s, %s) RETURNING id",
                              (name, email, body.district_id, auth.hash_password(temporary))).fetchone()[0]
    # The only time the temporary password exists in plain text; it is not stored or logged.
    return {"id": new_id, "name": name, "role": auth.ROLES["officer"], "temporary_password": temporary}


@app.post("/api/users/{user_id}/reset")  # admin resets a Deputy Director or another admin
def reset_user(user_id: int, user=Depends(ADMIN)):
    if user_id == user["id"]:
        raise HTTPException(422, "You cannot reset your own account; ask another admin.")
    with connect() as conn:
        row = conn.execute("SELECT name, role, email FROM staff WHERE id = %s", (user_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Unknown user")
        if row[1] == "nurse":
            raise HTTPException(403, "Nurses are reset by their district officer.")
        temporary = auth.reset_password(conn, user_id)
    return {"id": user_id, "name": row[0], "sign_in": row[2], "temporary_password": temporary}


# --- Self sign-up from the sign-in page: saved as a pending request until approved -----------------

class SignUp(BaseModel):
    name: str
    role: str
    password: str
    email: str | None = None
    mobile: str | None = None
    district_id: int | None = None
    block_ids: list[int] = []


@app.get("/api/public/districts")  # sign-up form: no session needed
def public_districts():
    with connect() as conn:
        return {"districts": [{"id": i, "name": n} for i, n in conn.execute("SELECT id, name FROM districts ORDER BY name")]}


@app.get("/api/public/blocks")  # sign-up form: blocks of the chosen district, for nurses
def public_blocks(district_id: int):
    with connect() as conn:
        rows = conn.execute("SELECT id, name FROM blocks WHERE district_id = %s ORDER BY name", (district_id,)).fetchall()
    return {"blocks": [{"id": i, "name": n} for i, n in rows]}


@app.post("/api/signup", status_code=201)
def signup(body: SignUp):
    if body.role not in auth.ROLES:
        raise HTTPException(422, "Choose a role.")
    name = re.sub(r"\s+", " ", body.name).strip()
    problem = auth.password_problem(body.password)
    if problem:
        raise HTTPException(422, problem)
    with connect() as conn:
        # A rejected request may be made again: clear it so its email or mobile is free.
        login = body.email.strip().lower() if body.role != "nurse" and body.email else re.sub(r"[\s-]", "", body.mobile or "").removeprefix("+91")
        conn.execute("DELETE FROM staff WHERE status = 'rejected' AND (email = %s OR mobile = %s)", (login, login))
        if body.role == "nurse":
            if not body.district_id:
                raise HTTPException(422, "Choose your district.")
            district_blocks = [r[0] for r in conn.execute("SELECT id FROM blocks WHERE district_id = %s", (body.district_id,))]
            mobiles = {r[0] for r in conn.execute("SELECT mobile FROM staff WHERE mobile IS NOT NULL")}
            try:
                name, mobile = staff.validate(name, body.mobile, body.district_id, body.block_ids, district_blocks, mobiles)
            except staff.StaffError as e:
                raise HTTPException(409 if "already registered" in str(e) else 422, str(e))
            email = None
        else:
            if not name:
                raise HTTPException(422, "Enter your name.")
            email, mobile = (body.email or "").strip().lower(), None
            if not EMAIL_RE.match(email):
                raise HTTPException(422, "Enter a valid official email.")
            if conn.execute("SELECT 1 FROM staff WHERE email = %s", (email,)).fetchone():
                raise HTTPException(409, "An account with this email already exists")
            if body.role == "officer" and not conn.execute("SELECT 1 FROM districts WHERE id = %s", (body.district_id,)).fetchone():
                raise HTTPException(422, "Choose your district.")
        district_id = None if body.role == "admin" else body.district_id
        new_id = conn.execute(
            "INSERT INTO staff (name, email, mobile, role, district_id, password_hash, must_change_password, status, requested_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, FALSE, 'pending', now()) RETURNING id",
            (name, email, mobile, body.role, district_id, auth.hash_password(body.password))).fetchone()[0]
        if body.role == "nurse":
            conn.cursor().executemany("INSERT INTO staff_blocks (staff_id, block_id) VALUES (%s, %s)",
                                      [(new_id, b) for b in sorted(set(body.block_ids))])
    approver = "your district officer" if body.role == "nurse" else "the state admin"
    return {"id": new_id, "status": "pending",
            "message": f"Request sent. You can sign in once {approver} approves it."}


def _requests_for(conn, user):
    """Pending requests this user may decide: the admin sees all, an officer sees nurses of their district."""
    where, params = ("TRUE", ()) if user["role"] == "admin" else ("s.role = 'nurse' AND s.district_id = %s", (user["district_id"],))
    return conn.execute(
        "SELECT s.id, s.name, s.role, COALESCE(s.email, s.mobile), d.name, s.requested_at, "
        "  COALESCE(array_agg(b.name ORDER BY b.name) FILTER (WHERE b.id IS NOT NULL), '{}') "
        "FROM staff s LEFT JOIN districts d ON d.id = s.district_id "
        "LEFT JOIN staff_blocks sb ON sb.staff_id = s.id LEFT JOIN blocks b ON b.id = sb.block_id "
        f"WHERE s.status = 'pending' AND {where} GROUP BY s.id, d.name ORDER BY s.requested_at", params).fetchall()


@app.get("/api/requests")
def account_requests(user=Depends(OFFICER)):
    with connect() as conn:
        rows = _requests_for(conn, user)
    return {"requests": [{"id": i, "name": n, "role": auth.ROLES[r], "sign_in": login, "district": d,
                          "requested_at": at, "blocks": b} for i, n, r, login, d, at, b in rows]}


@app.post("/api/requests/{request_id}/{decision}")
def decide_request(request_id: int, decision: str, user=Depends(OFFICER)):
    if decision not in ("approve", "reject"):
        raise HTTPException(404, "Unknown action")
    with connect() as conn:
        if request_id not in {r[0] for r in _requests_for(conn, user)}:
            raise HTTPException(404, "No pending request with this ID that you can decide.")
        conn.execute("UPDATE staff SET status = %s, decided_by = %s WHERE id = %s",
                     ("active" if decision == "approve" else "rejected", user["id"], request_id))
    return {"id": request_id, "status": "active" if decision == "approve" else "rejected"}


def own_district(user):
    if user["role"] != "officer":
        raise HTTPException(403, "Only a district officer manages field staff.")
    return user["district_id"]


@app.get("/api/blocks")  # E1-S2: the block picker lists only the officer's district
def blocks(user=Depends(OFFICER)):
    with connect() as conn:
        rows = conn.execute("SELECT id, name, population FROM blocks WHERE district_id = %s ORDER BY name",
                            (own_district(user),)).fetchall()
    return {"district": user["district"], "blocks": [{"id": i, "name": n, "population": p} for i, n, p in rows]}


@app.get("/api/staff")  # E1-S2: nurses in the officer's district
def list_staff(user=Depends(OFFICER)):
    with connect() as conn:
        rows = conn.execute(
            "SELECT s.id, s.name, s.mobile, s.must_change_password, "
            "  COALESCE(array_agg(b.name ORDER BY b.name) FILTER (WHERE b.id IS NOT NULL), '{}') "
            "FROM staff s LEFT JOIN staff_blocks sb ON sb.staff_id = s.id LEFT JOIN blocks b ON b.id = sb.block_id "
            "WHERE s.role = 'nurse' AND s.status = 'active' AND s.district_id = %s GROUP BY s.id ORDER BY s.name",
            (own_district(user),)).fetchall()
    return {"staff": [{"id": i, "name": n, "mobile": "••••••" + m[-4:], "password_set": not must, "blocks": b}
                      for i, n, m, must, b in rows]}


@app.post("/api/staff", status_code=201)  # E1-S2: always in the officer's own district
def create_staff(body: NewStaff, user=Depends(OFFICER)):
    district_id = own_district(user)
    temporary = auth.temporary_password()
    with connect() as conn:
        district_blocks = [r[0] for r in conn.execute("SELECT id FROM blocks WHERE district_id = %s", (district_id,))]
        mobiles = {r[0] for r in conn.execute("SELECT mobile FROM staff WHERE mobile IS NOT NULL")}
        try:
            name, mobile = staff.validate(body.name, body.mobile, district_id, body.block_ids, district_blocks, mobiles)
        except staff.StaffError as e:
            raise HTTPException(409 if "already registered" in str(e) else 422, str(e))
        staff_id = conn.execute("INSERT INTO staff (name, mobile, role, district_id, password_hash) "
                                "VALUES (%s, %s, 'nurse', %s, %s) RETURNING id",
                                (name, mobile, district_id, auth.hash_password(temporary))).fetchone()[0]
        conn.cursor().executemany("INSERT INTO staff_blocks (staff_id, block_id) VALUES (%s, %s)",
                                  [(staff_id, b) for b in sorted(set(body.block_ids))])
    return {"id": staff_id, "name": name, "temporary_password": temporary}


@app.post("/api/staff/{staff_id}/reset")  # officer resets a nurse in their own district
def reset_staff(staff_id: int, user=Depends(OFFICER)):
    district_id = own_district(user)
    with connect() as conn:
        row = conn.execute("SELECT name, mobile FROM staff WHERE id = %s AND role = 'nurse' AND district_id = %s",
                           (staff_id, district_id)).fetchone()
        if not row:
            raise HTTPException(404, "No nurse with this ID in your district.")
        temporary = auth.reset_password(conn, staff_id)
    return {"id": staff_id, "name": row[0], "sign_in": row[1], "temporary_password": temporary}


@app.get("/api/outbox")  # E4-S2: an officer sees their district's messages, the admin sees all
def outbox(limit: int = Query(100, le=500), user=Depends(OFFICER)):
    district_id = user["district_id"] if user["role"] == "officer" else None
    with connect() as conn:
        rows = conn.execute(
            "SELECT o.id, s.name, b.name, o.horizon, o.message, o.created_at FROM outbox o "
            "JOIN staff s ON s.id = o.staff_id JOIN blocks b ON b.id = o.block_id "
            "WHERE %(d)s::int IS NULL OR s.district_id = %(d)s "
            "ORDER BY o.created_at DESC, o.id DESC LIMIT %(n)s", {"d": district_id, "n": limit}).fetchall()
    return {"messages": [{"id": i, "to": f"{n}, {auth.ROLES['nurse']}, {b}", "horizon": h, "message": m, "created_at": c}
                         for i, n, b, h, m, c in rows],
            "note": "Simulated SMS: messages are shown here, nothing is sent.", "disclaimer": DISCLAIMER}


# --- My blocks (nurse) -------------------------------------------------------------------------

@app.get("/api/me/blocks")  # E4-S3: only the signed-in nurse's own blocks
def my_blocks(horizon: int = 7, user=Depends(NURSE)):
    check_horizon(horizon)
    with connect() as conn:
        run_id, run_date, _, _ = latest_run(conn)
        rows = conn.execute(
            "SELECT b.name, d.name, r.level, r.probability * b.vulnerability, b.actions "
            "FROM staff_blocks sb JOIN blocks b ON b.id = sb.block_id JOIN districts d ON d.id = b.district_id "
            "JOIN risk r ON r.district_id = b.district_id AND r.run_id = %s AND r.horizon = %s "
            "WHERE sb.staff_id = %s ORDER BY 4 DESC", (run_id, horizon, user["id"])).fetchall()
        alert = conn.execute("SELECT message, created_at FROM outbox WHERE staff_id = %s "
                             "ORDER BY created_at DESC LIMIT 1", (user["id"],)).fetchone()
    priority = [{"block": b, "district": d, "level": lvl, "priority": round(p, 3), "actions": acts}
                for b, d, lvl, p, acts in rows if lvl in ("High", "Very high")]
    return {"name": user["name"], "role": auth.ROLES["nurse"], "district": user["district"], "run_date": run_date,
            "horizon": horizon, "latest_alert": {"message": alert[0], "at": alert[1]} if alert else None,
            "blocks": priority, "assigned_count": len(rows), "age_advice": staff.AGE_ADVICE,
            "empty_text": "No priority visits this week", "disclaimer": DISCLAIMER}
