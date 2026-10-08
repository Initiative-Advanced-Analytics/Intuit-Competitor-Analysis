# Method 2: the rolling quarterly factor

To run it: `python "2. Scripts/run_all.py"`

Everything resolves relative to the folder, so it can be moved, renamed or
copied and will still run. It does not reach outside itself.

This is the working folder. `Production level/` holds the packaged version for
handover: same method and same figures, but with the source workbook dependency
removed and the date window deriving itself from the data.

---

## What Method 2 does

Corrects QuickBooks tracked spend against its own invoices using a
credibility-weighted blend of its recent and trailing actual-to-tracked ratios,
then applies the same factors to competitors.

```
blended factor = Z * (last completed quarter) + (1 - Z) * (trailing 4 quarters)
```

Both components use `SUM(actual) / SUM(tracked)`, summed before dividing.
Averaging monthly ratios instead lets a channel-month with almost no tracked
spend produce a factor in the thousands and drag the mean with it. On video the
two approaches give **32.2x** and **2,370.7x** respectively.

Z is the credibility weight: how far to trust the recent quarter against the
trailing average. It rises with the tracked spend behind that quarter, so a
low-volume quarter leans on the longer history.

---

## The two variants

Method 2 exists in two forms and they disagree. This is the decision to make
before using any of these figures.

The methodology document states:

> We do NOT apply QuickBooks' correction factors to competitors. A factor
> calibrated on QuickBooks' buying is not evidence about Xero's or Sage's, and
> transferring it invents precision we do not have.

The existing tracker file applies them regardless. Every competitor row reads
`FACTOR_BASIS = "QB-proxy"`.

`SCALE_COMPETITORS` in `m2_config.py` resolves it for the whole pipeline:

| Setting | Effect |
|---|---|
| `True` | Apply the factors to competitors. Matches the existing tracker and is the only setting that produces competitor spend figures |
| `False` | Leave competitors at tracked spend. Cleaner methodologically, but it moves Xero by 0.7%, so the result is effectively the raw feed |

Set to `True`, because the deliverable requires competitor figures. The caveat
travels with them: every competitor figure is one advertiser's measured
correction applied to another advertiser's buying, and should be presented as an
estimate rather than a measurement.

---

## Current output

Window July 2025 to April 2026, 241 rows.

| | Invoiced | Reported | Adjusted |
|---|---|---|---|
| Sage | | $28.38m | $67.94m |
| Xero | | $41.56m | $65.33m |
| QuickBooks | $19.76m | $11.29m | $24.56m |
| Zoho | | $1.75m | $7.74m |
| NetSuite | | $0.49m | $0.64m |
| **Total** | | **$83.47m** | **$166.22m** |

---

## The folders

### `1. Inputs`

| File | Contents |
|---|---|
| `Media Activity Template.xlsx` | Invoiced weekly spend, 2023-05 to 2026-05 |
| `Updated Nielsen + AdClarity Spends.csv` | The tracker file, 2025-01 to 2026-04 |
| `QuickBooks Rolling Factor & Competitor Confidence (v2).xlsx` | The published workbook, used as the reconstruction reference |

### `2. Scripts`

| File | Purpose |
|---|---|
| `run_all.py` | Start here. Runs every step in order and stops at the first failure |
| `m2_config.py` | Paths, channel taxonomy, offline multipliers, all settings |
| `stack_actuals.py` | Wide weekly template to long monthly rows on the tracker schema |
| `m2_rolling_factor.py` | The factor engine: ratios, credibility weighting, the cap |
| `build_m2_outputs.py` | Applies Method 2 and writes the dataset |
| `build_client_view.py` | Builds the reporting workbook |
| `verify_m2.py` | Validation checks. Do not publish figures unless these pass |

### `3. Outputs`

Regenerated on each run. Nothing here needs hand-editing.

| File | Contents |
|---|---|
| `Method 2 - Actuals vs Reported vs Adjusted.csv` | The dataset, one row per advertiser, month and channel, on the tracker's 15 columns |
| `Method 2 - Client View.xlsx` | Pivot-ready, with a summary and current accuracy figures |
| `Method 2 - Rolling Factors.csv` | Every factor with its components, Z and basis |
| `Intuit Actual Spend - Stacked.csv` | Invoiced spend, long form, full history |

For the Client View workbook, pivot with `ADVERTISER` on rows, `CHANNEL` on
columns, `Sum of SPEND` as values, and a filter of `BEST_AVAILABLE = TRUE`. The
sheet is long-form with three bases stacked, so an unfiltered pivot sums all
three.

---

## Channel coverage

Stacking the actuals alongside the tracker makes the gaps visible:

| Channel | Intuit actual | Tracked | Coverage |
|---|---|---|---|
| Digital (search) | $19.0m | $0 | Tracker has the channel but reports $0 for every advertiser in every month |
| Social | $6.6m | $8.4m | Both sources |
| Video | $3.1m | $0.15m | Both sources |
| Display | $1.5m | $0.05m | Both sources |
| Unclassified | $33k | | No tracker channel exists; the template's unlabelled column |
| TV, Radio, Outdoor, Press, Direct Mail | | $12.9m | Tracker only; no invoice exists |

Two consequences. QuickBooks' search is taken from invoices rather than the
tracker's modelled line. And the unlabelled column is retained as
`Unclassified` rather than dropped, at $421,757 across the full history.

---

## What reproduces, and what does not

Checked against the published workbook:

- The blend formula reproduces its `blended_factor` column exactly on all 20
  rows, given its own inputs
- 16 of 20 quarterly actual/tracked ratios reproduce to within 0.01
- 15 of 20 blended factors land within 20%
- Applied to competitors, the rebuild reproduces the tracker file to 0.6% on
  Xero

The four discrepancies are accounted for. Three are the seed quarter: the
workbook starts at 2025Q2 and this rebuild starts at 2025Q1, where tracked data
begins, so the trailing windows cover different quarters. The fourth is 2026Q2
Search.

One thing cannot be rebuilt. The workbook reports its `Z` values but never
defines them, and no single constant reproduces all twenty.
`fit_credibility_k()` fits `K` per channel against the workbook's own `Z`
column, landing within 0.001 on the low-credibility rows that matter most. Treat
`Z` as a fitted reconstruction rather than a recovered definition, and say so if
the figures are challenged.

---

## Before presenting this

**Quote totals rather than channel splits.** The method is calibrated to the
total and the per-channel errors do not cancel by design:

| Channel | Invoiced | Method 2 | |
|---|---|---|---|
| Digital | $11.03m | $11.03m | 1.00x, substituted from invoice |
| Social | $5.57m | $9.41m | 1.69x high |
| Video | $2.13m | $0.33m | 0.15x low |
| Display | $1.04m | $0.24m | 0.23x low |

**The headline accuracy figure needs qualifying.** Against invoices the total
lands within 6.3%, but Digital is over half that total and matches exactly
because it is substituted from invoice rather than estimated. On the channels
actually being estimated the error is 14.2%. Quote 6.3% for the deliverable;
know that 14.2% describes the method.

**Display and video carry no independent information.** Their own factors run to
978x and 5,689x, which is the result of dividing by a few hundred tracked
dollars. Method 2 overwrites both with the search factor, so the rolling
calculation only sets the level for search and social.

**The method's own out-of-sample test was a tie.** Predicting one quarter from
prior data only: flat annual factor 55.3% dollar-weighted error, rolling factor
56.6%. The original document says so plainly, and its stated value is fixing
the averaging problem and staying adaptive rather than being more accurate.

**Social swings hard.** Its factor runs 16.50x in 2025Q1 and Q2 down to 0.49x in
2025Q4, a 32-fold move within a year on the same advertiser. Applied to
competitors, four months of 2025 at 16.5x generate $184.9m of Xero's total,
which is why the output starts at 2025Q3.

**A month of search was being lost.** The tracker holds no QuickBooks digital
row for 2026-02, so $724,083 of invoiced search fell out. It is appended here,
and `verify_m2.py` will catch it if it returns. The published workbook drops
that month too, which is why its 2026Q1 Search actual reads $3,232,163 against
the invoiced $3,956,246.

---

## Refreshing when new data lands

**New actuals.** Replace `Media Activity Template.xlsx`, keeping the sheet name
`Media Activity Template`. If new buying tactics appear as columns, add them to
`ACTUAL_TO_TRACKER` in `m2_config.py` so they map to a tracker channel rather
than falling into `Unclassified`.

**New tracker data.** Replace `Updated Nielsen + AdClarity Spends.csv` and
update `WINDOW_START` and `WINDOW_STOP` in `m2_config.py`. The `Production
level/` copy derives these from the data instead.

Rerun `verify_m2.py` after either. The conservation and schema checks will show
quickly if something has drifted.

Most settings sit at the top of `m2_config.py`: the offline multipliers, the
capped channels, the seed weight, `ROLLING_START_Q` and `SCALE_COMPETITORS`.
