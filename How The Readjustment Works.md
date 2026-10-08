# How the readjustment works

A step-by-step walkthrough of Method 2: what it does, why, and what comes out.
Written to be read start to finish without prior knowledge of the data.

**Window covered:** July 2025 to April 2026
**Advertisers:** QuickBooks, Xero, Sage, Zoho, NetSuite

Every figure below comes from one specific run. The method is general; the
numbers are not. If the inputs have changed since, take the current figures from
`3. Outputs/Method 2 - Client View.xlsx` (Summary sheet) and use this document
for the derivation.

This is the working folder. The packaged version for handover, with the source
workbook dependency removed and the window deriving itself from the data, is in
`Production level/`.

---

## The problem

Nielsen and AdClarity report competitor media spend, but what they report is
what their technology detected, not what was placed. For paid search they report
nothing at all: $0 for every advertiser in every month. For display and video
they capture a few per cent. The raw figures therefore understate the market, and
they understate it by different amounts in different channels, which distorts
comparisons between advertisers rather than simply scaling them down.

The size of that gap is measurable for exactly one advertiser, QuickBooks,
because Intuit supplies its invoices. Method 2 measures the gap there and applies
it to the rest.

---

## Step 1. Reshape the invoiced spend

Intuit's spend arrives as a weekly spreadsheet with one column per buying tactic.
It is reshaped to one row per month per channel to align with the tracker data.

Tactics map to tracker channels as follows:

| Tracker channel | Intuit tactics |
|---|---|
| Digital | App Search, Paid Search, PerformanceMax, Demand Gen |
| Social | Paid Social |
| Video | OLV, YouTube, Video OLV |
| Display | Display |

The reshape conserves the total: **$65,251,608** across the full history,
matching the source file. Four published figures from the client deck also
reconcile exactly (2025 Digital $13,947,177, Social $7,400,881, Display
$758,320, and Jan to Apr 2026 $7,962,628).

One column in the template carries no label but contains $421,757. It is
retained as "Unclassified" rather than dropped, and excluded from every factor.

---

## Step 2. Adjust offline channels for rate card

Nielsen books TV, radio and outdoor at rate card, the published price rather than
the negotiated one. Press runs the other way and tends to be under-captured.

Fixed multipliers are applied before any factor:

| TV | Radio | Outdoor | Press | Direct Mail |
|---|---|---|---|---|
| 0.8164x | 0.6963x | 0.8000x | 1.4000x | 1.0000x |

These are inherited from the existing methodology rather than re-derived. No
offline invoices exist to calibrate them against.

---

## Step 3. Measure the gap by quarter

For each channel and quarter, compare invoiced spend against tracked spend:

```
ratio = total actual spend / total tracked spend
```

This is summed first and divided second, never averaged across monthly ratios. A
single month where the tracker captured almost nothing produces a ratio in the
thousands, and averaging lets it dominate. On video the two approaches give
**32x** and **2,371x** respectively.

Social, as an example:

| Quarter | Intuit actual | Tracked | Ratio |
|---|---|---|---|
| 2025Q1 | $1,751,344 | $106,172 | 16.50 |
| 2025Q2 | $2,121,688 | $1,632,952 | 1.30 |
| 2025Q3 | $1,623,290 | $4,676,638 | 0.35 |

These move considerably. That instability is what the next step addresses.

---

## Step 4. Blend recent against historical

Using only the most recent quarter makes the correction volatile. Using a long
average makes it stale. The two are blended:

```
factor = Z * (most recent quarter) + (1 - Z) * (trailing four quarters)
```

Z is a credibility weight: how far to trust the recent quarter. It rises with the
tracked spend behind that quarter:

```
Z = n / (n + K)
```

where n is the tracked spend in the recent quarter and K is the volume at which a
quarter earns half credibility:

| Digital | Social | Video | Display |
|---|---|---|---|
| $589,994 | $1,835,628 | $35,842 | $2,826 |

In effect, a quarter backed by substantial tracked spend carries weight, and a
quarter backed by very little defers to the longer average.

This is the damping mechanism. In 2026Q2 the most recent quarter implied a video
factor of 238x, but it rested on $1,027 of tracked spend. Z fell to 0.03 and the
final factor came out at 30x, almost entirely from the trailing average.

---

## Step 5. Cap display and video

Display and video have so little tracked spend that their own factors are not
usable: 978x and 5,689x. These are the result of dividing by a few hundred
dollars rather than estimates.

Both are capped at the search factor.

The consequence is that display and video carry no independent information. They
inherit the search figure, so the rolling calculation only sets the level for
search and social.

---

## Step 6. Drop the start-up quarters

The blend needs two distinct inputs. At the start of the series it does not have
them:

- **2025Q1** has no prior quarter at all.
- **2025Q2** has exactly one, so the recent and trailing components are the same
  number. Blending a number with itself returns that number for any Z.

Both quarters therefore carried QuickBooks' 16.5x seed ratio undamped, and that
ratio came from a single quarter where tracking had largely failed ($106k tracked
against $1.75m spent).

Left in, those two quarters alone generated $184.9m of Xero's total.

They are excluded. Output starts from 2025Q3, where the blend has real history.
This is the single largest correction made to the method:

| | QuickBooks invoiced | Method 2 | Error |
|---|---|---|---|
| Including start-up quarters | $34.57m | $58.08m | 68% |
| From 2025Q3 only | $19.76m | $21.01m | 6.3% |

Note how that 6.3% is composed. Digital is $11.03m of the $21.01m and matches at
exactly 1.00x because step 8 substitutes the invoice, so it is definitional
rather than evidence. On the channels actually being estimated (social, video,
display) the error is **+14.2%**. Both figures are valid but answer different
questions: 6.3% describes the deliverable, 14.2% describes the method.

---

## Step 7. Apply the factor

```
adjusted spend = reported spend * factor
```

The resulting factors:

| Channel | 2025Q3 | 2025Q4 | 2026Q1 | 2026Q2 |
|---|---|---|---|---|
| Digital / Display / Video | 4.97x | 4.80x | 4.55x | 7.42x |
| Social | 1.79x | 0.49x | 0.96x | 1.56x |
| TV / Radio / Outdoor / Press | 1.00x (already adjusted at step 2) | | | |

Social sometimes corrects downward. In 2025Q4 the factor is 0.49x: the trackers
were over-reporting social rather than under-reporting it. A method that could
only scale upward would not detect that.

---

## Step 8. Restore invoiced figures

Where an invoice exists it is used. QuickBooks' search spend is taken from
Intuit's books ($11.03m) rather than from the model.

One month was being lost: the tracker holds no QuickBooks digital row for
February 2026, so $724,083 of invoiced search had no row to sit against. It is
added as its own row.

---

## Output

| | Invoiced | Reported | Adjusted |
|---|---|---|---|
| Sage | | $28.38m | $67.94m |
| Xero | | $41.56m | $65.33m |
| QuickBooks | $19.76m | $11.29m | $24.56m |
| Zoho | | $1.75m | $7.74m |
| NetSuite | | $0.49m | $0.64m |
| **Total** | | **$83.47m** | **$166.22m** |

---

## Worked example

Social, 2025Q4, start to finish.

**1. Quarterly ratios**

| Quarter | Actual | Tracked | Ratio |
|---|---|---|---|
| 2025Q1 | $1,751,344 | $106,172 | 16.4954 |
| 2025Q2 | $2,121,688 | $1,632,952 | 1.2993 |
| 2025Q3 | $1,623,290 | $4,676,638 | 0.3471 |

**2. Most recent completed quarter** is 2025Q3, giving 0.3471.

**3. Trailing window**, summed then divided:

```
$5,496,323 / $6,415,762 = 0.8567
```

**4. Credibility weight.** 2025Q3 had $4,676,638 of tracked social behind it:

```
Z = 4,676,638 / (4,676,638 + 1,835,628) = 0.7181
```

Well populated, so the recent quarter takes 72% of the weight.

**5. Blend**

```
0.7181 * 0.3471  +  0.2819 * 0.8567
= 0.2493         +  0.2415
= 0.4907
```

**6. Apply**

| Advertiser | Reported | Adjusted at 0.4907 |
|---|---|---|
| Xero | $10,429,126 | $5,118,030 |
| Sage | $3,343,043 | $1,640,578 |
| QuickBooks | $1,853,852 | $909,767 |
| Zoho | $64,095 | $31,454 |
| NetSuite | $29,864 | $14,656 |

---

## Presenting this

Points that hold up:

- QuickBooks is the only advertiser with invoices. Every competitor figure is an
  estimate produced by applying QuickBooks' measured correction to their reported
  spend.
- On this window the method recovers QuickBooks' known spend to within 6.3%,
  which is the closest any version of this methodology has come to the invoiced
  total. If pressed, the fuller answer is that search is substituted from invoice
  rather than estimated, and the error on the estimated channels alone is 14.2%.
- The correction runs in both directions: search and display up, social sometimes
  down, TV and radio down for rate card.

Points to handle carefully:

- **Quote totals rather than channel splits.** The total holds up; individual
  channels do not. Social runs about 1.7x high and video about 6.5x low against
  invoices. They partly offset, which is why the total works.
- **Competitor figures carry an assumption the original methodology rejects.**
  The correction was measured on QuickBooks' buying and applied to advertisers
  whose buying is not visible. It is the only way to produce competitor figures,
  but it is an estimate rather than a measurement.
- **Display and video inherit the search factor** rather than being corrected on
  their own evidence.
- **The window is ten months, not a year.** Earlier months were excluded for the
  reason in step 6. An annual figure would need annualising or more data.

---

## Files

| File | Contents |
|---|---|
| `README.md` | Method description, configuration and what reproduces |
| `3. Outputs/Method 2 - Actuals vs Reported vs Adjusted.csv` | The dataset, one row per advertiser, month and channel |
| `3. Outputs/Method 2 - Client View.xlsx` | Pivot-ready, with a summary and current accuracy figures |
| `3. Outputs/Method 2 - Rolling Factors.csv` | Every factor with its components and basis |
| `3. Outputs/Intuit Actual Spend - Stacked.csv` | Invoiced spend, long form, full history |
| `2. Scripts/run_all.py` | Rebuilds everything from source |
| `2. Scripts/verify_m2.py` | Validation checks |
| `Production level/` | The packaged version for handover |

To rebuild: `python "2. Scripts/run_all.py"`
