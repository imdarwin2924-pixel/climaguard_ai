"""Sign-in (E1-S1, E1-S3): password hashing, one-time passwords, sessions, lockout.

Passwords are hashed with scrypt (standard library). Sessions are random tokens sent as an HttpOnly
cookie; only their SHA-256 is stored, so a database leak does not hand out live sessions.
"""
import datetime as dt
import hashlib
import hmac
import secrets

ROLES = {"admin": "State admin", "officer": "Deputy Director", "nurse": "Village Health Nurse"}
HOME = {"admin": "users", "officer": "outlook", "nurse": "my-blocks"}  # E1-S3: where each role lands
SESSION_HOURS = 12
MAX_FAILED, LOCK_MINUTES = 5, 15
MIN_PASSWORD = 10

_N, _R, _P = 2 ** 14, 8, 1


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${digest.hex()}"


def verify_password(password, stored):
    if not stored:
        return False
    _, n, r, p, salt, digest = stored.split("$")
    check = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p))
    return hmac.compare_digest(check.hex(), digest)


def temporary_password():
    """Shown once to the person creating the account; only its hash is kept."""
    return secrets.token_urlsafe(9)


def reset_password(conn, user_id):
    """New one-time password; clears any lockout and signs the person out everywhere. Returns it, once."""
    temporary = temporary_password()
    conn.execute("UPDATE staff SET password_hash = %s, must_change_password = TRUE, failed_logins = 0, "
                 "locked_until = NULL WHERE id = %s", (hash_password(temporary), user_id))
    conn.execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))
    return temporary


def password_problem(new, current=None):
    if len(new) < MIN_PASSWORD:
        return f"Use at least {MIN_PASSWORD} characters."
    if current is not None and new == current:
        return "Choose a password different from the temporary one."
    return None


def _token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def new_session(conn, user_id):
    token = secrets.token_urlsafe(32)
    conn.execute("INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (%s, %s, now() + %s)",
                 (_token_hash(token), user_id, dt.timedelta(hours=SESSION_HOURS)))
    return token


def end_session(conn, token):
    conn.execute("DELETE FROM sessions WHERE token_hash = %s", (_token_hash(token or ""),))


def user_for_session(conn, token):
    if not token:
        return None
    row = conn.execute(
        "SELECT s.id, s.name, s.role, s.district_id, d.name, s.must_change_password, s.email, s.mobile "
        "FROM sessions x JOIN staff s ON s.id = x.user_id LEFT JOIN districts d ON d.id = s.district_id "
        "WHERE x.token_hash = %s AND x.expires_at > now() AND s.status = 'active'", (_token_hash(token),)).fetchone()
    if not row:
        return None
    keys = ["id", "name", "role", "district_id", "district", "must_change_password", "email", "mobile"]
    return dict(zip(keys, row))


def normalise_login(login):
    """Email for admins and officers (case-insensitive), 10-digit mobile for nurses."""
    login = (login or "").strip()
    return login.lower() if "@" in login else login.replace(" ", "").removeprefix("+91")


def check_login(conn, login, password):
    """-> (user_id, None) on success, (None, message) otherwise. Same message for unknown user and wrong
    password so the form does not reveal who has an account."""
    login = normalise_login(login)
    row = conn.execute("SELECT id, password_hash, locked_until > now(), status FROM staff WHERE email = %s OR mobile = %s",
                       (login, login)).fetchone()
    if row and row[2]:
        return None, f"Too many wrong attempts. Try again in {LOCK_MINUTES} minutes."
    if not row or not verify_password(password, row[1]):
        if row:
            conn.execute("UPDATE staff SET failed_logins = failed_logins + 1, "
                         "locked_until = CASE WHEN failed_logins + 1 >= %s THEN now() + %s END WHERE id = %s",
                         (MAX_FAILED, dt.timedelta(minutes=LOCK_MINUTES), row[0]))
        return None, "Wrong sign-in or password."
    conn.execute("UPDATE staff SET failed_logins = 0, locked_until = NULL WHERE id = %s", (row[0],))
    # Status is revealed only after the right password, so it does not tell strangers who has asked for an account.
    if row[3] == "pending":
        return None, "Your account request is waiting for approval."
    if row[3] == "rejected":
        return None, "Your account request was not approved. Contact your district officer or the state admin."
    return row[0], None
