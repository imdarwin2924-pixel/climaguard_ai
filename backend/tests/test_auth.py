"""E1-S1, E1-S2, E1-S3 on a throwaway database: accounts, sign-in, roles, first-password change."""
import pytest
from fastapi.testclient import TestClient

import api.main as api_main
from climaguard import auth, db


def test_password_hash_roundtrip_and_never_plain():
    stored = auth.hash_password("correct horse")
    assert "correct horse" not in stored and stored.startswith("scrypt$")
    assert auth.verify_password("correct horse", stored)
    assert not auth.verify_password("wrong", stored)
    assert auth.hash_password("correct horse") != stored          # salted


def test_password_rules():
    assert auth.password_problem("short")
    assert auth.password_problem("same-as-temp-1", current="same-as-temp-1")
    assert auth.password_problem("a-good-new-password", current="tmp") is None


@pytest.fixture
def world(make_user):
    """Two districts with one block each, a signed-out client, and a state admin."""
    with db.connect() as conn:
        conn.execute("INSERT INTO districts (id, name, history_of, lat, lon) VALUES (1,'Krishnagiri','Krishnagiri',0,0), "
                     "(2,'Chennai','Chennai',0,0)")
        conn.execute("INSERT INTO blocks (id, sdt_code, name, district_id, population, density, child_share, "
                     "past_outbreaks, vulnerability, factor_pct, actions) VALUES "
                     "(10, 1, 'Hosur', 1, 1, 1, .1, 0, .5, '{}', '[\"Check stored water in every house\"]'), "
                     "(20, 2, 'Chennai', 2, 1, 1, .1, 0, .5, '{}', '[\"Check stored water in every house\"]')")
        run = conn.execute("INSERT INTO runs (run_date, kind, model_version) VALUES (now(), 'live', 't') RETURNING id").fetchone()[0]
        conn.execute("INSERT INTO risk VALUES (%s,1,7,.9,'Very high','[]'), (%s,2,7,.1,'Low','[]')", (run, run))
    make_user("admin", "admin@tn.gov.in", "admin-pass-1")
    return TestClient(api_main.app)


def sign_in(client, login, password):
    return client.post("/api/auth/login", json={"login": login, "password": password})


def test_signed_out_gets_nothing(world):
    for path in ["/api/risk", "/api/users", "/api/me/blocks", "/api/staff", "/api/outbox", "/api/geo/districts"]:
        assert world.get(path).status_code == 401, path


def test_wrong_password_gives_error_and_no_data(world):
    r = sign_in(world, "admin@tn.gov.in", "nope")
    assert r.status_code == 401 and r.json()["detail"] == "Wrong sign-in or password."
    assert sign_in(world, "nobody@tn.gov.in", "nope").json()["detail"] == "Wrong sign-in or password."  # no enumeration
    assert "cg_session" not in world.cookies
    assert world.get("/api/risk").status_code == 401


def test_lockout_after_repeated_failures(world):
    for _ in range(auth.MAX_FAILED):
        sign_in(world, "admin@tn.gov.in", "nope")
    r = sign_in(world, "admin@tn.gov.in", "admin-pass-1")       # even the right password is refused now
    assert r.status_code == 429 and "Too many" in r.json()["detail"]


def test_full_chain_admin_officer_nurse(world):
    c = world
    # Admin lands on user management (E1-S3) and creates a Deputy Director (E1-S1).
    me = sign_in(c, " Admin@TN.gov.in ", "admin-pass-1").json()
    assert me["home"] == "users"
    r = c.post("/api/users", json={"name": "Dr. S. Kavitha", "email": "dd.krishnagiri@tn.gov.in", "district_id": 1})
    assert r.status_code == 201
    officer_temp = r.json()["temporary_password"]
    listed = c.get("/api/users").json()["users"]
    assert {"name": "Dr. S. Kavitha", "role": "Deputy Director", "district": "Krishnagiri"}.items() <= next(
        u for u in listed if u["name"] == "Dr. S. Kavitha").items()
    with db.connect() as conn:
        stored = conn.execute("SELECT password_hash FROM staff WHERE email = 'dd.krishnagiri@tn.gov.in'").fetchone()[0]
    assert officer_temp not in stored                              # temporary password never stored in plain text
    dup = c.post("/api/users", json={"name": "Other", "email": "DD.Krishnagiri@tn.gov.in", "district_id": 2})
    assert dup.status_code == 409 and dup.json()["detail"] == "An account with this email already exists"
    assert c.get("/api/risk").status_code == 200                   # admin may view the outlook
    c.post("/api/auth/logout")
    assert c.get("/api/users").status_code == 401

    # Officer: first sign-in must set a new password before anything else (E1-S3).
    me = sign_in(c, "dd.krishnagiri@tn.gov.in", officer_temp).json()
    assert me["must_change_password"] and me["home"] == "outlook"
    assert c.get("/api/risk").status_code == 403
    assert c.post("/api/auth/password", json={"current": officer_temp, "new": officer_temp}).status_code == 422
    assert c.post("/api/auth/password", json={"current": officer_temp, "new": "kavitha-new-pass"}).status_code == 200
    assert c.get("/api/risk").status_code == 200
    assert c.get("/api/users").status_code == 403                  # not an admin

    # Officer creates a nurse: only own district's blocks (E1-S2).
    assert [b["name"] for b in c.get("/api/blocks").json()["blocks"]] == ["Hosur"]
    assert c.post("/api/staff", json={"name": "R. Selvi", "mobile": "9876543210", "block_ids": [20]}).status_code == 422
    r = c.post("/api/staff", json={"name": "R. Selvi", "mobile": "9876543210", "block_ids": [10]})
    assert r.status_code == 201
    nurse_temp = r.json()["temporary_password"]
    dup = c.post("/api/staff", json={"name": "X", "mobile": "98765 43210", "block_ids": [10]})
    assert dup.status_code == 409
    c.post("/api/auth/logout")

    # Nurse signs in with her mobile, sets a password, lands on My blocks; cannot open officer pages.
    me = sign_in(c, "+91 98765 43210", nurse_temp).json()
    assert me["home"] == "my-blocks"
    c.post("/api/auth/password", json={"current": nurse_temp, "new": "selvi-new-pass-1"})
    mine = c.get("/api/me/blocks").json()
    assert [b["block"] for b in mine["blocks"]] == ["Hosur"] and mine["name"] == "R. Selvi"
    for path in ["/api/risk", "/api/staff", "/api/outbox", "/api/users", "/api/districts/1/priority"]:
        assert c.get(path).status_code == 403, path


def test_session_cookie_is_httponly_and_only_hash_stored(world):
    r = sign_in(world, "admin@tn.gov.in", "admin-pass-1")
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    token = world.cookies["cg_session"]
    with db.connect() as conn:
        assert conn.execute("SELECT count(*) FROM sessions WHERE token_hash = %s", (token,)).fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM sessions").fetchone()[0] == 1


def test_reset_rules_lockout_and_sign_out_everywhere(world, make_user):
    officer = make_user("officer", "dd@tn.gov.in", "officer-pass-1", district_id=1)
    other_officer = make_user("officer", "dd2@tn.gov.in", "officer-pass-2", district_id=2)
    nurse = make_user("nurse", "9876543210", "nurse-pass-01", district_id=1)
    far_nurse = make_user("nurse", "9876543211", "nurse-pass-02", district_id=2)

    # The nurse is signed in on her phone and has locked herself out on another device.
    phone = TestClient(api_main.app)
    sign_in(phone, "9876543210", "nurse-pass-01")
    assert phone.get("/api/me/blocks").status_code == 200
    for _ in range(auth.MAX_FAILED):
        sign_in(world, "9876543210", "forgot")

    # Her officer resets her: new one-time password, lockout cleared, old session ended.
    sign_in(world, "dd@tn.gov.in", "officer-pass-1")
    assert world.post(f"/api/staff/{far_nurse}/reset").status_code == 404          # not in this officer's district
    r = world.post(f"/api/staff/{nurse}/reset")
    assert r.status_code == 200 and r.json()["sign_in"] == "9876543210"
    temp = r.json()["temporary_password"]
    assert phone.get("/api/me/blocks").status_code == 401                         # signed out everywhere
    assert world.post(f"/api/users/{other_officer}/reset").status_code == 403     # officers cannot reset officers
    world.post("/api/auth/logout")

    me = sign_in(world, "9876543210", temp).json()
    assert me["must_change_password"]
    assert sign_in(world, "9876543210", "nurse-pass-01").status_code == 401        # old password no longer works

    # The admin resets officers, not nurses, and not themselves.
    world.post("/api/auth/logout")
    sign_in(world, "admin@tn.gov.in", "admin-pass-1")
    assert world.post(f"/api/users/{officer}/reset").status_code == 200
    assert world.post(f"/api/users/{nurse}/reset").status_code == 403
    admin_id = world.get("/api/auth/me").json()["id"]
    assert world.post(f"/api/users/{admin_id}/reset").status_code == 422


def test_self_signup_waits_for_the_right_approver(world, make_user):
    c = world
    make_user("officer", "dd@tn.gov.in", "officer-pass-1", district_id=1)
    make_user("officer", "dd2@tn.gov.in", "officer-pass-2", district_id=2)
    pub = c.get("/api/public/districts").json()["districts"]
    assert {d["name"] for d in pub} == {"Krishnagiri", "Chennai"}                  # sign-up form needs no session
    assert [b["name"] for b in c.get("/api/public/blocks", params={"district_id": 1}).json()["blocks"]] == ["Hosur"]

    # Validation
    bad = {"name": "X", "role": "nurse", "mobile": "9876500001", "district_id": 1, "block_ids": [20], "password": "nurse-pass-01"}
    assert c.post("/api/signup", json=bad).status_code == 422                       # block from another district
    assert c.post("/api/signup", json=bad | {"block_ids": [10], "password": "short"}).status_code == 422
    assert c.post("/api/signup", json={"name": "X", "role": "superuser", "password": "x" * 12}).status_code == 422
    assert c.post("/api/signup", json={"name": "X", "role": "officer", "email": "dd@tn.gov.in", "district_id": 1,
                                       "password": "x" * 12}).status_code == 409    # email taken

    # A nurse and a would-be admin ask for accounts; both are saved as pending and cannot sign in yet.
    r = c.post("/api/signup", json=bad | {"block_ids": [10], "name": "R. Selvi"})
    assert r.status_code == 201 and "district officer" in r.json()["message"]
    nurse_id = r.json()["id"]
    admin_req = c.post("/api/signup", json={"name": "Someone", "role": "admin", "email": "me@example.com",
                                            "password": "wannabe-admin-1"}).json()["id"]
    with db.connect() as conn:
        assert conn.execute("SELECT status FROM staff WHERE id = %s", (admin_req,)).fetchone()[0] == "pending"
    r = sign_in(c, "me@example.com", "wannabe-admin-1")
    assert r.status_code == 403 and "waiting for approval" in r.json()["detail"]
    assert sign_in(c, "me@example.com", "wrong-password").json()["detail"] == "Wrong sign-in or password."  # no status leak

    # The other district's officer cannot see or approve her; her own officer can.
    sign_in(c, "dd2@tn.gov.in", "officer-pass-2")
    assert c.get("/api/requests").json()["requests"] == []
    assert c.post(f"/api/requests/{nurse_id}/approve").status_code == 404
    c.post("/api/auth/logout")
    sign_in(c, "dd@tn.gov.in", "officer-pass-1")
    reqs = c.get("/api/requests").json()["requests"]
    assert [(q["name"], q["blocks"]) for q in reqs] == [("R. Selvi", ["Hosur"])]  # officers never see admin requests
    assert c.post(f"/api/requests/{admin_req}/approve").status_code == 404
    assert c.post(f"/api/requests/{nurse_id}/approve").json()["status"] == "active"
    c.post("/api/auth/logout")
    assert sign_in(c, "9876500001", "nurse-pass-01").json()["home"] == "my-blocks"  # own password, no forced change
    c.post("/api/auth/logout")

    # The admin rejects the admin request; it stays on record and cannot sign in, but may ask again.
    sign_in(c, "admin@tn.gov.in", "admin-pass-1")
    assert [q["name"] for q in c.get("/api/requests").json()["requests"]] == ["Someone"]
    assert c.post(f"/api/requests/{admin_req}/reject").json()["status"] == "rejected"
    assert "Someone" not in [u["name"] for u in c.get("/api/users").json()["users"]]
    c.post("/api/auth/logout")
    assert "not approved" in sign_in(c, "me@example.com", "wannabe-admin-1").json()["detail"]
    again = c.post("/api/signup", json={"name": "Someone", "role": "admin", "email": "me@example.com", "password": "second-try-123"})
    assert again.status_code == 201
