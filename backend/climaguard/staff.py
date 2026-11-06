"""Field staff (E1-S2), their outbox (E4-S2) and age-specific advice (E4-S3).

Staff are entered by the district officer; nothing here is seeded. A mobile number is the only contact
detail kept, and it never appears in a message body (NF2).
"""
import re

from .blocks import sms_action

MOBILE_RE = re.compile(r"^[6-9]\d{9}$")  # Indian mobile: 10 digits starting 6-9
SMS_LIMIT = 160

# Solution doc §2 guidance cards (dengue, High). Draft text: review by a public health official before real use.
AGE_ADVICE = [
    {"group": "Children (0–12)", "advice": "Clear standing water in school grounds; full-sleeve clothing; check fever early."},
    {"group": "Adults (13–64), incl. pregnant women",
     "advice": "Weekly clean-up of water containers at home and work; repellent at dawn and dusk."},
    {"group": "Older adults (65+)", "advice": "Sleep under mosquito nets; get any fever tested early at the nearest PHC."},
]


class StaffError(ValueError):
    pass


def validate(name, mobile, district_id, block_ids, district_blocks, existing_mobiles):
    """-> cleaned (name, mobile). Raises StaffError with a message the officer can act on."""
    name = re.sub(r"\s+", " ", name or "").strip()
    mobile = re.sub(r"[\s-]", "", mobile or "").removeprefix("+91")
    if not name:
        raise StaffError("Enter the nurse's name.")
    if not MOBILE_RE.match(mobile):
        raise StaffError("Enter a 10-digit mobile number starting with 6, 7, 8 or 9.")
    if mobile in existing_mobiles:
        raise StaffError("This mobile number is already registered.")
    if not block_ids:
        raise StaffError("Choose at least one block.")
    if not set(block_ids) <= set(district_blocks):
        raise StaffError("Blocks must belong to the selected district.")
    return name, mobile


def message(level, district, horizon, block, first_action):
    """Outbox SMS: names the block and the first action; no names, numbers or patient data."""
    text = f"ClimaGuard: dengue risk {level} in {district}, next {horizon} days. Start at {block}: {sms_action(first_action)}."
    if len(text) > SMS_LIMIT:
        text = f"ClimaGuard: dengue risk {level}. Start at {block}: {sms_action(first_action)}."
    return text[:SMS_LIMIT]


def fan_out(conn, run_id):
    """E4-S2: one outbox message per nurse with blocks in a district that alerted in this run.

    A district alerting on both horizons sends one message, using the shorter (7-day) outlook.
    """
    rows = conn.execute(
        """SELECT DISTINCT ON (s.id) s.id, d.name, a.horizon, r.level, b.id, b.name, b.actions->>0
           FROM district_alerts a
           JOIN districts d ON d.id = a.district_id
           JOIN risk r ON r.run_id = a.run_id AND r.district_id = a.district_id AND r.horizon = a.horizon
           JOIN blocks b ON b.district_id = a.district_id
           JOIN staff_blocks sb ON sb.block_id = b.id
           JOIN staff s ON s.id = sb.staff_id
           WHERE a.run_id = %s AND s.status = 'active'
           ORDER BY s.id, a.horizon, b.vulnerability DESC""", (run_id,)).fetchall()
    for staff_id, district, horizon, level, block_id, block, first_action in rows:
        conn.execute("INSERT INTO outbox (run_id, staff_id, block_id, horizon, message) VALUES (%s, %s, %s, %s, %s)",
                     (run_id, staff_id, block_id, horizon, message(level, district, horizon, block, first_action)))
    return len(rows)
