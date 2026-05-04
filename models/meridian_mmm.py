"""
Marketing Mix Model using Google Meridian.
Applied to GA4 ecommerce data with Bayesian inference.

NOTE: This is a conceptual template. The API calls below (set_adstock,
set_saturation, sample, get_trace, etc.) are illustrative only.
Google's actual Meridian library uses a different API surface.
See: https://github.com/google/meridian
Adapt this script to the real API before running in production.

Prerequisites:
    pip install -r requirements.txt
    # or: pip install git+https://github.com/google/meridian.git

Data: CSV export from BigQuery (see GUIDE.md Step 2.4 for the JOIN query)
"""

import pandas as pd
import numpy as np
import arviz as az
import matplotlib.pyplot as plt

# Meridian imports - these come from the google/meridian GitHub repo
try:
    from meridian.model import Meridian
    HAS_MERIDIAN = True
except ImportError:
    HAS_MERIDIAN = False
    print("WARNING: Meridian not installed. Install with:")
    print("   pip install git+https://github.com/google/meridian.git")
    print("   Then adapt this script to the real API before re-running.")
    exit(1)

# ── Configuration ──────────────────────────────────────────────

DATA_FILE = "mmm_input.csv"          # CSV exported from BigQuery
OUTPUT_DIR = "output/"               # Where to save plots and diagnostics
CHANNELS = ['tv', 'digital', 'search', 'social', 'tiktok', 'ooh']

# Adstock priors: how long does ad impact persist?
# Higher mean = longer carryover. Digital: 0.3-0.5, TV: 0.5-0.8.
ADSTOCK_MEAN = 0.5
ADSTOCK_SD = 0.2

# ROI priors: prior belief about return per euro spent
# If you have historical data, tighten these. Otherwise keep them wide.
ROI_PRIOR_MEAN = 2.0
ROI_PRIOR_SD = 1.5

# MCMC sampling
NUM_SAMPLES = 2000     # Posterior samples per chain
NUM_WARMUP = 1000      # Burn-in samples (discarded)
NUM_CHAINS = 4         # Independent chains for convergence diagnostics

# ── Data Loading ───────────────────────────────────────────────

def load_and_prep_data(csv_path):
    """Load the BigQuery CSV export and pivot into Meridian format."""
    df = pd.read_csv(csv_path, parse_dates=['week_start'])

    # Pivot spend: rows=weeks, columns=channels, values=spend
    spend_wide = df.pivot_table(
        index='week_start',
        columns='channel',
        values='spend',
        aggfunc='sum'
    ).fillna(0)

    # Ensure all channels exist (fill missing ones with zeros)
    for ch in CHANNELS:
        if ch not in spend_wide.columns:
            spend_wide[ch] = 0
    spend_wide = spend_wide[CHANNELS]

    # Revenue: aggregate to weekly
    revenue = df.groupby('week_start')['revenue'].sum()
    # Align with spend index
    revenue = revenue.reindex(spend_wide.index)

    # Control variables: aggregate by week
    controls = df.groupby('week_start').agg({
        'is_holiday': 'max',
        'is_black_friday_week': 'max',
        'is_summer': 'max',
        'is_promo_period': 'max',
        'month_num': 'first',
    }).reindex(spend_wide.index).fillna(0)

    print(f"Loaded {len(spend_wide)} weeks across {len(CHANNELS)} channels")
    print(f"Date range: {spend_wide.index.min().date()} to {spend_wide.index.max().date()}")
    print(f"Total revenue: €{revenue.sum():,.0f}")
    print(f"Total spend: €{spend_wide.sum().sum():,.0f}")

    return spend_wide, revenue, controls


# ── Model Specification ────────────────────────────────────────

def build_meridian_model(spend, revenue, controls):
    """
    Configure a Meridian model with:
    - Geometric adstock per channel
    - Hill saturation per channel
    - Control variables (seasonality, holidays)
    - ROI priors
    """

    # Initialise Meridian with data
    mmm = Meridian(
        KPI=revenue.values,
        media=spend.values,
        controls=controls.values if controls is not None else None,
        media_names=CHANNELS,
    )

    # Set adstock: geometric decay with prior
    mmm.set_adstock(
        model='geometric',
        prior_mean=ADSTOCK_MEAN,
        prior_sd=ADSTOCK_SD,
    )

    # Set saturation: Hill function (diminishing returns)
    mmm.set_saturation(model='hill')

    # Set ROI prior: regularising prior on channel coefficients
    mmm.set_roi_prior(
        mean=ROI_PRIOR_MEAN,
        sd=ROI_PRIOR_SD,
    )

    return mmm


# ── Sampling & Diagnostics ─────────────────────────────────────

def sample_model(mmm):
    """Run MCMC and return the fitted model."""
    print(f"\nRunning MCMC: {NUM_SAMPLES} samples × {NUM_CHAINS} chains...")
    print("(This may take a few minutes — watch the progress bars)")

    mmm.sample(
        num_samples=NUM_SAMPLES,
        num_warmup=NUM_WARMUP,
        num_chains=NUM_CHAINS,
    )

    return mmm


def run_diagnostics(mmm):
    """Check convergence and produce diagnostic plots."""
    import os
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    trace = mmm.get_trace()

    # R-hat (convergence diagnostic)
    rhat = az.rhat(trace)
    rhat_summary = rhat.to_dataframe()

    with open(f"{OUTPUT_DIR}/diagnostics_summary.txt", "w") as f:
        f.write("Meridian MMM — Convergence Diagnostics\n")
        f.write("=" * 50 + "\n\n")
        f.write(f"Chains: {NUM_CHAINS}\n")
        f.write(f"Samples per chain: {NUM_SAMPLES}\n")
        f.write(f"Warmup: {NUM_WARMUP}\n\n")
        f.write("R-hat values (should be < 1.05, ideally < 1.01):\n")
        f.write(str(rhat_summary))
        f.write("\n\n")

        high_rhat = rhat_summary[rhat_summary > 1.05].dropna()
        if len(high_rhat) > 0:
            f.write("WARNING: Some parameters have R-hat > 1.05:\n")
            f.write(str(high_rhat))
            f.write("\nConsider increasing NUM_SAMPLES or NUM_WARMUP.\n")
        else:
            f.write("All R-hat values < 1.05. Model has converged.\n")

    print(f"Diagnostics saved to {OUTPUT_DIR}/diagnostics_summary.txt")

    # Trace plots
    az.plot_trace(trace, compact=True)
    plt.suptitle("Meridian MMM — Trace Plots", fontsize=14)
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/trace_plots.png", dpi=150)
    plt.close()
    print(f"Trace plots saved to {OUTPUT_DIR}/trace_plots.png")

    # Effective sample size
    ess = az.ess(trace)
    print(f"\nEffective sample size (min): {ess.min().values:.0f}")
    print(f"Effective sample size (median): {np.median(ess.values):.0f}")

    return rhat


# ── Results ────────────────────────────────────────────────────

def plot_results(mmm, spend):
    """Produce ROI distributions and response curves."""

    # ROI posterior distributions
    roi_samples = mmm.get_roi_samples()

    fig, axes = plt.subplots(len(CHANNELS), 1, figsize=(8, 3 * len(CHANNELS)))
    if len(CHANNELS) == 1:
        axes = [axes]

    for i, ch in enumerate(CHANNELS):
        ch_roi = roi_samples[:, i]
        median = np.median(ch_roi)
        lower = np.percentile(ch_roi, 5)
        upper = np.percentile(ch_roi, 95)
        prob_profitable = np.mean(ch_roi > 1.0)

        axes[i].hist(ch_roi, bins=50, color='steelblue', edgecolor='white', alpha=0.8)
        axes[i].axvline(1.0, color='red', linestyle='--', alpha=0.5, label='Breakeven')
        axes[i].axvline(median, color='darkblue', linestyle='-', alpha=0.8, label=f'Median: {median:.2f}')
        axes[i].axvline(lower, color='grey', linestyle=':', alpha=0.5)
        axes[i].axvline(upper, color='grey', linestyle=':', alpha=0.5)
        axes[i].set_title(
            f"{ch}: ROI = {median:.2f}  [{lower:.2f}, {upper:.2f}]  P(ROI>1) = {prob_profitable:.0%}"
        )
        axes[i].legend(fontsize=8)

    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/roi_posteriors.png", dpi=150)
    plt.close()
    print(f"ROI posteriors saved to {OUTPUT_DIR}/roi_posteriors.png")

    # Response curves
    mmm.plot_response_curves()
    plt.savefig(f"{OUTPUT_DIR}/response_curves.png", dpi=150)
    plt.close()
    print(f"Response curves saved to {OUTPUT_DIR}/response_curves.png")

    # Print summary table
    print("\n" + "=" * 70)
    print(f"{'Channel':<12} {'ROI (median)':>12} {'90% CI':>20} {'P(ROI>1)':>10}")
    print("-" * 70)
    for i, ch in enumerate(CHANNELS):
        ch_roi = roi_samples[:, i]
        median = np.median(ch_roi)
        lower = np.percentile(ch_roi, 5)
        upper = np.percentile(ch_roi, 95)
        prob = np.mean(ch_roi > 1.0)
        print(f"{ch:<12} {median:>12.2f} [{lower:.2f}, {upper:.2f}]   {prob:>8.0%}")
    print("=" * 70)


# ── Main ───────────────────────────────────────────────────────

if __name__ == "__main__":
    import os
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 60)
    print("Meridian MMM — GA4 Ecommerce")
    print("=" * 60)

    # 1. Load data
    spend, revenue, controls = load_and_prep_data(DATA_FILE)

    # 2. Build model
    mmm = build_meridian_model(spend, revenue, controls)

    # 3. Sample
    mmm = sample_model(mmm)

    # 4. Diagnostics
    run_diagnostics(mmm)

    # 5. Results
    plot_results(mmm, spend)

    print(f"\nDone. All outputs in {OUTPUT_DIR}/")
