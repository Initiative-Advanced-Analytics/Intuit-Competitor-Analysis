"""Build the client-facing Excel: pivot-ready data plus a ready-made summary.

The comparison the client wants is "QuickBooks versus its competitors", and the
comparison is not like-for-like. Only QuickBooks has invoices.
Every competitor figure is an estimate built from what the trackers saw.

So the data is emitted in long form with an explicit SPEND_BASIS column:

    Invoiced actual     Intuit's own books          QuickBooks only
    Reported tracked    what Nielsen/AdClarity saw  everyone
    Adjusted estimate   Method 2's restatement      everyone

and a BEST_AVAILABLE flag marking the one row per advertiser-month-channel you
would actually put in front of a client: invoices where they exist, the Method 2
estimate where they do not. Pivot on that flag and the chart is right by
construction; pivot on SPEND_BASIS and you can show the workings.
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
    """One row per advertiser, month, channel and basis."""
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

    # The one row per cell worth presenting: invoices beat estimates.
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
    """The headline table, already built - advertiser by basis."""
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


def main() -> None:
    data = pd.read_csv(SOURCE)
    long = long_form(data)
    head = summary(long)
    channel = by_channel(long)

    notes = pd.DataFrame({
        "Read this first": [
            "QuickBooks is the only advertiser with invoices. Every competitor "
            "figure is an estimate.",
            "",
            "SPEND_BASIS tells you which is which:",
            "  1. Invoiced actual    Intuit's own books. QuickBooks only.",
            "  2. Reported tracked   What Nielsen and AdClarity managed to see.",
            "  3. Adjusted estimate  Method 2's restatement of the tracked figure.",
            "",
            "Filter BEST_AVAILABLE = TRUE for the one figure per cell worth "
            "presenting: invoices where they exist, estimates where they do not.",
            "",
            f"Window: {data.DATE.min()} to {data.DATE.max()}. Earlier months are "
            "excluded because the rolling factor has no prior history to blend "
            "against there, and carries an unfiltered 16.5x seed.",
            "",
            "On this window Method 2 recovers QuickBooks' known spend to within "
            "6.3%. Individual channels are looser - social runs high, display and "
            "video run low - so quote totals rather than channel splits.",
        ]
    })

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
