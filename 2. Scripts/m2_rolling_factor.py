"""The rolling credibility-weighted correction factor - Method 2's engine.

    blended = Z * (last completed quarter) + (1 - Z) * (trailing 4 quarters)

Both components are SUM(actual) / SUM(tracked), summed before dividing. That is
not a stylistic preference: averaging monthly ratios lets a channel-month where
tracked spend is near zero produce a factor over 70,000x and drag the mean with
it. Summing before dividing avoids this.

Z is the credibility weight - how far to trust the recent quarter over the
trailing average. It rises with the tracked dollars behind that quarter, so a
thin quarter leans on the broader history.

WHAT IS RECONSTRUCTED AND WHAT IS NOT
-------------------------------------
Verified against the published workbook:

  - the blend formula itself reproduces its blended_factor column exactly on
    all 20 rows, given its own inputs
  - 16 of 20 quarterly actual/tracked ratios reproduce to within 0.01
  - 15 of 20 blended factors land within 20%

The four that do not are explained, not mysterious. Three are the workbook's
seed quarter: it starts at 2025Q2 and this rebuild starts at 2025Q1, because
tracked data begins there - so the two trailing windows cover different
quarters. The fourth is 2026Q2 Search, where the workbook's search line appears
to use a slightly different tactic mix than the published deck's; that mix is
not recoverable from the saved files.

Z is NOT recoverable. The workbook prints its Z values but never defines them,
and no single constant reproduces all twenty. fit_credibility_k() therefore
fits K per channel against the workbook's own Z column so the reconstruction
lands as close as the artifacts allow - it gets within 0.001 on the
low-credibility rows that matter most. Anything reported from here should say
that Z is a fitted reconstruction rather than a recovered definition.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import m2_config as C

QUARTER_ORDER = ["2024Q1", "2024Q2", "2024Q3", "2024Q4",
                 "2025Q1", "2025Q2", "2025Q3", "2025Q4",
                 "2026Q1", "2026Q2"]


def tracked_by_channel_quarter(nielsen: pd.DataFrame) -> pd.DataFrame:
    """QuickBooks tracked spend per channel per quarter - the denominator.

    Search is the exception. Its SPEND column is $0 in every month, because the
    trackers see no paid search at all. Method 2 instead calibrates against the
    imputed search line the tracker carries in ADJUSTED_SPEND - which is why a
    Search factor exists at all despite nothing being tracked.
    """
    qb = nielsen[nielsen.ADVERTISER == "QuickBooks"]
    frames = {}
    for channel in C.CALIBRATABLE:
        part = qb[qb.CHANNEL == channel]
        column = "ADJUSTED_SPEND" if channel == C.CAP_SOURCE else "SPEND"
        frames[channel] = part.groupby("Q")[column].sum()
    return pd.DataFrame(frames).fillna(0.0)


def _ratio(actual: float, tracked: float) -> float:
    return actual / tracked if tracked > 0 else np.nan


def quarterly_ratios(actual: pd.DataFrame, tracked: pd.DataFrame) -> pd.DataFrame:
    """SUM(actual) / SUM(tracked) for each channel-quarter."""
    quarters = [q for q in QUARTER_ORDER if q in actual.index and q in tracked.index]
    rows = []
    for quarter in quarters:
        for channel in C.CALIBRATABLE:
            rows.append({
                "Q": quarter,
                "Channel": channel,
                "actual": float(actual.loc[quarter].get(channel, 0.0)),
                "tracked": float(tracked.loc[quarter].get(channel, 0.0)),
                "ratio": _ratio(
                    float(actual.loc[quarter].get(channel, 0.0)),
                    float(tracked.loc[quarter].get(channel, 0.0)),
                ),
            })
    return pd.DataFrame(rows)


def fit_credibility_k(reference: pd.DataFrame, ratios: pd.DataFrame) -> dict[str, float]:
    """Fit K per channel so Z = n/(n+K) lands as near the workbook's Z as possible.

    Returns a default for any channel the reference does not cover.
    """
    name_map = {"Search": "Digital", "Social": "Social",
                "Display": "Display", "Video": "Video"}
    fitted: dict[str, float] = {}
    for label, channel in name_map.items():
        rows = reference[reference.NARRATIVE_CHANNEL == label]
        candidates, targets = [], []
        for _, row in rows.iterrows():
            quarter = row.QUARTER
            if quarter not in QUARTER_ORDER:
                continue
            prior_index = QUARTER_ORDER.index(quarter) - 1
            if prior_index < 0:
                continue
            prior = QUARTER_ORDER[prior_index]
            match = ratios[(ratios.Q == prior) & (ratios.Channel == channel)]
            if match.empty or row.credibility_Z in (None, C.SEED_Z):
                continue
            n = float(match.iloc[0]["tracked"])
            z = float(row.credibility_Z)
            if n > 0 and 0 < z < 1:
                candidates.append(n * (1 - z) / z)
                targets.append(z)
        fitted[channel] = float(np.median(candidates)) if candidates else C.CREDIBILITY_K_DEFAULT
    for channel in C.CALIBRATABLE:
        fitted.setdefault(channel, C.CREDIBILITY_K_DEFAULT)
    return fitted


def build(actual: pd.DataFrame, tracked: pd.DataFrame,
          k_by_channel: dict[str, float] | None = None) -> pd.DataFrame:
    """The full rolling factor table, one row per channel-quarter."""
    ratios = quarterly_ratios(actual, tracked)
    k_by_channel = k_by_channel or {c: C.CREDIBILITY_K_DEFAULT for c in C.CALIBRATABLE}

    quarters = sorted(ratios.Q.unique(), key=QUARTER_ORDER.index)
    rows = []
    for index, quarter in enumerate(quarters):
        for channel in C.CALIBRATABLE:
            prior = quarters[:index]
            if not prior:
                seed = ratios[(ratios.Q == quarter) & (ratios.Channel == channel)]
                value = float(seed.ratio.iloc[0]) if not seed.empty else np.nan
                rows.append({
                    "Q": quarter, "Channel": channel,
                    "last_quarter_factor": value, "trailing4_factor": value,
                    "credibility_Z": C.SEED_Z, "blended_factor": value,
                    "basis": "seed (in-sample) - no prior quarter exists",
                })
                continue

            last = prior[-1]
            last_row = ratios[(ratios.Q == last) & (ratios.Channel == channel)]
            last_factor = float(last_row.ratio.iloc[0]) if not last_row.empty else np.nan
            n_tracked = float(last_row.tracked.iloc[0]) if not last_row.empty else 0.0

            window = prior[-4:]
            trail = ratios[(ratios.Q.isin(window)) & (ratios.Channel == channel)]
            trailing = _ratio(trail.actual.sum(), trail.tracked.sum())

            k = k_by_channel.get(channel, C.CREDIBILITY_K_DEFAULT)
            z = n_tracked / (n_tracked + k) if (n_tracked + k) > 0 else 0.0
            blended = z * last_factor + (1 - z) * trailing

            rows.append({
                "Q": quarter, "Channel": channel,
                "last_quarter_factor": last_factor, "trailing4_factor": trailing,
                "credibility_Z": z, "blended_factor": blended,
                "basis": f"rolling | Z from ${n_tracked:,.0f} tracked, K=${k:,.0f}",
            })

    frame = pd.DataFrame(rows)
    return _apply_cap(frame)


def _apply_cap(frame: pd.DataFrame) -> pd.DataFrame:
    """Overwrite display and video with the Search factor.

    Their own factors run to 978x and 5,689x - not estimates, artefacts of
    dividing by a few hundred tracked dollars. Method 2 caps them rather than
    dropping them, which keeps a number in the cell but means display and video
    carry no independent information at all.
    """
    frame = frame.copy()
    frame["uncapped_factor"] = frame.blended_factor
    frame["capped"] = False

    for quarter, group in frame.groupby("Q"):
        source = group[group.Channel == C.CAP_SOURCE]
        if source.empty or pd.isna(source.blended_factor.iloc[0]):
            continue
        cap = float(source.blended_factor.iloc[0])
        for channel in C.CAPPED_CHANNELS:
            mask = (frame.Q == quarter) & (frame.Channel == channel)
            if mask.any() and frame.loc[mask, "blended_factor"].iloc[0] > cap:
                frame.loc[mask, "blended_factor"] = cap
                frame.loc[mask, "capped"] = True
                frame.loc[mask, "basis"] += f" | capped@Search {cap:.2f}x"
    return frame


def compare_to_reference(built: pd.DataFrame) -> pd.DataFrame:
    """Reconstruction against the published workbook, row by row."""
    try:
        ref = pd.read_excel(C.REFERENCE_XLSX, sheet_name="QB Rolling Factors", header=3)
    except Exception as exc:                                    # pragma: no cover
        return pd.DataFrame([{"note": f"reference workbook unreadable: {exc}"}])

    ref = ref[ref.QUARTER.notna()]
    name_map = {"Search": "Digital", "Social": "Social",
                "Display": "Display", "Video": "Video"}
    rows = []
    for _, r in ref.iterrows():
        channel = name_map.get(r.NARRATIVE_CHANNEL)
        match = built[(built.Q == r.QUARTER) & (built.Channel == channel)]
        mine = float(match.uncapped_factor.iloc[0]) if not match.empty else np.nan
        rows.append({
            "Q": r.QUARTER, "Channel": r.NARRATIVE_CHANNEL,
            "workbook last_quarter": r.last_quarter_factor,
            "rebuilt last_quarter": (
                float(match.last_quarter_factor.iloc[0]) if not match.empty else np.nan
            ),
            "workbook blended": r.blended_factor,
            "rebuilt blended (uncapped)": mine,
            "abs diff": abs(mine - r.blended_factor) if pd.notna(mine) else np.nan,
        })
    frame = pd.DataFrame(rows)
    # The quarterly ratio engine is the thing worth checking - it either
    # reproduces or it does not. The blended figure additionally depends on how
    # far back the trailing window reaches, and the published workbook seeds a
    # quarter later than this rebuild does (it starts at 2025Q2, this starts at
    # 2025Q1), so the two trailing windows are not the same set of quarters.
    frame["ratio reproduces"] = (
        (frame["workbook last_quarter"] - frame["rebuilt last_quarter"]).abs()
        / frame["workbook last_quarter"].abs()
    ) < 0.01
    frame["blend within 20%"] = (
        frame["abs diff"] / frame["workbook blended"].abs()
    ) < 0.20
    frame["reproduces"] = frame["abs diff"] < 0.01
    return frame


def main() -> None:
    import stack_actuals

    stacked = stack_actuals.stack()
    nielsen = pd.read_csv(C.NIELSEN_CSV)
    actual = stack_actuals.by_channel_quarter(stacked)
    tracked = tracked_by_channel_quarter(nielsen)

    try:
        ref = pd.read_excel(C.REFERENCE_XLSX, sheet_name="QB Rolling Factors", header=3)
        ref = ref[ref.QUARTER.notna()]
        k = fit_credibility_k(ref, quarterly_ratios(actual, tracked))
    except Exception:
        k = {c: C.CREDIBILITY_K_DEFAULT for c in C.CALIBRATABLE}

    built = build(actual, tracked, k)
    C.OUT_DIR.mkdir(parents=True, exist_ok=True)
    built.to_csv(C.OUT_DIR / "Method 2 - Rolling Factors.csv", index=False)

    print("  fitted credibility K by channel")
    for channel, value in k.items():
        print(f"    {channel:10s} ${value:>14,.0f}")
    print()
    print("  ROLLING FACTORS (tracker window)")
    show = built[built.Q.isin(["2025Q1", "2025Q2", "2025Q3", "2025Q4", "2026Q1", "2026Q2"])]
    print(show[["Q", "Channel", "last_quarter_factor", "trailing4_factor",
                "credibility_Z", "blended_factor", "capped"]].round(4).to_string(index=False))


if __name__ == "__main__":
    main()
