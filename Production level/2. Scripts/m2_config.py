"""Configuration for the Method 2 rolling quarterly factor pipeline.

Method 2 corrects QuickBooks tracked spend using a credibility-weighted blend of
its recent and trailing actual/tracked ratios, then optionally applies the same
factors to competitors.

All paths resolve relative to this file. The folder is self-contained.
"""

from __future__ import annotations

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
INPUT_DIR = BASE_DIR / "1. Inputs"
OUT_DIR = BASE_DIR / "3. Outputs"

ACTUALS_XLSX = INPUT_DIR / "Media Activity Template.xlsx"
ACTUALS_SHEET = "Media Activity Template"
NIELSEN_CSV = INPUT_DIR / "Updated Nielsen + AdClarity Spends.csv"

# Not shipped. Only used to fit CREDIBILITY_K, which is now pinned below.
# Restore it to "1. Inputs" under this name to refit (fit_credibility_k).
REFERENCE_XLSX = INPUT_DIR / "QuickBooks Rolling Factor & Competitor Confidence (v2).xlsx"

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

# Tracker column order. All emitted datasets use these columns so they stack.
TRACKER_COLUMNS = [
    "ADVERTISER", "PRODUCT", "DATE", "Q", "CHANNEL", "SOURCE",
    "SPEND", "ADJUSTED_SPEND", "RAW_CHANNEL_FACTOR", "CORRECTION_FACTOR",
    "CORRECTED_SPEND", "FACTOR_BASIS", "FACTOR_CONFIDENCE",
    "IMPRESSIONS", "PUBLISHERS",
]

PRODUCT = "QuickBooks"          # product category, not the advertiser
ADVERTISERS = ["QuickBooks", "Xero", "Sage", "Zoho", "Netsuite"]

# ---------------------------------------------------------------------------
# Channel taxonomy
# ---------------------------------------------------------------------------

# Actual-spend columns mapped to tracker channels. Matches the published deck's
# channel totals; Demand Gen sits in Digital because the deck counts it there.
ACTUAL_TO_TRACKER = {
    "App Search": "Digital",
    "Paid Search": "Digital",
    "PerformanceMax": "Digital",
    "Demand Gen": "Digital",
    "Paid Social": "Social",
    "OLV": "Video",
    "Youtube": "Video",
    "Video OLV": "Video",
    "Display": "Display",
    "null": "Unclassified",
}

# The template has an unlabelled column containing spend. It is retained but
# maps to no tracker channel, so it is excluded from all factor calculations.
UNCLASSIFIED = "Unclassified"

ONLINE_CHANNELS = {"Digital", "Display", "Social", "Video"}
OFFLINE_CHANNELS = {"TV", "Radio", "Outdoor", "Press", "Direct Mail"}

# Channels with invoiced actuals. Only these can produce a factor.
CALIBRATABLE = ["Digital", "Social", "Video", "Display"]

# ---------------------------------------------------------------------------
# Method 2 parameters
# ---------------------------------------------------------------------------

# Fixed pre-adjustment for above-the-line channels, applied to tracked spend
# before any factor. Values taken from the existing tracker file.
OFFLINE_MULTIPLIER = {
    "TV": 0.8164,
    "Radio": 0.6963,
    "Outdoor": 0.8000,
    "Press": 1.4000,
    "Direct Mail": 1.0000,
}

# Credibility weight: Z = n / (n + K), where n is tracked spend in the most
# recent completed quarter.
#
# The source workbook reports Z but does not define it, and no single K
# reproduces all 20 rows. K is therefore fitted per channel against the
# workbook's Z column. The blend formula itself reproduces exactly; only the
# weight is reconstructed. Treat K as a documented assumption.
CREDIBILITY_K_DEFAULT = 500_000.0
SEED_Z = 0.80  # first quarter has no prior; workbook pins Z at 0.8

# Tracked spend at which a quarter earns half credibility, per channel. Low K
# favours the recent quarter, high K favours the trailing average.
#
# Pinned so the pipeline reproduces without REFERENCE_XLSX. Editable, but note
# the sensitivity: reverting to the 500,000 default moves Social by up to 94%
# in a low-volume quarter, while Digital, Display and Video move under 3%.
CREDIBILITY_K = {
    "Digital": 589_993.77,
    "Social": 1_835_627.72,
    "Video": 35_842.18,
    "Display": 2_826.00,
}

# The blend requires two distinct components. The first two quarters of any
# series cannot provide them:
#
#   quarter 1  no prior quarter; seeded with the in-sample ratio
#   quarter 2  one prior quarter, so last_quarter == trailing4. Since
#              Z * x + (1 - Z) * x = x for any Z, the weighting has no effect
#              and cannot damp an outlier.
#
# On the original series both quarters carried a 16.5x social seed ratio from a
# quarter with $106k tracked against $1.75m spent, which generated $184.9m of
# Xero's $267.8m total. Those quarters are dropped.
ROLLING_START_Q_OVERRIDE = None   # set e.g. "2025Q3" to pin manually
INERT_SEED_QUARTERS = 2           # leading quarters to drop

# Display and Video factors are not usable on their own volumes (978x and
# 5,689x on the original series), so both are overwritten with the Search
# factor.
CAPPED_CHANNELS = ["Display", "Video"]
CAP_SOURCE = "Digital"

# Date window. Derived from the tracker file, so a different input needs no
# edit here. Set the overrides to report on less than the data covers.
WINDOW_START_OVERRIDE = None      # e.g. "2025-01-01"
WINDOW_STOP_OVERRIDE = None       # e.g. "2026-04-30"


def _tracker_dates():
    """Sorted dates from the tracker file, or None if it cannot be read."""
    import pandas as pd
    try:
        dates = pd.to_datetime(pd.read_csv(NIELSEN_CSV, usecols=["DATE"]).DATE)
        return dates.dropna().sort_values()
    except Exception:
        return None


_dates = _tracker_dates()

if _dates is None or _dates.empty:
    # Tracker file missing or unreadable. Fall back to the original window
    # rather than raising at import time.
    WINDOW_START, WINDOW_STOP = "2025-01-01", "2026-04-30"
    ROLLING_START_Q = "2025Q3"
else:
    import pandas as _pd
    WINDOW_START = WINDOW_START_OVERRIDE or _dates.min().strftime("%Y-%m-%d")
    WINDOW_STOP = WINDOW_STOP_OVERRIDE or (
        _dates.max() + _pd.offsets.MonthEnd(0)).strftime("%Y-%m-%d")

    _quarters = sorted(set(_pd.PeriodIndex(_dates, freq="Q").astype(str)))
    ROLLING_START_Q = ROLLING_START_Q_OVERRIDE or (
        _quarters[INERT_SEED_QUARTERS]
        if len(_quarters) > INERT_SEED_QUARTERS else None)

# ---------------------------------------------------------------------------
# Competitor treatment
# ---------------------------------------------------------------------------

# The methodology document states that QuickBooks' correction factors should not
# be applied to competitors, on the grounds that a factor calibrated on
# QuickBooks' buying is not evidence about Xero's or Sage's. The existing
# tracker file applies them regardless (competitor rows read FACTOR_BASIS =
# "QB-proxy").
#
#   True   apply the factors to competitors. Matches the existing tracker and
#          is the only setting that produces competitor spend figures.
#   False  leave competitors at tracked spend. Cleaner methodologically, but it
#          moves Xero by 0.7%, so the result is effectively the raw feed.
#
# Set True because the deliverable requires competitor figures. Those figures
# are estimates: one advertiser's measured correction applied to another
# advertiser's buying.
SCALE_COMPETITORS = True

__all__ = [name for name in dir() if not name.startswith("_")]
