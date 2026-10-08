"""Reshape actual QuickBooks spend to the tracker schema.

The Media Activity Template is wide: one row per week, one column per buying
tactic. Downstream code needs it long, as one row per advertiser, month and
channel on the same 15 columns as the tracker file.

Two deliberate behaviours:

  - the unlabelled 'null' column is retained, not dropped. It contains $421,757
    across 100 weeks. It is mapped to 'Unclassified' and excluded from all
    factor calculations.
  - output is not restricted to the tracker window. The full history is
    written, because the trailing-four-quarter factor needs quarters that
    predate the tracker file.
"""

from __future__ import annotations

import pandas as pd

import m2_config as C


def load_actuals_wide() -> pd.DataFrame:
    """Weekly actual spend as held in the template."""
    frame = pd.read_excel(C.ACTUALS_XLSX, sheet_name=C.ACTUALS_SHEET)
    frame["Week"] = pd.to_datetime(frame["Week"])
    return frame


def stack(frame: pd.DataFrame | None = None) -> pd.DataFrame:
    """Reshape wide weekly tactics to long monthly rows on the tracker schema.

    Weeks are assigned to the month containing their start date, so a week
    spanning a month boundary falls entirely in the earlier month. This matches
    the convention used by the tracker's monthly rows.
    """
    frame = load_actuals_wide() if frame is None else frame

    tactics = [c for c in frame.columns if c in C.ACTUAL_TO_TRACKER]
    missing = set(C.ACTUAL_TO_TRACKER) - set(tactics)
    if missing:
        print(f"  note: template has no column for {sorted(missing)}")

    long = frame.melt(
        id_vars="Week", value_vars=tactics,
        var_name="ACTUAL_TACTIC", value_name="SPEND",
    )
    long = long[long.SPEND.notna() & (long.SPEND != 0)].copy()

    long["CHANNEL"] = long.ACTUAL_TACTIC.map(C.ACTUAL_TO_TRACKER)
    long["DATE"] = long.Week.dt.to_period("M").dt.to_timestamp()
    long["Q"] = long.Week.dt.to_period("Q").astype(str)

    grouped = (
        long.groupby(["DATE", "Q", "CHANNEL", "ACTUAL_TACTIC"], as_index=False)
        .SPEND.sum()
    )

    grouped["ADVERTISER"] = "QuickBooks"
    grouped["PRODUCT"] = C.PRODUCT
    grouped["SOURCE"] = "Intuit Actuals"
    grouped["ADJUSTED_SPEND"] = grouped.SPEND
    grouped["RAW_CHANNEL_FACTOR"] = 1.0
    grouped["CORRECTION_FACTOR"] = 1.0
    grouped["CORRECTED_SPEND"] = grouped.SPEND
    grouped["FACTOR_BASIS"] = "Intuit invoiced actual - no correction applies"
    grouped["FACTOR_CONFIDENCE"] = "invoiced"
    grouped["IMPRESSIONS"] = pd.NA
    grouped["PUBLISHERS"] = pd.NA
    grouped["DATE"] = grouped.DATE.dt.strftime("%Y-%m-%d")

    return grouped[C.TRACKER_COLUMNS + ["ACTUAL_TACTIC"]]


def by_channel_quarter(stacked: pd.DataFrame) -> pd.DataFrame:
    """Actual spend by tracker channel and quarter. Factor numerator."""
    usable = stacked[stacked.CHANNEL != C.UNCLASSIFIED]
    return (
        usable.pivot_table(index="Q", columns="CHANNEL", values="SPEND", aggfunc="sum")
        .fillna(0.0)
    )


def coverage(stacked: pd.DataFrame, nielsen: pd.DataFrame) -> pd.DataFrame:
    """Channel coverage by source.

    Digital exists as a tracker channel but reports $0 for every advertiser in
    every month, so it is effectively actuals-only.
    """
    window = stacked[
        (stacked.DATE >= C.WINDOW_START) & (stacked.DATE <= C.WINDOW_STOP)
    ]
    act = window.groupby("CHANNEL").SPEND.sum()
    qb = nielsen[nielsen.ADVERTISER == "QuickBooks"]
    tracked = qb.groupby("CHANNEL").SPEND.sum()

    channels = sorted(set(act.index) | set(tracked.index))
    rows = []
    for channel in channels:
        a = float(act.get(channel, 0.0))
        t = float(tracked.get(channel, 0.0))
        if a > 0 and t > 0:
            verdict = "both sources"
        elif a > 0 and t == 0:
            verdict = (
                "ACTUALS ONLY - channel absent from tracker"
                if channel not in set(nielsen.CHANNEL)
                else "ACTUALS ONLY - tracker has the channel but reports $0"
            )
        elif t > 0:
            verdict = "TRACKER ONLY - no Intuit invoice exists"
        else:
            verdict = "no spend either side"
        rows.append({
            "Channel": channel,
            "Intuit actual": a,
            "Nielsen/AdClarity tracked": t,
            "Tracked / actual": (t / a) if a else float("nan"),
            "Coverage": verdict,
            "Usable for a factor": channel in C.CALIBRATABLE and a > 0 and t > 0,
        })
    return pd.DataFrame(rows)


def main() -> None:
    stacked = stack()
    C.OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = C.OUT_DIR / "Intuit Actual Spend - Stacked.csv"
    stacked.to_csv(path, index=False)

    print(f"  {path.name}")
    print(f"    {len(stacked):,} rows | {stacked.DATE.min()} -> {stacked.DATE.max()}")
    print()
    print("  BY CHANNEL, full history")
    summary = stacked.groupby("CHANNEL").SPEND.sum().sort_values(ascending=False)
    for channel, value in summary.items():
        print(f"    {channel:14s} ${value:>14,.0f}")
    print(f"    {'TOTAL':14s} ${summary.sum():>14,.0f}")


if __name__ == "__main__":
    main()
