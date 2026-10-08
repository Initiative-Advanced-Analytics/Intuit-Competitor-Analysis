# Method 2: rolling quarterly factor

Restates reported competitor media spend into an estimate of spend actually
placed, by measuring the reporting gap on the one advertiser with invoiced
actuals and applying it to the rest.

The folder is self-contained. Point it at different inputs and rerun. No figures
are hard-coded in this file; current numbers are always in `3. Outputs`, and the
date window and quarter handling derive from whatever data is loaded.

## Running it

```
python "2. Scripts/run_all.py"
```

Five steps: stack actuals, build factors, apply the method, build the workbook,
validate. The run stops at the first failure and names the file if one is locked.

Requires Python 3.9 or later with pandas, numpy, openpyxl and xlsxwriter.

## Method

```
factor   = Z * (last completed quarter) + (1 - Z) * (trailing four quarters)
Z        = n / (n + K)
adjusted = reported * factor
```

1. Stack the actuals. Weekly invoice columns become monthly rows on the
   tracker's channels.
2. Pre-adjust offline channels for rate card, since the tracker books TV, radio
   and outdoor at published rather than negotiated prices.
3. Measure the gap per channel and quarter as `SUM(actual) / SUM(tracked)`,
   summed before dividing. Averaging monthly ratios lets a month with almost no
   tracked spend produce a ratio in the thousands and dominate the mean.
4. Blend the recent quarter against the trailing window, weighted by Z, which
   is driven by the tracked spend behind that recent quarter. A low-volume
   quarter falls back on the longer history.
5. Cap the low-volume channels at the search factor. Their own ratios are
   division by a few hundred dollars rather than usable estimates.
6. Drop the leading quarters the blend cannot damp (see below).
7. Apply the factor to every advertiser.
8. Substitute invoiced spend wherever it exists.

`Methodology - How The Readjustment Works.md` has the full walkthrough with a
worked example.

## Changing the inputs

### Input files

Both sit in `1. Inputs`. Keep the filenames, or repoint `ACTUALS_XLSX` and
`NIELSEN_CSV` at the top of `m2_config.py`.

**`Media Activity Template.xlsx`** holds the invoiced actuals on a sheet named
`Media Activity Template`. One row per week, one column per buying tactic:

| Week | App Search | Paid Social | Display | ... | Total Media |
|---|---|---|---|---|---|

**`Updated Nielsen + AdClarity Spends.csv`** holds the tracker feed, one row per
advertiser, month and channel. Required columns:

```
ADVERTISER  PRODUCT  DATE  Q  CHANNEL  SOURCE  SPEND  ADJUSTED_SPEND
RAW_CHANNEL_FACTOR  CORRECTION_FACTOR  CORRECTED_SPEND
FACTOR_BASIS  FACTOR_CONFIDENCE  IMPRESSIONS  PUBLISHERS
```

`SPEND` is reported spend. `ADJUSTED_SPEND` is used in preference for any
channel where `SPEND` is zero but a modelled figure exists. `CORRECTED_SPEND` is
optional: if present, one diagnostic compares against it.

### Derived automatically

These need no edit when the data changes:

| Item | Source |
|---|---|
| Date window | The tracker file's own date range |
| Seed cut-off | The first two quarters present are dropped |
| Advertisers | Taken from the tracker; any set of names works |
| Quarters | Derived from the dates; any span works |

Set `WINDOW_START_OVERRIDE`, `WINDOW_STOP_OVERRIDE` or
`ROLLING_START_Q_OVERRIDE` in `m2_config.py` to pin any of them. All default to
`None`, meaning derive.

### Requires an edit

New buying tactics: add the column to `ACTUAL_TO_TRACKER` in `m2_config.py` so
it maps to a tracker channel. Unmapped columns fall into `Unclassified`, which
is carried through but excluded from every factor, so the spend is retained but
not corrected.

New tracker channels: add offline channels to `OFFLINE_MULTIPLIER`. Add online
channels to `CALIBRATABLE` only if invoiced actuals exist for them, since a
channel without invoices cannot produce a factor.

### Configuration

All at the top of `m2_config.py`:

| Setting | Effect |
|---|---|
| `SCALE_COMPETITORS` | `True` applies the measured factors to competitors. `False` leaves them at reported spend and produces no competitor estimates. See the caveats below |
| `CREDIBILITY_K` | Tracked spend at which a quarter earns half credibility, per channel. Low favours the recent quarter, high favours the trailing average |
| `OFFLINE_MULTIPLIER` | Rate-card correction per offline channel. Inherited assumptions; no offline invoices exist to calibrate against |
| `CAPPED_CHANNELS`, `CAP_SOURCE` | Which low-volume channels inherit which factor |
| `INERT_SEED_QUARTERS` | Leading quarters to discard. Leave at 2 unless the next section applies |
| `SEED_Z` | Weight used in the first quarter, which has no prior |
| `CALIBRATABLE` | Channels permitted to produce a factor |

`CREDIBILITY_K` is pinned to values fitted against the original source workbook,
so the pipeline reproduces without it. It is a documented assumption rather than
a measurement, and it is the most sensitive setting here: reverting to a flat
default moves the social factor by up to 94% in a low-volume quarter, while
search, display and video move under 3%. Rerun the checks after changing it.

### Why the first two quarters are dropped

The blend needs two distinct inputs. At the start of any series it does not have
them: the first quarter has no prior, and the second has exactly one, so the
recent and trailing components are the same number. Since
`Z * x + (1 - Z) * x = x` for any Z, the weighting has no effect there and
cannot damp a bad early tracking quarter.

On the original series, leaving those quarters in overshot the invoiced total by
68%, and a single seed ratio generated most of the largest competitor's spend.
Raise `INERT_SEED_QUARTERS` if the history is noisier; do not lower it.

## Outputs

Everything in `3. Outputs` is regenerated on each run and should not be edited
by hand.

### `Method 2 - Client View.xlsx`

Four sheets: Read Me, Summary, By Channel, Data. The Data sheet is an Excel
Table named `SpendData`, so Insert > PivotTable picks up the range without a
selection.

Pivot with `ADVERTISER` on rows, `CHANNEL` on columns, `Sum of SPEND` as values,
and a filter of `BEST_AVAILABLE = TRUE`.

That filter is required. The sheet is long-form with three bases stacked
(invoiced, reported, adjusted), so an unfiltered pivot sums all three.
`BEST_AVAILABLE` marks one row per advertiser, month and channel: invoiced where
available, estimated otherwise.

The Read Me sheet reports the current accuracy against invoices, computed from
the loaded data rather than stored.

### Other files

| File | Contents |
|---|---|
| `Method 2 - Actuals vs Reported vs Adjusted.csv` | The same figures wide: one row per advertiser, month and channel on the tracker's 15 columns, so it loads into anything already built against that schema |
| `Method 2 - Rolling Factors.csv` | Every factor with its components, Z and basis. Audit trail for tracing any figure back |
| `Intuit Actual Spend - Stacked.csv` | Invoiced spend, long form, full history |

## Validation

```
python "2. Scripts/verify_m2.py"
```

Thirteen checks covering dollar conservation through the reshape, schema
integrity, the blend sitting between its components, credibility rising with
volume, the cap, the offline adjustment, invoice substitution and non-negative
output. A fourteenth becomes active if the source reconstruction workbook is
restored to `1. Inputs`.

Do not circulate figures unless this completes clean. `Verification.txt` is a
dated receipt of the last run; regenerate it after any change.

Lines marked `INFO` are reported but do not affect the result. They are
diagnostics that only reconcile against the dataset the method was originally
built on. The tracker's own `CORRECTED_SPEND` column, for example, was computed
over the full original series including the seed quarters this pipeline drops,
so it reads near 1.00 on that input and diverges on any other.

Checks worth understanding when they fail:

- **stacking conserves total actual spend**: the reshape lost or created spend,
  usually an unmapped tactic column.
- **blend lies between its two components**: an arithmetic error in the factor
  engine, or a Z outside 0 to 1.
- **QuickBooks search uses invoiced actuals**: a month of invoiced spend has no
  tracker row to sit against and is being dropped.

## Caveats

These apply regardless of the data loaded.

**Quote totals rather than channel splits.** The method is calibrated to the
total, and per-channel errors do not cancel by design. Expect social to run high
and the low-volume channels to run low. Check the current spread in the Read Me
sheet before quoting any channel-level figure.

**Search accuracy is partly definitional.** Where invoices exist, search is
substituted rather than estimated, so it reports as an exact match and flatters
any headline accuracy figure. The Read Me sheet reports both the total and the
error on the estimated channels only; the second describes the method.

**Competitor figures are estimates resting on a contested assumption.** The
methodology document states that QuickBooks' correction factors should not be
applied to competitors. `SCALE_COMPETITORS = True` applies them anyway, since
`False` produces no competitor figures at all. Every competitor figure is one
advertiser's measured correction applied to another advertiser's buying, and
should be presented as such.

**Capped channels carry no independent information.** They inherit the search
factor, so the rolling calculation only sets the level for search and whichever
channels have genuine tracked volume.

**Z is a reconstruction.** The source workbook reported Z but did not define it,
and no single constant reproduced all of its values. K is fitted per channel
against that column. The blend formula itself reproduces exactly.

**Correction runs in both directions.** Factors below 1.0 are a valid result,
not an error. The trackers over-report some channels, and rate-card pricing
makes offline spend read high.

## Contents

| Path | Contents |
|---|---|
| `README.md` | This file |
| `Methodology - How The Readjustment Works.md` | Step-by-step walkthrough with a worked example |
| `Verification.txt` | Dated receipt of the last validation run |
| `1. Inputs/` | The two source files |
| `2. Scripts/` | `run_all.py`, `m2_config.py`, `stack_actuals.py`, `m2_rolling_factor.py`, `build_m2_outputs.py`, `build_client_view.py`, `verify_m2.py` |
| `3. Outputs/` | Regenerated on each run |
