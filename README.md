# Marketing Mix Modeling with Google Meridian

I built the [lightweight MMM](https://github.com/GlitchG/simple-marketing-mix-model) first — adstock, saturation, plain regression. It works. But it has limits: point estimates only, no uncertainty, and no principled way to incorporate what you already know about your channels.

This is the real thing. Google's [Meridian](https://github.com/google/meridian) library does proper Bayesian Marketing Mix Modeling. For every channel, you get a **full posterior distribution** — not just "ROI = 2.3" but "there's a 95% chance ROI is between 1.8 and 3.1." When you're presenting to a CMO who wants to shift half a million euros of budget, that uncertainty matters.

This repo is a step-by-step guide to running Meridian on **your GA4 ecommerce data** — the exact setup I use with clients.

## Why Meridian instead of a linear regression?

| | Simple MMM | Meridian |
|---|:---:|:---:|
| **Method** | OLS regression | Bayesian inference (PyMC) |
| **Output** | Single ROI number | Full probability distribution |
| **Uncertainty** | None | Credible intervals for everything |
| **Priors** | No | Yes — incorporate known channel efficiency ranges |
| **Saturation** | Hill function (manual) | Built-in Hill + reach curves |
| **Geo-level** | No | Yes — hierarchical by region |
| **Experiment calibration** | No | Yes — use lift test results as priors |
| **Media lag** | Geometric only | Geometric + delayed + custom lag functions |

If you have 2+ years of weekly data and at least 3-4 channels, Meridian is the right tool. If you just need a quick sanity check, use the [lightweight version](https://github.com/GlitchG/simple-marketing-mix-model).

## How it works (the short version)

1. **Data prep** — extract weekly spend, revenue, and control variables from GA4 into BigQuery tables
2. **Model specification** — define which channels, what adstock shape, what saturation curve, and what priors
3. **Sampling** — Meridian runs MCMC (Markov Chain Monte Carlo) to draw thousands of samples from the posterior
4. **Diagnostics** — check R-hat values, trace plots, effective sample size to confirm the model converged
5. **Results** — posterior distributions for ROI, response curves per channel, budget optimisation

The output you actually care about:

```
Channel        ROI (median)     90% CI          P(ROI > 1)
─────────────  ───────────────  ─────────────  ──────────
search          3.14            [2.41, 4.02]    0.99
tv              2.47            [1.65, 3.39]    0.98
digital         1.82            [1.20, 2.55]    0.94
social          0.91            [0.40, 1.38]    0.38
```

Search is almost certainly profitable (99% probability). Social might be losing money — you'd need more data to be sure.

## Setup

```bash
# Clone this repo
git clone https://github.com/GlitchG/bigquery-meridian-mmm.git
cd bigquery-meridian-mmm

# Install Meridian (from GitHub — not on PyPI)
pip install -r requirements.txt

# Or manually:
pip install git+https://github.com/google/meridian.git
```

Meridian requires PyMC, which needs a C compiler. On macOS: `xcode-select --install`. On Linux: `apt install build-essential`.

## Running it on your GA4 data

There are three phases, each with a dedicated guide:

### 1. Prepare the data in BigQuery

Run these SQL files against your GA4 export. They produce three clean weekly tables:

- `sql/01_media_spend.sql` — spend, impressions, clicks per channel per week
- `sql/02_kpi_prep.sql` — revenue, transactions, AOV from GA4 ecommerce
- `sql/03_control_vars.sql` — holidays, seasonality dummies, promo periods

Each file has comments explaining how to adapt it to your own schema.

### 2. Configure and fit the model

`models/meridian_mmm.py` loads the CSV exports, configures the Meridian model (adstock priors, saturation curves, ROI priors), runs MCMC sampling, and produces diagnostic plots. The script is heavily commented — read it alongside the [Meridian documentation](https://developers.google.com/meridian).

### 3. Interpret results

The script outputs:
- **Trace plots** — check that chains converged (R-hat < 1.05 for all parameters)
- **Response curves** — spend vs predicted revenue per channel, with uncertainty bands
- **ROI distributions** — posterior density plots per channel
- **Budget optimiser** — what happens if you shift 20% from channel X to channel Y

See `GUIDE.md` for a full walkthrough with screenshots and interpretation notes.

## Data requirements

- **Minimum**: 1 year of weekly data, 3+ channels
- **Recommended**: 2-3 years, geo-level if available
- **GA4**: ecommerce tracking set up, BigQuery export enabled
- **Media data**: spend by channel by week — import from Facebook Ads, Google Ads, TikTok, TV, radio, etc.

If you don't have media data in BigQuery yet, see `sql/00_setup_media_tables.sql` for the table schema.

## What the model assumes

- Adstock decays geometrically (Meridian supports custom lag functions if you need them)
- Saturation follows a Hill curve (Meridian also supports reach-based curves)
- Channels are additive — no interaction effects between TV and search (this is a known limitation of all MMMs)
- Past data predicts future performance — if you changed creative mid-period, the model averages over it

None of these assumptions are dealbreakers. But read the Meridian docs if you want to relax them — most are configurable.

## Files

```
sql/
  01_media_spend.sql          — Weekly spend: Facebook, Google, TikTok, TV, Radio, OOH
  02_kpi_prep.sql             — Weekly revenue from GA4 ecommerce
  03_control_vars.sql         — Holidays, seasonality, promo periods
  00_setup_media_tables.sql   — Schema for importing ad platform data

models/
  meridian_mmm.py             — Meridian model config, MCMC sampling, diagnostics, plots

GUIDE.md                      — Full step-by-step walkthrough with interpretation notes
requirements.txt              — meridian, pymc, arviz, numpy, pandas, matplotlib, jax
```

## Other projects

- [Simple MMM](https://github.com/GlitchG/simple-marketing-mix-model) — lightweight version, no Meridian, plain regression
- [GA4 Attribution Models](https://github.com/GlitchG/ga4-attribution-models) — SQL attribution models
- [Landing Page AB Testing](https://github.com/GlitchG/landing-page-ab-testing) — statistical AB test analysis

---

MIT


## Related

- [ga4-attribution-models](https://github.com/GlitchG/ga4-attribution-models) — multi-touch attribution in BigQuery/Dataform
- [ga4-bigquery-incremental](https://github.com/GlitchG/ga4-bigquery-incremental) — GA4 incremental refresh patterns
- [bigquery-meridian-mmm](https://github.com/GlitchG/bigquery-meridian-mmm) — Bayesian MMM
- [landing-page-ab-testing](https://github.com/GlitchG/landing-page-ab-testing) — GA4 A/B testing in BigQuery
- [cohort-log-predict](https://github.com/GlitchG/cohort-log-predict) — cohort retention prediction
- [receipt-sorter](https://github.com/GlitchG/receipt-sorter) — AI receipt classification
