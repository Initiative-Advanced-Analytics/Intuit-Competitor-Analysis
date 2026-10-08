"""Apply Method 2 and write the consolidated output dataset.

Emits:

  Method 2 - Actuals vs Reported vs Adjusted.csv

one row per advertiser, month and channel, carrying ACTUAL_SPEND,
REPORTED_SPEND and ADJUSTED_SPEND on the tracker's 15-column schema.

Competitor handling is controlled by SCALE_COMPETITORS in m2_config.

Channels present in the invoices but absent from the tracker feed are carried
into the QuickBooks rows so its total is complete. These are search, which the
trackers report as $0 for every advertiser, and the template's unlabelled
column.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import m2_config as C
import m2_rolling_factor as RF
import stack_actuals


# ---------------------------------------------------------------------------
# Step 1 - offline pre-adjustment
# ---------------------------------------------------------------------------

def pre_adjust(frame: pd.DataFrame) -> pd.DataFrame:
    """Apply fixed offline multipliers to tracked spend, before any factor."""
    out = frame.copy()
    out["ADJUSTED_SPEND"] = out.apply(
        lambda r: r.SPEND * C.OFFLINE_MULTIPLIER.get(r.CHANNEL, 1.0), axis=1
    )
    # Search tracked spend is $0, so retain the tracker's imputed search line
    # rather than multiplying it to zero.
    blind = out.CHANNEL == C.CAP_SOURCE
    out.loc[blind, "ADJUSTED_SPEND"] = frame.loc[blind, "ADJUSTED_SPEND"]
    return out


# ---------------------------------------------------------------------------
# Step 2 - apply the rolling factor
# ---------------------------------------------------------------------------

def _factor_lookup(factors: pd.DataFrame) -> dict[tuple[str, str], dict]:
    return {
        (r.Q, r.Channel): {
            "factor": r.blended_factor,
            "uncapped": r.uncapped_factor,
            "capped": r.capped,
            "basis": r.basis,
        }
        for _, r in factors.iterrows()
    }


def apply_method_2(nielsen: pd.DataFrame, factors: pd.DataFrame,
                   scale_competitors: bool) -> pd.DataFrame:
    """Apply Method 2 to every row. scale_competitors selects the variant."""
    out = pre_adjust(nielsen)
    lookup = _factor_lookup(factors)

    raw_f, corr_f, corrected, basis, confidence = [], [], [], [], []

    for _, row in out.iterrows():
        is_qb = row.ADVERTISER == "QuickBooks"
        entry = lookup.get((row.Q, row.CHANNEL))

        if row.CHANNEL in C.OFFLINE_CHANNELS:
            multiplier = C.OFFLINE_MULTIPLIER.get(row.CHANNEL, 1.0)
            raw_f.append(1.0); corr_f.append(1.0)
            corrected.append(row.ADJUSTED_SPEND)
            basis.append(f"above-the-line | rate-card adjustment {multiplier:.4f}x")
            confidence.append("medium (Nielsen tracks above-the-line well)")
            continue

        if entry is None or pd.isna(entry["factor"]):
            raw_f.append(np.nan); corr_f.append(np.nan)
            corrected.append(row.ADJUSTED_SPEND)
            basis.append("no factor estimable for this channel-quarter")
            confidence.append("none")
            continue

        if not is_qb and not scale_competitors:
            raw_f.append(entry["uncapped"]); corr_f.append(np.nan)
            corrected.append(row.ADJUSTED_SPEND)
            basis.append(
                "competitor | NOT scaled - QuickBooks' factor is not evidence "
                "about this advertiser (see methodology s.6)"
            )
            confidence.append("floor (tracked spend, uncorrected)")
            continue

        factor = float(entry["factor"])
        raw_f.append(entry["uncapped"]); corr_f.append(factor)
        corrected.append(row.ADJUSTED_SPEND * factor)
        anchor = "QB ground-truth" if is_qb else "QB-proxy"
        basis.append(f"{anchor} | {entry['basis']}")
        confidence.append(
            "low (capped - no credible Display/Video volume)" if entry["capped"]
            else ("high" if is_qb else "low (factor borrowed from QuickBooks)")
        )

    out["RAW_CHANNEL_FACTOR"] = raw_f
    out["CORRECTION_FACTOR"] = corr_f
    out["CORRECTED_SPEND"] = corrected
    out["FACTOR_BASIS"] = basis
    out["FACTOR_CONFIDENCE"] = confidence
    return out[C.TRACKER_COLUMNS]


# ---------------------------------------------------------------------------
# Step 3 - restore the channels the tracker cannot see
# ---------------------------------------------------------------------------

def add_actual_only_channels(adjusted: pd.DataFrame,
                             stacked: pd.DataFrame) -> pd.DataFrame:
    """Add QuickBooks channels that exist only in the invoices.

    Two cases, both spend the tracker feed cannot account for:

      Unclassified  the template's unlabelled column, which has no tracker
                    channel equivalent
      Digital       the tracker carries the channel but reports $0 every month,
                    so QuickBooks' corrected search level is replaced with the
                    invoiced figure

    Neither applies to competitors, since no competitor invoices exist. Their
    search remains at the imputed level and their totals should be read as
    floors.
    """
    window = stacked[
        (stacked.DATE >= C.WINDOW_START) & (stacked.DATE <= C.WINDOW_STOP)
    ].copy()

    out = adjusted.copy()

    # Replace QuickBooks' modelled search with the invoiced figure.
    invoiced = (
        window[window.CHANNEL == C.CAP_SOURCE]
        .groupby("DATE").SPEND.sum()
    )
    mask = (out.ADVERTISER == "QuickBooks") & (out.CHANNEL == C.CAP_SOURCE)
    covered = set()
    for index in out[mask].index:
        date = out.at[index, "DATE"]
        if date in invoiced.index:
            out.at[index, "CORRECTED_SPEND"] = float(invoiced[date])
            out.at[index, "FACTOR_BASIS"] = (
                "QB invoiced | invoiced actual replaces the modelled "
                "search estimate"
            )
            out.at[index, "FACTOR_CONFIDENCE"] = "invoiced"
            out.at[index, "CORRECTION_FACTOR"] = np.nan
            covered.add(date)

    # The tracker does not carry a row for every month. Where a month of
    # invoiced search has no tracker row at all, it must be appended rather
    # than quietly lost - 2026-02 alone is $724,083, and the published
    # workbook's Search line drops it for exactly this reason.
    orphaned = invoiced[~invoiced.index.isin(covered)]
    if not orphaned.empty:
        gap = pd.DataFrame({
            "DATE": orphaned.index,
            "SPEND": 0.0,
            "CORRECTED_SPEND": orphaned.to_numpy(dtype=float),
        })
        gap["Q"] = (
            pd.to_datetime(gap.DATE).dt.to_period("Q").astype(str)
        )
        gap["CHANNEL"] = C.CAP_SOURCE
        gap["ADVERTISER"] = "QuickBooks"
        gap["PRODUCT"] = C.PRODUCT
        gap["SOURCE"] = "Intuit Actuals"
        gap["ADJUSTED_SPEND"] = 0.0
        gap["RAW_CHANNEL_FACTOR"] = np.nan
        gap["CORRECTION_FACTOR"] = np.nan
        gap["FACTOR_BASIS"] = (
            "QB invoiced | invoiced actual - no tracker row exists "
            "for this month"
        )
        gap["FACTOR_CONFIDENCE"] = "invoiced"
        gap["IMPRESSIONS"] = np.nan
        gap["PUBLISHERS"] = np.nan
        out = pd.concat([out, gap[C.TRACKER_COLUMNS]], ignore_index=True)

    # Append channels with no tracker counterpart whatsoever.
    extra = window[window.CHANNEL == C.UNCLASSIFIED]
    if not extra.empty:
        rows = (
            extra.groupby(["DATE", "Q", "CHANNEL"], as_index=False).SPEND.sum()
        )
        rows["ADVERTISER"] = "QuickBooks"
        rows["PRODUCT"] = C.PRODUCT
        rows["SOURCE"] = "Intuit Actuals"
        rows["ADJUSTED_SPEND"] = rows.SPEND
        rows["RAW_CHANNEL_FACTOR"] = np.nan
        rows["CORRECTION_FACTOR"] = np.nan
        rows["CORRECTED_SPEND"] = rows.SPEND
        rows["FACTOR_BASIS"] = (
            "Intuit invoiced actual | no tracker channel exists for this spend"
        )
        rows["FACTOR_CONFIDENCE"] = "invoiced"
        rows["IMPRESSIONS"] = np.nan
        rows["PUBLISHERS"] = np.nan
        out = pd.concat([out, rows[C.TRACKER_COLUMNS]], ignore_index=True)

    return out


# ---------------------------------------------------------------------------

def summarise(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for advertiser in C.ADVERTISERS:
        row = {"Advertiser": advertiser}
        for label, frame in frames.items():
            part = frame[frame.ADVERTISER == advertiser]
            row[label] = part.CORRECTED_SPEND.sum()
        row["Nielsen tracked"] = frames[list(frames)[0]]
        rows.append(row)
    out = pd.DataFrame(rows).drop(columns="Nielsen tracked")
    return out


FINAL_COLUMNS = [
    "ADVERTISER", "PRODUCT", "DATE", "Q", "CHANNEL", "SOURCE",
    "ACTUAL_SPEND",
    "REPORTED_SPEND",
    "CORRECTION_FACTOR",
    "ADJUSTED_SPEND",
    "FACTOR_BASIS", "FACTOR_CONFIDENCE",
    "IMPRESSIONS", "PUBLISHERS",
]


def consolidate(stacked: pd.DataFrame, nielsen: pd.DataFrame,
                adjusted_frame: pd.DataFrame) -> pd.DataFrame:
    """Build the output dataset with three spend levels per row.

        ACTUAL_SPEND      invoiced spend (QuickBooks only)
        REPORTED_SPEND    tracked spend as reported by Nielsen/AdClarity
        ADJUSTED_SPEND    Method 2 restatement

    Keys are the union of the tracker's rows and any month-channel present only
    in the invoices, so no row is dropped for lack of a match on either side.
    """
    keys = ["ADVERTISER", "PRODUCT", "DATE", "Q", "CHANNEL"]

    actual = (
        stacked[(stacked.DATE >= C.WINDOW_START) & (stacked.DATE <= C.WINDOW_STOP)]
        .groupby(keys, as_index=False).SPEND.sum()
        .rename(columns={"SPEND": "ACTUAL_SPEND"})
    )

    reported = nielsen[keys + ["SOURCE", "SPEND", "IMPRESSIONS", "PUBLISHERS"]].rename(
        columns={"SPEND": "REPORTED_SPEND"}
    )

    adj = adjusted_frame[keys + ["CORRECTED_SPEND", "CORRECTION_FACTOR",
                                 "FACTOR_BASIS", "FACTOR_CONFIDENCE"]].rename(
        columns={"CORRECTED_SPEND": "ADJUSTED_SPEND"}
    )

    out = reported.merge(actual, on=keys, how="outer")
    out = out.merge(adj, on=keys, how="outer")

    out["SOURCE"] = out.SOURCE.fillna("Intuit Actuals")
    out["FACTOR_BASIS"] = out.FACTOR_BASIS.fillna(
        "invoiced actual - no tracker row exists for this month-channel"
    )
    out["FACTOR_CONFIDENCE"] = out.FACTOR_CONFIDENCE.fillna("invoiced")
    for column in ("REPORTED_SPEND", "ACTUAL_SPEND"):
        out[column] = out[column].fillna(0.0)

    # Drop the leading quarters where the rolling blend has no prior history.
    # See ROLLING_START_Q in m2_config.
    if C.ROLLING_START_Q:
        dropped = out[out.Q < C.ROLLING_START_Q]
        if not dropped.empty:
            print(f"  excluded {len(dropped):,} rows before {C.ROLLING_START_Q} "
                  "(rolling blend has no prior history there)")
            print(f"    they would have added "
                  f"${dropped.ADJUSTED_SPEND.sum()/1e6:,.1f}m")
        out = out[out.Q >= C.ROLLING_START_Q]

    out = out.sort_values(["ADVERTISER", "CHANNEL", "DATE"]).reset_index(drop=True)
    return out[FINAL_COLUMNS]


def main() -> None:
    C.OUT_DIR.mkdir(parents=True, exist_ok=True)

    stacked = stack_actuals.stack()
    nielsen = pd.read_csv(C.NIELSEN_CSV)

    actual = stack_actuals.by_channel_quarter(stacked)
    tracked = RF.tracked_by_channel_quarter(nielsen)
    # K comes from m2_config rather than being refitted from the source
    # workbook, so the pipeline reproduces without it.
    k = dict(C.CREDIBILITY_K)
    factors = RF.build(actual, tracked, k)

    # SCALE_COMPETITORS is set in m2_config rather than here, so the competitor
    # treatment is changed in configuration rather than in logic.
    adjusted = add_actual_only_channels(
        apply_method_2(nielsen, factors,
                       scale_competitors=C.SCALE_COMPETITORS), stacked)

    final = consolidate(stacked, nielsen, adjusted)
    path = C.OUT_DIR / "Method 2 - Actuals vs Reported vs Adjusted.csv"
    final.to_csv(path, index=False)
    print(f"  {path.name}  ({len(final):,} rows)")
    print(f"  competitors scaled: {C.SCALE_COMPETITORS}")

    print()
    print("TOTALS ($m)")
    totals = final.groupby("ADVERTISER")[
        ["ACTUAL_SPEND", "REPORTED_SPEND", "ADJUSTED_SPEND"]
    ].sum()
    totals.loc["TOTAL"] = totals.sum()
    print((totals / 1e6).round(2).to_string())

    print()
    print("QUICKBOOKS BY CHANNEL ($m) - only advertiser with invoices")
    qb = final[final.ADVERTISER == "QuickBooks"].groupby("CHANNEL")[
        ["ACTUAL_SPEND", "REPORTED_SPEND", "ADJUSTED_SPEND"]
    ].sum()
    qb.loc["TOTAL"] = qb.sum()
    print((qb / 1e6).round(3).to_string())


if __name__ == "__main__":
    main()
