# Architecture — bigquery-meridian-mmm

## Stack
Python 3.10+, Google Meridian, PyMC, JAX, BigQuery, SQL

## Data Flow
```
GA4 BigQuery export (ecommerce events)
    → sql/01_media_spend.sql (weekly spend per channel)
    → sql/02_kpi_prep.sql (weekly revenue, transactions)
    → sql/03_control_vars.sql (holidays, seasonality, promos)
        → BigQuery JOIN → CSV export (mmm_input.csv)
            → models/meridian_mmm.py (load CSV → Meridian model → MCMC sampling)
                → output/ (trace plots, ROI posteriors, response curves, diagnostics)
```

## File Map
- `sql/` — BigQuery queries for data prep: media spend, KPI, control variables
- `models/meridian_mmm.py` — core model: Meridian config, MCMC sampling, diagnostics, visualisation
- `GUIDE.md` — full step-by-step walkthrough with interpretation notes
- `requirements.txt` — meridian, pymc, arviz, numpy, pandas, matplotlib, jax
- `.brain/` — AI agent context
- `.github/workflows/` — CI

## Design Patterns
- **SQL for extraction, Python for modelling**: BigQuery handles heavy aggregation; Python does the Bayesian inference
- **Config over code**: all model parameters (priors, channels, sampling) are module-level constants, easy to adjust without touching logic
- **Diagnostics-first**: R-hat, trace plots, and ESS are checked before any ROI interpretation
- **Prior-driven**: Bayesian approach means you can incorporate existing knowledge through priors — no "cold start" like frequentist methods
