"""Shared configuration for the Method 2 (rolling quarterly factor) pipeline.

Everything resolves relative to this file, so the whole folder can be moved,
renamed or copied anywhere and will still run. It never reaches outside itself.

Method 2 in one line: correct QuickBooks with a credibility-weighted blend of its
recent and trailing actual/tracked ratios, then decide what - if anything - to do
with competitors.
"""

from __future__ import annotations

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
INPUT_DIR = BASE_DIR / "1. Inputs"
OUT_DIR = BASE_DIR / "3. Outputs"

ACTUALS_XLSX = INPUT_DIR / "Media Activity Template.xlsx"
ACTUALS_SHEET = "Media Activity Template"
NIELSEN_CSV = INPUT_DIR / "Updated Nielsen + AdClarity Spends.csv"
REFERENCE_XLSX = INPUT_DIR / "QuickBooks Rolling Factor & Competitor Confidence (v2).xlsx"

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

# The 15 columns of the tracker file, in order. Every dataset this pipeline
# emits leads with exactly these, so they stack and diff against each other.
TRACKER_COLUMNS = [
    "ADVERTISER", "PRODUCT", "DATE", "Q", "CHANNEL", "SOURCE",
    "SPEND", "ADJUSTED_SPEND", "RAW_CHANNEL_FACTOR", "CORRECTION_FACTOR",
    "CORRECTED_SPEND", "FACTOR_BASIS", "FACTOR_CONFIDENCE",
    "IMPRESSIONS", "PUBLISHERS",
]

PRODUCT = "QuickBooks"          # the tracked product category, not the advertiser
ADVERTISERS = ["QuickBooks", "Xero", "Sage", "Zoho", "Netsuite"]

# ---------------------------------------------------------------------------
# Channel taxonomy
# ---------------------------------------------------------------------------

# Intuit's actual-spend columns mapped onto the tracker's channel vocabulary.
# These reproduce the published deck's channel totals, which is why Demand Gen
# sits in Digital rather than Display - the deck counts it as search.
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

# Channels where Intuit holds invoices. Only these can produce a factor.
CALIBRATABLE = ["Digital", "Social", "Video", "Display"]

# ---------------------------------------------------------------------------
# Method 2 parameters
# ---------------------------------------------------------------------------

# Step 1 - fixed pre-adjustment on the above-the-line channels, applied to raw
# tracked spend before any factor. Recovered from the shipped tracker file.
OFFLINE_MULTIPLIER = {
    "TV": 0.8164,
    "Radio": 0.6963,
    "Outdoor": 0.8000,
    "Press": 1.4000,
    "Direct Mail": 1.0000,
}

# Step 2 - credibility weight. Z = n / (n + K), n being the tracked dollars
# behind the most recent completed quarter.
#
# The source workbook reports Z but does not define it, and no single K
# reproduces all 20 rows. K is fitted per channel against the workbook's Z
# column (see m2_rolling_factor.fit_credibility_k). The blend formula itself
# reproduces exactly; only the weight is reconstructed. Treat K as a documented
# assumption.
CREDIBILITY_K_DEFAULT = 500_000.0
SEED_Z = 0.80  # the first quarter has no prior, so the workbook pins Z at 0.8

# The blend requires two distinct components. It does not have them at the
# start of the series:
#
#   2025Q1  no prior quarter at all - seeded with the raw in-sample ratio
#   2025Q2  exactly one prior quarter, so last_quarter and trailing4 are the
#           SAME number. Z * x + (1 - Z) * x = x for any Z, so the credibility
#           weighting is arithmetically inert and cannot damp anything.
#
# Both quarters therefore carry QuickBooks' seed social ratio of 16.5x
# unfiltered - itself the product of a single bad tracking quarter ($106k
# tracked against $1.75m actually spent). Under the as-shipped version those
# two quarters alone generate $184.9m of Xero's $267.8m.
#
# From 2025Q3 the blend has real history and behaves: 1.79, 0.49, 0.96, 1.56.
# Output is restricted to that range. Set to None to publish everything.
ROLLING_START_Q = "2025Q3"

# Step 3 - display and video factors are unusable on their own (they run to
# 978x and 5,689x), so the method overwrites them with the Search factor.
CAPPED_CHANNELS = ["Display", "Video"]
CAP_SOURCE = "Digital"

# Window covered by the tracker file.
WINDOW_START = "2025-01-01"
WINDOW_STOP = "2026-04-30"

# ---------------------------------------------------------------------------
# Competitor treatment
# ---------------------------------------------------------------------------

# Method 2 exists in two versions and they disagree. The methodology document
# is explicit:
#
#   "we do NOT apply QuickBooks' correction factors to competitors. A factor
#    calibrated on QuickBooks' buying is not evidence about Xero's or Sage's."
#
# The existing tracker file applies them regardless; every competitor row
# reads FACTOR_BASIS = "QB-proxy". Both variants are produced so the
# difference is quantified.
#
# SCALE_COMPETITORS resolves it, one way, for the whole pipeline:
#
#   True   apply QuickBooks' factors to competitors. This is what the live
#          tracker does, and the only setting that produces competitor spend
#          figures at all - which is what the market-sizing work needs.
#   False  leave competitors at tracked spend. Methodologically cleaner, but
#          it moves Xero by 0.7%, so it is equivalent to using raw data.
#
# Set True because the deliverable requires competitor numbers. The caveat
# travels with them: every competitor figure is QuickBooks' correction applied
# to a different advertiser's buying, and should be read as an estimate.
SCALE_COMPETITORS = True

__all__ = [name for name in dir() if not name.startswith("_")]
