"""Build the reporting workbook: pivot-ready data plus a summary.

The QuickBooks versus competitors comparison is not like-for-like. Only
QuickBooks has invoices; every competitor figure is an estimate derived from
tracked spend.

Data is therefore emitted in long form with an explicit SPEND_BASIS column:

    Invoiced actual     invoiced spend              QuickBooks only
    Reported tracked    tracked spend as reported   all advertisers
    Adjusted estimate   Method 2 restatement        all advertisers

A BEST_AVAILABLE flag marks the single row per advertiser-month-channel to
report: invoiced where available, the Method 2 estimate otherwise. Pivoting on
that flag avoids double counting across bases; pivoting on SPEND_BASIS shows the
derivation.
"""

from __future__ import annotations

import pandas as pd

import m2_config as C

SOURCE = C.OUT_DIR / "Method 2 - Actuals vs Reported vs Adjusted.csv"
DEST = C.OUT_DIR / "Method 2 - Client View.xlsx"

BASIS_INVOICED = "1. Invoiced actual"
BASIS_REPORTED = "2. Reported tracked"
BASIS_ADJUSTED = "3. Adjusted estimate"


def long_form(data: pd.DataFrame) -> pd.DataFrame:
    """Reshape to one row per advertiser, month, channel and basis."""
    keys = ["ADVERTISER", "DATE", "Q", "CHANNEL"]
    parts = []

    invoiced = data[data.ACTUAL_SPEND > 0][keys + ["ACTUAL_SPEND"]].copy()
    invoiced["SPEND_BASIS"] = BASIS_INVOICED
    invoiced = invoiced.rename(columns={"ACTUAL_SPEND": "SPEND"})
    parts.append(invoiced)

    reported = data[data.REPORTED_SPEND > 0][keys + ["REPORTED_SPEND"]].copy()
    reported["SPEND_BASIS"] = BASIS_REPORTED
    reported = reported.rename(columns={"REPORTED_SPEND": "SPEND"})
    parts.append(reported)

    adjusted = data[data.ADJUSTED_SPEND > 0][
        keys + ["ADJUSTED_SPEND"]
    ].copy()
    adjusted["SPEND_BASIS"] = BASIS_ADJUSTED
    adjusted = adjusted.rename(columns={"ADJUSTED_SPEND": "SPEND"})
    parts.append(adjusted)

    out = pd.concat(parts, ignore_index=True)

    # One row per cell for reporting: prefer invoiced over estimated.
    invoiced_cells = set(
        map(tuple, data[data.ACTUAL_SPEND > 0][keys].to_numpy().tolist())
    )
    out["BEST_AVAILABLE"] = [
        (
            row.SPEND_BASIS == BASIS_INVOICED
            or (
                row.SPEND_BASIS == BASIS_ADJUSTED
                and tuple(getattr(row, k) for k in keys) not in invoiced_cells
            )
        )
        for row in out.itertuples()
    ]

    out["EVIDENCE"] = out.apply(
        lambda r: "Invoiced - Intuit's own books"
        if r.SPEND_BASIS == BASIS_INVOICED
        else ("Estimated - no invoice exists for this advertiser"
              if r.SPEND_BASIS == BASIS_ADJUSTED
              else "Tracker feed - what the vendor could see"),
        axis=1,
    )

    out["MONTH"] = pd.to_datetime(out.DATE).dt.strftime("%b %Y")
    order = ["ADVERTISER", "DATE", "MONTH", "Q", "CHANNEL",
             "SPEND_BASIS", "EVIDENCE", "BEST_AVAILABLE", "SPEND"]
    return out[order].sort_values(
        ["ADVERTISER", "CHANNEL", "DATE", "SPEND_BASIS"]
    ).reset_index(drop=True)


def summary(long: pd.DataFrame) -> pd.DataFrame:
    """Summary table: advertiser by spend basis."""
    table = long.pivot_table(
        index="ADVERTISER", columns="SPEND_BASIS", values="SPEND", aggfunc="sum"
    ).fillna(0.0)
    best = long[long.BEST_AVAILABLE].groupby("ADVERTISER").SPEND.sum()
    table["Best available"] = best
    table.loc["TOTAL"] = table.sum()
    return table.reset_index()


def by_channel(long: pd.DataFrame) -> pd.DataFrame:
    table = long[long.BEST_AVAILABLE].pivot_table(
        index="CHANNEL", columns="ADVERTISER", values="SPEND", aggfunc="sum"
    ).fillna(0.0)
    table["TOTAL"] = table.sum(axis=1)
    table.loc["TOTAL"] = table.sum()
    return table.reset_index()


def _notes(data: pd.DataFrame) -> list[str]:
    """Build the Read Me text, with accuracy measured from the loaded data."""
    qb = data[data.ADVERTISER == "QuickBooks"]
    cal = qb[qb.CHANNEL.isin(C.CALIBRATABLE)]
    total_err = cal.ADJUSTED_SPEND.sum() / cal.ACTUAL_SPEND.sum() - 1

    # Search is substituted from invoice, so its match is definitional. Quote the
    # error on the estimated channels separately.
    est = cal[cal.CHANNEL != C.CAP_SOURCE]
    est_err = est.ADJUSTED_SPEND.sum() / est.ACTUAL_SPEND.sum() - 1

    worst = []
    for channel in sorted(cal.CHANNEL.unique()):
        part = cal[cal.CHANNEL == channel]
        if part.ACTUAL_SPEND.sum() > 0:
            worst.append(
                f"    {channel:<10} invoiced ${part.ACTUAL_SPEND.sum():>12,.0f}"
                f"   adjusted ${part.ADJUSTED_SPEND.sum():>12,.0f}"
                f"   {part.ADJUSTED_SPEND.sum() / part.ACTUAL_SPEND.sum():.2f}x"
            )

    return [
        "QuickBooks is the only advertiser with invoiced spend. Every "
        "competitor figure is an estimate.",
        "",
        "SPEND_BASIS identifies which is which:",
        "  1. Invoiced actual    Invoiced spend. QuickBooks only.",
        "  2. Reported tracked   Spend as reported by Nielsen and AdClarity.",
        "  3. Adjusted estimate  Method 2 restatement of the tracked figure.",
        "",
        "Filter BEST_AVAILABLE = TRUE for one figure per advertiser, month and "
        "channel: invoiced where available, estimated otherwise. Without that "
        "filter a pivot sums all three bases together.",
        "",
        f"Window: {data.DATE.min()} to {data.DATE.max()}. Earlier months are "
        "excluded because the rolling factor has no prior history to blend "
        "against there and carries an undamped seed ratio.",
        "",
        "ACCURACY against QuickBooks invoices, this window:",
        f"    total across calibrated channels   {total_err:+.1%}",
        f"    estimated channels only            {est_err:+.1%}",
        "",
        f"The second figure is the one that describes the method. {C.CAP_SOURCE} "
        "is substituted from invoice rather than estimated, so its match is "
        "definitional and flatters the total.",
        "",
        "By channel:",
    ] + worst + [
        "",
        "Quote totals rather than channel splits. Per-channel errors do not "
        "cancel by design.",
    ]


def main() -> None:
    data = pd.read_csv(SOURCE)
    long = long_form(data)
    head = summary(long)
    channel = by_channel(long)

    notes = pd.DataFrame({"Read this first": _notes(data)})

    with pd.ExcelWriter(DEST, engine="xlsxwriter") as writer:
        notes.to_excel(writer, sheet_name="Read Me", index=False)
        head.to_excel(writer, sheet_name="Summary", index=False)
        channel.to_excel(writer, sheet_name="By Channel", index=False)
        long.to_excel(writer, sheet_name="Data", index=False)

        book = writer.book
        money = book.add_format({"num_format": "$#,##0"})
        bold = book.add_format({"bold": True})

        # Format the flat sheet as a real Excel Table so Insert > PivotTable
        # picks the range up with no selecting.
        sheet = writer.sheets["Data"]
        sheet.add_table(
            0, 0, len(long), len(long.columns) - 1,
            {
                "name": "SpendData",
                "style": "Table Style Light 9",
                "columns": [{"header": c} for c in long.columns],
            },
        )
        sheet.set_column("A:A", 13)
        sheet.set_column("B:C", 11)
        sheet.set_column("D:E", 10)
        sheet.set_column("F:F", 20)
        sheet.set_column("G:G", 44)
        sheet.set_column("H:H", 15)
        sheet.set_column("I:I", 14, money)

        for name, frame in (("Summary", head), ("By Channel", channel)):
            ws = writer.sheets[name]
            ws.set_column("A:A", 16, bold)
            ws.set_column("B:H", 20, money)

        writer.sheets["Read Me"].set_column("A:A", 92)

    print(f"  {DEST.name}")
    print()
    print("SUMMARY ($m)")
    print((head.set_index("ADVERTISER") / 1e6).round(2).to_string())


if __name__ == "__main__":
    main()
