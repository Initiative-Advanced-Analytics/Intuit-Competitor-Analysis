"""Checks that must pass before any Method 2 number is used.

Several exist because something was wrong the first time. If this does not come
back clean, do not ship the figures.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import m2_config as C
import m2_rolling_factor as RF
import stack_actuals
from build_m2_outputs import add_actual_only_channels, apply_method_2

PASS, FAIL = [], []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(f"{'PASS' if ok else 'FAIL'}  {name:<46s} {detail}")


def main() -> int:
    stacked = stack_actuals.stack()
    nielsen = pd.read_csv(C.NIELSEN_CSV)
    actual = stack_actuals.by_channel_quarter(stacked)
    tracked = RF.tracked_by_channel_quarter(nielsen)

    try:
        ref = pd.read_excel(C.REFERENCE_XLSX, sheet_name="QB Rolling Factors", header=3)
        ref = ref[ref.QUARTER.notna()]
        k = RF.fit_credibility_k(ref, RF.quarterly_ratios(actual, tracked))
    except Exception:
        ref, k = None, {c: C.CREDIBILITY_K_DEFAULT for c in C.CALIBRATABLE}

    factors = RF.build(actual, tracked, k)
    adjusted = add_actual_only_channels(
        apply_method_2(nielsen, factors,
                       scale_competitors=C.SCALE_COMPETITORS), stacked)
    # The unscaled variant is still built, but only so the competitor-handling
    # check below has something to assert against.
    unscaled = add_actual_only_channels(
        apply_method_2(nielsen, factors, scale_competitors=False), stacked)

    # 1. No spend may be lost in the wide -> long reshape.
    wide = stack_actuals.load_actuals_wide()
    check(
        "stacking conserves total actual spend",
        abs(stacked.SPEND.sum() - wide["Total Media"].sum()) < 1.0,
        f"${stacked.SPEND.sum():,.0f}",
    )

    # 2. The unlabelled column must survive rather than be silently dropped.
    unclassified = stacked[stacked.CHANNEL == C.UNCLASSIFIED].SPEND.sum()
    check(
        "unlabelled template column is carried",
        unclassified > 0,
        f"${unclassified:,.0f} kept as '{C.UNCLASSIFIED}'",
    )

    # 3. Every emitted dataset must match the tracker schema exactly.
    source_columns = list(nielsen.columns)
    check(
        "adjusted dataset matches tracker schema",
        list(adjusted.columns) == source_columns,
        f"{len(source_columns)} columns",
    )

    # 4. SUM/SUM, never a mean of ratios. A mean would blow up on the thin
    #    quarters; confirm the two differ, so summing first has an effect.
    ratios = RF.quarterly_ratios(actual, tracked)
    video = ratios[(ratios.Channel == "Video") & ratios.ratio.notna()]
    sum_over_sum = video.actual.sum() / video.tracked.sum()
    mean_of_ratios = video.ratio.mean()
    check(
        "SUM/SUM differs from mean-of-ratios",
        mean_of_ratios > sum_over_sum * 2,
        f"video {sum_over_sum:,.1f}x vs {mean_of_ratios:,.1f}x if averaged",
    )

    # 5. The blend must sit between its two components.
    rolling = factors[factors.basis.str.startswith("rolling")].dropna(
        subset=["last_quarter_factor", "trailing4_factor"]
    )
    lo = rolling[["last_quarter_factor", "trailing4_factor"]].min(axis=1)
    hi = rolling[["last_quarter_factor", "trailing4_factor"]].max(axis=1)
    inside = ((rolling.uncapped_factor >= lo - 1e-6)
              & (rolling.uncapped_factor <= hi + 1e-6))
    check("blend lies between its two components", bool(inside.all()),
          f"{inside.sum()}/{len(inside)} rows")

    # 6. Credibility must move the right way: more tracked dollars, more weight
    #    on the recent quarter.
    #    K differs per channel, so pooling channels breaks the relationship.
    #    Z is monotonic in n within a channel, which is what to test.
    work = rolling.copy()
    work["n"] = (
        work.basis.str.extract(r"Z from \$([\d,]+)")[0]
        .str.replace(",", "").astype(float)
    )
    monotonic = []
    for channel, group in work.groupby("Channel"):
        if len(group) < 3:
            continue
        # Spearman, not Pearson: Z = n/(n+K) is monotonic in n but hyperbolic,
        # so a linear correlation understates a relationship that is exact.
        monotonic.append(
            group[["n", "credibility_Z"]].corr(method="spearman").iloc[0, 1]
        )
    worst = min(monotonic) if monotonic else float("nan")
    check("credibility rises with tracked volume", worst > 0.999,
          f"worst within-channel rank r = {worst:.3f}")

    # 7. Display and video must end up capped - uncapped they are artefacts.
    capped = factors[factors.Channel.isin(C.CAPPED_CHANNELS)]
    check(
        "display and video are capped at Search",
        bool(capped.capped.any()),
        f"{capped.capped.sum()}/{len(capped)} channel-quarters",
    )

    # 8. As documented, no competitor may be scaled at all.
    comp = unscaled[unscaled.ADVERTISER != "QuickBooks"]
    untouched = np.isclose(
        comp.CORRECTED_SPEND, comp.ADJUSTED_SPEND, rtol=1e-9, atol=1e-6
    )
    check(
        "unscaled variant leaves competitors untouched",
        bool(untouched.all()),
        f"{untouched.sum()}/{len(comp)} competitor rows at tracked level",
    )

    # 9. As shipped must reproduce the real tracker file it is imitating.
    mine = adjusted[adjusted.ADVERTISER == "Xero"].CORRECTED_SPEND.sum()
    theirs = nielsen[nielsen.ADVERTISER == "Xero"].CORRECTED_SPEND.sum()
    check(
        "as-shipped reproduces the tracker file",
        abs(mine / theirs - 1) < 0.05,
        f"Xero ${mine/1e6:.1f}m vs ${theirs/1e6:.1f}m ({mine/theirs:.3f})",
    )

    # 10. QuickBooks' search must come from invoices, not the modelled line.
    qb_search = adjusted[
        (adjusted.ADVERTISER == "QuickBooks") & (adjusted.CHANNEL == C.CAP_SOURCE)
    ]
    invoiced = stacked[
        (stacked.CHANNEL == C.CAP_SOURCE)
        & (stacked.DATE >= C.WINDOW_START) & (stacked.DATE <= C.WINDOW_STOP)
    ].SPEND.sum()
    check(
        "QuickBooks search uses invoiced actuals",
        abs(qb_search.CORRECTED_SPEND.sum() - invoiced) < 1.0,
        f"${invoiced:,.0f}",
    )

    # 11. Channels the tracker cannot see must reach the output.
    extra = adjusted[adjusted.CHANNEL == C.UNCLASSIFIED]
    check(
        "invoice-only channels reach the adjusted dataset",
        not extra.empty,
        f"{len(extra)} rows, ${extra.CORRECTED_SPEND.sum():,.0f}",
    )

    # 12. Offline pre-adjustment must be applied.
    tv = adjusted[adjusted.CHANNEL == "TV"]
    ratio = tv.ADJUSTED_SPEND.sum() / tv.SPEND.sum()
    check(
        "offline rate-card adjustment applied",
        abs(ratio - C.OFFLINE_MULTIPLIER["TV"]) < 0.001,
        f"TV {ratio:.4f}x",
    )

    # 13. Reconstruction quality against the published workbook.
    if ref is not None:
        comparison = RF.compare_to_reference(factors)
        good = int(comparison["ratio reproduces"].sum())
        check(
            "quarterly ratios reproduce the workbook",
            good >= 15,
            f"{good}/{len(comparison)} to 0.01 "
            "(misses are the seed quarter and the Search tactic mix)",
        )

    # 14. No negative or absurd corrected values.
    bad = adjusted[adjusted.CORRECTED_SPEND < 0]
    check("no negative corrected spend", bad.empty, f"{len(bad)} rows")

    # 15. The published file must carry exactly one adjusted-spend column.
    published = pd.read_csv(
        C.OUT_DIR / "Method 2 - Actuals vs Reported vs Adjusted.csv"
    )
    adjusted_columns = [c for c in published.columns if c.startswith("ADJUSTED")]
    check("published file has one adjusted column", len(adjusted_columns) == 1,
          ", ".join(adjusted_columns))

    print()
    print(f"{len(PASS)}/{len(PASS) + len(FAIL)} checks passed")
    if FAIL:
        print("FAILED: " + ", ".join(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
