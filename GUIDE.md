# Guide: Running Meridian MMM on GA4 Data

A step-by-step walkthrough from GA4 export to budget optimisation. I wrote this for my own reference and for clients who want to understand what's happening under the hood.

## Prerequisites

- GA4 property with ecommerce tracking and BigQuery export enabled
- Media spend data (Facebook Ads, Google Ads, TikTok, etc.) — see `sql/00_setup_media_tables.sql` for the schema
- Python 3.10–3.12 with Meridian installed (`pip install -r requirements.txt`)
- At least 52 weeks of data (156 / 3 years recommended for a national model)

> **Just want to see it run?** Skip straight to a synthetic dataset: `python python/generate_sample_data.py` then `python models/meridian_mmm.py`. No BigQuery required. See Step 2.5 for the column dictionary.

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

### 2.5 The `mmm_input.csv` data dictionary

The model script reads one **long-format** CSV — one row per week per channel. This is exactly what the JOIN above produces, and also what `python/generate_sample_data.py` writes. Each column:

| Column | Type | Level | Required | Description |
|---|---|---|---|---|
| `week_start` | DATE (`YYYY-MM-DD`) | week | yes | First day of the week (Monday). The model's time axis. |
| `channel` | STRING | row | yes | Channel name. Must match the `CHANNELS` list in the script (`search`, `tv`, `digital`, `tiktok`, `ooh`, `social`). |
| `spend` | FLOAT | week × channel | yes | Media spend for that channel that week, in your currency. Drives the ROI estimate. |
| `impressions` | INT | week × channel | yes | Impressions for that channel that week. Meridian uses these as the media execution variable. If you only have spend, set `impressions = spend` (the model still works; ROI is unaffected). |
| `clicks` | INT | week × channel | no | Not used by the model — kept for your own CPM/CTR analysis. |
| `revenue` | FLOAT | week | yes | Total weekly revenue (the KPI). **Repeated on every channel row for that week** — the loader takes one value per week, so all rows for a given week must carry the same number. |
| `is_holiday` | 0/1 | week | yes | Holiday-week flag (control). |
| `is_black_friday_week` | 0/1 | week | yes | Black Friday week flag (control). |
| `is_summer` | 0/1 | week | yes | Summer-period flag (control). |
| `is_promo_period` | 0/1 | week | yes | Promo-week flag (control). |
| `month_num` | INT (1–12) | week | no | Kept for reference; not fed as a control (raw month as a linear term would be misleading). |

**Filling it in — bare minimum vs. ideal:**

- **Bare minimum to run:** `week_start`, `channel`, `spend`, `impressions`, `revenue`, and the four control flags, for **at least 52 weeks**. If you have no impressions, copy `spend` into `impressions`.
- **Recommended:** **156 weeks (3 years)** — Meridian's guidance for a national model — so it can separate annual seasonality from channel effects. Real impressions per channel. Accurate control flags for every known sales event.

> **Sanity check before fitting:** every channel should have *varying* spend week to week. If two channels always move together (e.g. TV and radio always run the same weeks at proportional budgets), Meridian can't tell them apart and will split the credit arbitrarily. The synthetic generator deliberately varies each channel independently to avoid this.

## Step 3: Configure the model

Open `models/meridian_mmm.py` and adjust these sections:

### Channel list
```python
CHANNELS = ["search", "tv", "digital", "tiktok", "ooh", "social"]
CONTROL_COLS = ["is_holiday", "is_black_friday_week", "is_summer", "is_promo_period"]
```
Remove channels you don't have and add channels you do — the names must match the `channel` values in your CSV.

### ROI priors
Meridian uses an **ROI-based prior** (`media_prior_type='roi'`): you state a prior belief about each channel's return, and the model updates it from the data. The script sets a single weakly-informative LogNormal prior for all channels:
```python
ROI_PRIOR_MU = np.log(2.0)   # prior median ROI ≈ 2x
ROI_PRIOR_SIGMA = 0.7        # 90% prior range ≈ 0.5x–8x
```
If you have lift tests or strong per-channel beliefs, tighten `ROI_PRIOR_SIGMA` (and you can give each channel its own prior by passing a batched `LogNormal` to `roi_m`). For a first MMM, keep it wide.

### Adstock window
```python
MAX_LAG = 8   # weeks of carryover Meridian considers
```
Meridian fits the geometric adstock decay rate per channel from the data; `MAX_LAG` just caps how many past weeks contribute. 8 weeks is plenty for digital; raise it if you run long TV bursts.

### Sampling
```python
N_CHAINS, N_ADAPT, N_BURNIN, N_KEEP = 4, 1000, 500, 1000
```
Lower these for a quick smoke test; raise `N_KEEP`/`N_CHAINS` for a production fit. Convergence (R-hat) is reported in the model summary.

## Step 4: Run the model

```bash
python models/meridian_mmm.py
```

What happens:
1. Meridian reads the CSV and pivots it into its wide internal layout (no geo column → a single-geo national model)
2. Configures the model with geometric adstock, Hill saturation, and the ROI priors
3. Runs NUTS MCMC sampling (this takes several minutes — progress bars show the chains)
4. Writes `output/roi_summary.txt` and `output/summary_output.html`

## Step 5: Check diagnostics

Before trusting any ROI numbers, verify the model converged. Open **`output/summary_output.html`** — Meridian's built-in report. It contains:

### R-hat values
Every parameter should have R-hat < 1.05, ideally < 1.01. If any parameter exceeds this, increase `N_KEEP` / `N_BURNIN` (and optionally `N_ADAPT`) in the script and re-run.

### Model fit
The actual-vs-expected revenue plot should track closely. Large systematic gaps mean missing controls or too short a history.

### Effective sample size
Should be comfortably > 100 for the ROI parameters. If it's low, raise `N_KEEP`.

> On the synthetic dataset, the recovered ROIs should land near the ground-truth values printed by `generate_sample_data.py` (search ≈ 3.0, tv ≈ 2.4, digital ≈ 1.8, tiktok ≈ 1.5, ooh ≈ 1.2, social ≈ 0.9). That round-trip is the cheapest confirmation the pipeline is wired up correctly.

## Step 6: Interpret results

### ROI distributions
`output/roi_summary.txt` lists, per channel:

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
`summary_output.html` includes spend-vs-incremental-revenue curves per channel, with uncertainty bands. Look for:

- **Saturation point** — the spend level where the curve flattens. Spending more beyond this point adds little.
- **Shape** — a steep initial slope means the first euros are very efficient. A flat curve from the start means the channel isn't working.

### Budget optimisation (optional next step)
The script stops at ROI + summary. To turn the fit into a budget recommendation, Meridian ships an optimiser:
```python
from meridian.analysis import optimizer
opt = optimizer.BudgetOptimizer(mmm)
results = opt.optimize()           # respects each channel's saturation curve
results.output_optimization_summary("optimization_output.html", "output")
```
It won't pour everything into `search` if search is already saturated — it allocates against the response curves.

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
