# Guide: Running Meridian MMM on GA4 Data

A step-by-step walkthrough from GA4 export to budget optimisation. I wrote this for my own reference and for clients who want to understand what's happening under the hood.

## Prerequisites

- GA4 property with ecommerce tracking and BigQuery export enabled
- Media spend data (Facebook Ads, Google Ads, TikTok, etc.) — see `sql/00_setup_media_tables.sql` for the schema
- Python 3.10+ with Meridian installed (`pip install -r requirements.txt`)
- At least 52 weeks of data (104+ recommended)

## Step 1: Export media spend data

Before running Meridian, you need your media data in BigQuery. If you're using ad platform exports (Supermetrics, Fivetran, n8n pipelines), the data should already be there. If not, create a table using the schema in `sql/00_setup_media_tables.sql` and import your data.

The key columns:
- `week_start` (DATE) — first day of the week (Monday)
- `channel` (STRING) — 'facebook', 'google', 'tiktok', 'tv', 'radio', 'ooh'
- `spend` (FLOAT64) — total spend in euros for that week
- `impressions` (INT64) — optional, used for CPM analysis
- `clicks` (INT64) — optional

## Step 2: Run the SQL preparation queries

Run these in order against your GA4 BigQuery dataset:

### 2.1 Media spend aggregation
```sql
-- Run: sql/01_media_spend.sql
-- Output: weekly_media_spend table with spend, impressions, clicks per channel
```

This query joins all your channel tables and produces a clean weekly view. Edit the `WHERE` clauses to match your date range and channel availability.

### 2.2 KPI preparation
```sql
-- Run: sql/02_kpi_prep.sql
-- Output: weekly_kpi table with revenue, transactions, AOV
```

Extracts ecommerce revenue from GA4 purchase events, aggregated by week. If your KPI is something other than revenue (leads, subscriptions, trial starts), modify the metric extraction.

### 2.3 Control variables
```sql
-- Run: sql/03_control_vars.sql
-- Output: weekly_controls table with holiday flags, seasonality, promo periods
```

Without control variables, the model will attribute seasonal spikes (Christmas, Black Friday) to whatever ads happened to run that week. The controls let Meridian separate "people just buy more in December" from "the December campaign actually worked."

For Portuguese/European data, the file includes:
- Portuguese national holidays
- Black Friday week indicator
- Summer period (July-August)
- Month dummies for residual seasonality
- Promo period flags (custom — set your own)

### 2.4 Export to CSV

Run this in BigQuery to join everything:

```sql
SELECT
  ms.week_start,
  ms.channel,
  ms.spend,
  ms.impressions,
  kpi.revenue,
  kpi.transactions,
  c.is_holiday,
  c.is_black_friday_week,
  c.is_summer,
  c.is_promo_period,
  c.month_num
FROM weekly_media_spend ms
JOIN weekly_kpi kpi ON ms.week_start = kpi.week_start
JOIN weekly_controls c ON ms.week_start = c.week_start
ORDER BY ms.week_start, ms.channel
```

Export as CSV and save as `mmm_input.csv` in the project root.

## Step 3: Configure the model

Open `models/meridian_mmm.py` and adjust these sections:

### Channel list
```python
CHANNELS = ['tv', 'digital', 'search', 'social', 'tiktok', 'ooh']
```
Remove channels you don't have. Add channels you do. Keep the order consistent with your CSV.

### Adstock priors
```python
ADSTOCK_PRIOR_MEAN = 0.5   # Half-life: 1-2 weeks for digital, 2-4 for TV
ADSTOCK_PRIOR_SD = 0.2     # How uncertain you are
```
Higher mean = longer carryover. Digital channels typically decay faster (0.3-0.5); TV and radio decay slower (0.5-0.8).

### ROI priors
```python
ROI_PRIOR_MEAN = 2.0       # Prior belief: each channel returns ~2x
ROI_PRIOR_SD = 1.5         # Wide uncertainty if you're not sure
```
If you have historical data or lift tests, tighten the priors. If this is your first MMM, keep them wide.

## Step 4: Run the model

```bash
python models/meridian_mmm.py
```

What happens:
1. Meridian reads the CSV
2. Configures the model with adstock, saturation, and prior distributions
3. Runs MCMC sampling (this takes a few minutes — the progress bar shows chains)
4. Produces diagnostic plots in `output/`

## Step 5: Check diagnostics

Before trusting any ROI numbers, verify the model converged:

### R-hat values
Open `output/diagnostics_summary.txt`. Every parameter should have R-hat < 1.05, ideally < 1.01. If any parameter exceeds this, increase `NUM_SAMPLES` and `NUM_WARMUP` in the script and re-run.

### Trace plots
Open `output/trace_plots.png`. Each parameter gets one row. The chains (different colours) should overlap completely — no separation, no drift. If chains don't mix, the model hasn't converged.

### Effective sample size
Should be > 100 for key parameters (ROI, adstock decay). If ESS is low, increase the number of samples.

## Step 6: Interpret results

### ROI distributions
`output/roi_posteriors.png` shows the posterior distribution for each channel's ROI. Key numbers to pull from the summary output:

- **Median ROI** — the most likely return per euro spent
- **90% credible interval** — there's a 90% chance the true ROI is in this range
- **P(ROI > 1)** — probability the channel is actually profitable

Example interpretation:
```
search:  ROI = 3.14  [2.41, 4.02]  P(ROI>1) = 0.99  → very likely profitable
social:  ROI = 0.91  [0.40, 1.38]  P(ROI>1) = 0.38  → probably losing money
tv:      ROI = 2.47  [1.65, 3.39]  P(ROI>1) = 0.98  → likely profitable
```

### Response curves
`output/response_curves.png` plots spend vs predicted revenue per channel, with uncertainty bands. Look for:

- **Saturation point** — the spend level where the curve flattens. Spending more beyond this point adds little.
- **Shape** — a steep initial slope means the first euros are very efficient. A flat curve from the start means the channel isn't working.

### Budget optimiser
`output/budget_optimisation.png` shows the optimal allocation given a total budget constraint. It respects saturation — it won't tell you to put all your money into search if search is already saturated.

## Step 7: Act on the findings

The model tells you what happened. What you do with it is your call. Typical actions:

- **ROI > 2 with wide intervals**: increase spend and re-measure in 3 months to narrow the estimate
- **ROI < 1 with P(ROI>1) < 0.3**: consider cutting or redesigning creative
- **Saturated channels**: don't cut — the model is telling you they're effective, just at diminishing returns. Optimise within budget, don't kill them.
- **Channels with very wide intervals**: you need more data. Keep spending at current levels, don't make big changes until the uncertainty narrows.

## Common pitfalls

### Not enough data
Meridian needs at least 52 weeks. With less, the model can't separate seasonality from channel effects. The diagnostics will warn you — R-hat values will be high, and the trace plots won't converge.

### Collinear channels
If you always run TV and radio together (same weeks, proportional spend), Meridian can't separate them. The model will split the credit evenly, which may be wrong. Fix: vary your spend patterns, or merge the channels if they're always coupled.

### Ignoring seasonality
Without control variables, Meridian will attribute Christmas revenue to December ads. Always include holiday flags, month dummies, and any known sales events.

### Over-interpreting point estimates
The whole point of Meridian is uncertainty. Don't say "search ROI is 3.14." Say "search ROI is probably between 2.4 and 4.0, with a median of 3.1." The interval is the real result.

## When to run this again

- Every quarter — track how channel efficiency changes over time
- After major campaign changes — did the new creative improve ROI?
- Before budget planning — optimise next quarter's allocation
- After adding a new channel — wait at least 26 weeks, then re-run
