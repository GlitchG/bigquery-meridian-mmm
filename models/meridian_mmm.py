"""
Marketing Mix Model using Google Meridian (real API).

Fits a national, revenue-based Bayesian MMM on weekly GA4 ecommerce data:
geometric adstock + Hill saturation per channel, ROI priors, NUTS sampling,
then ROI posteriors and a model-results summary.

Quick start (synthetic data — no BigQuery needed):
    pip install -r requirements.txt
    python python/generate_sample_data.py   # writes mmm_input.csv
    python models/meridian_mmm.py

On your own data, export the BigQuery tables to the same long-format CSV
(see GUIDE.md for the column dictionary and the export query), then run the
model script unchanged.

API reference: https://developers.google.com/meridian
"""

import os

import numpy as np
import pandas as pd

from meridian import constants
from meridian.data import data_frame_input_data_builder as builder_lib
from meridian.model import model, prior_distribution, spec
from meridian.analysis import analyzer, optimizer, summarizer
import tensorflow_probability as tfp

# ── Configuration ──────────────────────────────────────────────

DATA_FILE = "mmm_input.csv"          # long-format CSV (see generate_sample_data.py / GUIDE.md)
OUTPUT_DIR = "output"                # where plots, summary, and ROI table are written
CHANNELS = ["search", "tv", "digital", "tiktok", "ooh", "social"]
CONTROL_COLS = ["is_holiday", "is_black_friday_week", "is_summer", "is_promo_period"]

# ROI prior (LogNormal, in revenue-per-euro units). Wide enough to be weakly
# informative: median ROI ~2, but the 90% range spans roughly 0.5–8.
# Tighten these if you have lift-test results or strong priors per channel.
ROI_PRIOR_MU = np.log(2.0)
ROI_PRIOR_SIGMA = 0.7

MAX_LAG = 8          # weeks of adstock carryover Meridian considers
CONFIDENCE = 0.90    # credible-interval level reported in the summary

# MCMC settings. Lower n_keep / n_chains for a fast smoke test; raise for a
# production fit. Convergence is checked via R-hat in the model summary.
N_CHAINS = 4
N_ADAPT = 1000
N_BURNIN = 500
N_KEEP = 1000
N_PRIOR = 500
SEED = 0


# ── Data Loading ───────────────────────────────────────────────

def load_and_prep_data(csv_path):
    """Load the long-format CSV and pivot into Meridian's wide layout.

    Long format (one row per week per channel) is what the BigQuery pipeline
    and generate_sample_data.py emit. Meridian wants one row per week with a
    `<channel>_spend` and `<channel>_impression` column per channel, plus the
    weekly KPI and control columns.
    """
    df = pd.read_csv(csv_path)

    spend = df.pivot_table(index="week_start", columns="channel", values="spend", aggfunc="sum")
    impressions = df.pivot_table(index="week_start", columns="channel", values="impressions", aggfunc="sum")

    for ch in CHANNELS:
        if ch not in spend.columns:
            spend[ch] = 0.0
            impressions[ch] = 0.0

    wide = pd.DataFrame(index=spend.index)
    for ch in CHANNELS:
        wide[f"{ch}_spend"] = spend[ch].fillna(0.0)
        wide[f"{ch}_impression"] = impressions[ch].fillna(0.0)

    # revenue + controls are week-level: take the per-week value (first row).
    week_level = df.groupby("week_start").agg(
        revenue=("revenue", "first"),
        **{c: (c, "max") for c in CONTROL_COLS},
    )
    wide = wide.join(week_level)

    wide = wide.reset_index().rename(columns={"index": "week_start"})
    wide["week_start"] = pd.to_datetime(wide["week_start"]).dt.strftime("%Y-%m-%d")
    wide = wide.sort_values("week_start").reset_index(drop=True)

    print(f"Loaded {len(wide)} weeks across {len(CHANNELS)} channels")
    print(f"Date range: {wide['week_start'].min()} to {wide['week_start'].max()}")
    print(f"Total revenue: EUR {wide['revenue'].sum():,.0f}")
    spend_cols = [f"{ch}_spend" for ch in CHANNELS]
    print(f"Total spend:   EUR {wide[spend_cols].to_numpy().sum():,.0f}")
    return wide


# ── Model Specification ────────────────────────────────────────

def build_input_data(wide):
    """Build a Meridian InputData object from the wide weekly DataFrame.

    No geo column -> Meridian builds a single-geo (national) model.
    """
    builder = builder_lib.DataFrameInputDataBuilder(
        kpi_type=constants.REVENUE,
        default_kpi_column="revenue",
        default_time_column="week_start",
    )
    builder = (
        builder
        .with_kpi(wide, kpi_col="revenue", time_col="week_start")
        .with_controls(wide, control_cols=CONTROL_COLS, time_col="week_start")
        .with_media(
            wide,
            media_cols=[f"{ch}_impression" for ch in CHANNELS],
            media_spend_cols=[f"{ch}_spend" for ch in CHANNELS],
            media_channels=CHANNELS,
            time_col="week_start",
        )
    )
    return builder.build()


def build_model(input_data):
    """Configure priors + model spec and instantiate the Meridian model."""
    prior = prior_distribution.PriorDistribution(
        roi_m=tfp.distributions.LogNormal(
            ROI_PRIOR_MU, ROI_PRIOR_SIGMA, name=constants.ROI_M
        )
    )
    model_spec = spec.ModelSpec(
        prior=prior,
        max_lag=MAX_LAG,
        media_prior_type=constants.TREATMENT_PRIOR_TYPE_ROI,  # 'roi'
    )
    return model.Meridian(input_data=input_data, model_spec=model_spec)


# ── Sampling ───────────────────────────────────────────────────

def sample_model(mmm):
    """Draw prior + posterior samples (NUTS). This is the slow step."""
    print(f"\nSampling prior ({N_PRIOR} draws)...")
    mmm.sample_prior(N_PRIOR)

    print(f"Sampling posterior: {N_CHAINS} chains x {N_KEEP} kept draws "
          f"(adapt={N_ADAPT}, burnin={N_BURNIN})...")
    print("(This runs NUTS MCMC and can take several minutes.)")
    mmm.sample_posterior(
        n_chains=N_CHAINS,
        n_adapt=N_ADAPT,
        n_burnin=N_BURNIN,
        n_keep=N_KEEP,
        seed=SEED,
    )
    return mmm


# ── Results ────────────────────────────────────────────────────

def report_roi(mmm):
    """Extract posterior ROI per channel and write a summary table."""
    az = analyzer.Analyzer(mmm)
    # shape: (n_chains, n_draws, n_channels) with geo aggregated away
    roi = np.asarray(az.roi(use_posterior=True, aggregate_geos=True))
    roi = roi.reshape(-1, roi.shape[-1])  # flatten chains x draws

    lo = (1 - CONFIDENCE) / 2 * 100
    hi = (1 + CONFIDENCE) / 2 * 100
    lines = []
    header = f"{'Channel':<10}{'ROI (median)':>14}{'90% CI':>22}{'P(ROI>1)':>11}"
    sep = "-" * len(header)
    lines += ["Meridian MMM — posterior ROI by channel", "=" * len(header), header, sep]
    for i, ch in enumerate(CHANNELS):
        s = roi[:, i]
        med, low, up = np.median(s), np.percentile(s, lo), np.percentile(s, hi)
        p_profit = float(np.mean(s > 1.0))
        lines.append(f"{ch:<10}{med:>14.2f}{f'[{low:.2f}, {up:.2f}]':>22}{p_profit:>11.0%}")
    lines.append("=" * len(header))

    table = "\n".join(lines)
    print("\n" + table)
    with open(os.path.join(OUTPUT_DIR, "roi_summary.txt"), "w") as f:
        f.write(table + "\n")
    print(f"\nROI summary written to {OUTPUT_DIR}/roi_summary.txt")


def write_model_summary(mmm):
    """Write Meridian's full HTML results summary (fit, R-hat, response curves)."""
    start = mmm.input_data.time.values[0]
    end = mmm.input_data.time.values[-1]
    summarizer.Summarizer(mmm).output_model_results_summary(
        "summary_output.html", OUTPUT_DIR, str(start), str(end)
    )
    print(f"Model results summary written to {OUTPUT_DIR}/summary_output.html")


def optimise_budget(mmm):
    """Reallocate the historical budget to maximise revenue, respecting saturation.

    Fixed-budget optimisation: keeps total spend the same as the observed period
    and shifts euros toward the channels with the best marginal return, bounded by
    each channel's response curve. Writes an HTML summary and prints the proposed
    per-channel spend shift.
    """
    results = optimizer.BudgetOptimizer(mmm).optimize()  # fixed_budget=True by default
    results.output_optimization_summary("optimization_output.html", OUTPUT_DIR)
    print(f"Budget optimisation summary written to {OUTPUT_DIR}/optimization_output.html")

    # Non-optimised (historical) vs optimised spend per channel.
    before = results.nonoptimized_data.spend.to_series()
    after = results.optimized_data.spend.to_series()
    header = f"{'Channel':<10}{'Current spend':>16}{'Optimised spend':>18}{'Change':>10}"
    lines = ["Budget reallocation (same total budget)", "=" * len(header), header, "-" * len(header)]
    for ch in before.index:
        b, a = float(before[ch]), float(after[ch])
        pct = (a - b) / b * 100 if b else float("nan")
        lines.append(f"{ch:<10}{b:>16,.0f}{a:>18,.0f}{pct:>9.0f}%")
    lines.append("=" * len(header))
    print("\n" + "\n".join(lines))


# ── Main ───────────────────────────────────────────────────────

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("=" * 60)
    print("Meridian MMM — GA4 Ecommerce (national, revenue-based)")
    print("=" * 60)

    wide = load_and_prep_data(DATA_FILE)
    input_data = build_input_data(wide)
    mmm = build_model(input_data)
    mmm = sample_model(mmm)
    report_roi(mmm)
    write_model_summary(mmm)
    optimise_budget(mmm)

    print(f"\nDone. All outputs in {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
