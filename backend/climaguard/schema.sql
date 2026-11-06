-- Aggregated, anonymised data only (NF2): no people, no patients.

CREATE TABLE IF NOT EXISTS districts (
    id          SERIAL PRIMARY KEY,
    name        TEXT UNIQUE NOT NULL,
    history_of  TEXT NOT NULL,          -- whose case history to use (itself, or parent for new districts)
    lat         DOUBLE PRECISION NOT NULL,
    lon         DOUBLE PRECISION NOT NULL,
    area_km2    DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS weather_daily (
    district_id   INT REFERENCES districts(id),
    date          DATE NOT NULL,
    temp_mean     REAL,
    humidity_mean REAL,
    precip        REAL,
    is_forecast   BOOLEAN NOT NULL DEFAULT FALSE,
    fetched_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (district_id, date)
);

-- Keyed by name, not district id, because sources use the 32 pre-2019 districts too.
CREATE TABLE IF NOT EXISTS dengue_monthly (
    district TEXT NOT NULL,
    year     INT NOT NULL,
    month    INT NOT NULL CHECK (month BETWEEN 1 AND 12),
    cases    INT NOT NULL CHECK (cases >= 0),
    outbreaks INT,                      -- IDSP outbreak reports with onset this month (NULL for case-count sources)
    source   TEXT NOT NULL,
    PRIMARY KEY (district, year, month)
);
ALTER TABLE dengue_monthly ADD COLUMN IF NOT EXISTS outbreaks INT;

CREATE TABLE IF NOT EXISTS runs (
    id            SERIAL PRIMARY KEY,
    run_date      DATE NOT NULL,
    kind          TEXT NOT NULL CHECK (kind IN ('live', 'backtest')),
    model_version TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS risk (
    run_id      INT REFERENCES runs(id) ON DELETE CASCADE,
    district_id INT REFERENCES districts(id),
    horizon     INT NOT NULL CHECK (horizon IN (7, 14)),
    probability REAL NOT NULL,
    level       TEXT NOT NULL,
    drivers     JSONB NOT NULL,
    PRIMARY KEY (run_id, district_id, horizon)
);

CREATE TABLE IF NOT EXISTS district_alerts (
    id          SERIAL PRIMARY KEY,
    run_id      INT REFERENCES runs(id) ON DELETE CASCADE,
    district_id INT REFERENCES districts(id),
    horizon     INT NOT NULL,
    reason      TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (run_id, district_id, horizon)
);

-- E4-S1: field priority units (Census 2011 sub-districts) and their vulnerability index.
CREATE TABLE IF NOT EXISTS blocks (
    id             SERIAL PRIMARY KEY,
    sdt_code       INT UNIQUE NOT NULL,
    name           TEXT NOT NULL,
    district_id    INT REFERENCES districts(id),
    population     INT NOT NULL,
    density        REAL NOT NULL,
    child_share    REAL NOT NULL,
    past_outbreaks INT NOT NULL,
    vulnerability  REAL NOT NULL,
    factor_pct     JSONB NOT NULL,
    actions        JSONB NOT NULL
);

-- E1-S2: field staff entered by the district officer. Contact detail is the mobile number only.
CREATE TABLE IF NOT EXISTS staff (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    mobile      TEXT UNIQUE NOT NULL,
    role        TEXT NOT NULL DEFAULT 'Village Health Nurse',
    district_id INT NOT NULL REFERENCES districts(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS staff_blocks (
    staff_id INT REFERENCES staff(id) ON DELETE CASCADE,
    block_id INT REFERENCES blocks(id) ON DELETE CASCADE,
    PRIMARY KEY (staff_id, block_id)
);

-- E4-S2: the message each nurse would receive (simulated SMS; nothing is sent).
CREATE TABLE IF NOT EXISTS outbox (
    id         SERIAL PRIMARY KEY,
    run_id     INT REFERENCES runs(id) ON DELETE CASCADE,
    staff_id   INT REFERENCES staff(id) ON DELETE CASCADE,
    block_id   INT REFERENCES blocks(id) ON DELETE CASCADE,
    horizon    INT NOT NULL,
    message    TEXT NOT NULL CHECK (char_length(message) <= 160),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- E1-S1/S3: staff doubles as the user table. Admins and officers sign in by email, nurses by mobile.
ALTER TABLE staff ALTER COLUMN mobile DROP NOT NULL;
ALTER TABLE staff ALTER COLUMN district_id DROP NOT NULL;      -- the state admin has no district
ALTER TABLE staff ALTER COLUMN role SET DEFAULT 'nurse';
UPDATE staff SET role = 'nurse' WHERE role = 'Village Health Nurse';
ALTER TABLE staff ADD COLUMN IF NOT EXISTS email TEXT UNIQUE;
ALTER TABLE staff ADD COLUMN IF NOT EXISTS password_hash TEXT;  -- scrypt; plain passwords are never stored
ALTER TABLE staff ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE staff ADD COLUMN IF NOT EXISTS failed_logins INT NOT NULL DEFAULT 0;
ALTER TABLE staff ADD COLUMN IF NOT EXISTS locked_until TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,                                 -- SHA-256 of the cookie token
    user_id    INT NOT NULL REFERENCES staff(id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Self sign-up from the sign-in page: requests wait as 'pending' until approved (admin: officers and admins;
-- district officer: nurses in their district). Accounts made by an admin or officer are 'active' at once.
ALTER TABLE staff ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active'
    CHECK (status IN ('pending', 'active', 'rejected'));
ALTER TABLE staff ADD COLUMN IF NOT EXISTS requested_at TIMESTAMPTZ;
ALTER TABLE staff ADD COLUMN IF NOT EXISTS decided_by INT REFERENCES staff(id) ON DELETE SET NULL;
