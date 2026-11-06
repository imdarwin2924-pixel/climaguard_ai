import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres@localhost:5432/climaguard")
DATASET_DIR = (BACKEND_DIR / os.environ.get("DATASET_DIR", "../dataset")).resolve()
MODEL_DIR = BACKEND_DIR / "models"

# PRD §4 risk levels: probability of an above-normal month.
LEVELS = [(0.25, "Low"), (0.50, "Moderate"), (0.75, "High"), (1.01, "Very high")]
HORIZONS = (7, 14)
# Index levels are on a climatology percentile, not a probability: High = top 20% for this district and
# month, Very high = top 5%. Keeps High+ rare enough that alerts mean something.
INDEX_LEVELS = [(0.50, "Low"), (0.80, "Moderate"), (0.95, "High"), (1.01, "Very high")]

# "index" = weather suitability index (no case data needed); "model" = XGBoost trained on case labels.
# The model stays off until real case counts exist: on IDSP outbreak labels it scored AUC ~0.58.
RISK_ENGINE = "index"

# Which label the model learns: "outbreak" = an IDSP dengue outbreak reported that district-month
# (free weekly source); "counts" = above-normal monthly case counts (Indiastat, subscription).
LABEL = "outbreak"

# Above-normal label for "counts" (design §0): mean + ABOVE_NORMAL_SD * sd of the other years, and at least MIN_CASES.
ABOVE_NORMAL_SD = 2.0
MIN_CASES = 5

# Days in the Aedes transmission temperature band (°C).
AEDES_BAND = (26.0, 30.0)

# Observed days fetched before today for a live run; covers the 8-week rain lag.
LIVE_PAST_DAYS = 61

SPOTLIGHT = ["Chennai", "Coimbatore", "Krishnagiri", "Madurai", "The Nilgiris"]

# Districts formed 2019-20 borrow their parent's case history (design §0).
PARENT = {
    "Chengalpattu": "Kanchipuram",
    "Ranipet": "Vellore",
    "Tirupathur": "Vellore",
    "Kallakurichi": "Villupuram",
    "Tenkasi": "Tirunelveli",
    "Mayiladuthurai": "Nagapattinam",
}
