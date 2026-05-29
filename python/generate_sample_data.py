"""
Generate a synthetic MMM dataset for the Meridian model.

This produces `mmm_input.csv` in the SAME LONG FORMAT the BigQuery SQL
pipeline emits (one row per week per channel), so the model script's
load/pivot step is exercised exactly as it would be on real data.

The data is built from a KNOWN ground truth — each channel has a true
ROI, adstock decay, and saturation point baked in — so after fitting you
can check that Meridian recovers numbers close to these:

    channel   true_roi   adstock_decay   half_saturation (weekly spend)
    search       3.0         0.30            12,000
    tv           2.4         0.70            40,000
    digital      1.8         0.40            18,000
    tiktok       1.5         0.50            10,000
    ooh          1.2         0.60            25,000
    social       0.9         0.45            14,000

Revenue = baseline + seasonality/holiday effects + sum of channel
contributions + noise. A channel's contribution is
    true_roi * saturate(adstock(spend))
scaled so that, integrated over the period, incremental revenue / spend
≈ true_roi.

Run:
    python python/generate_sample_data.py
    # writes mmm_input.csv next to the SQL pipeline output
"""

import numpy as np
import pandas as pd

SEED = 42
N_WEEKS = 156  # 3 years — Meridian's recommended minimum for a national model
START = "2023-01-02"  # a Monday

# channel -> (true_roi, adstock_decay, half_saturation_spend, base_weekly_spend)
CHANNELS = {
    "search":  (3.0, 0.30, 12_000, 10_000),
    "tv":      (2.4, 0.70, 40_000, 30_000),
    "digital": (1.8, 0.40, 18_000, 15_000),
    "tiktok":  (1.5, 0.50, 10_000,  6_000),
    "ooh":     (1.2, 0.60, 25_000, 12_000),
    "social":  (0.9, 0.45, 14_000,  9_000),
}

# rough cost-per-thousand-impressions per channel, used to derive impressions
CPM = {"search": 4.0, "tv": 8.0, "digital": 3.5, "tiktok": 5.0, "ooh": 6.0, "social": 4.5}

BASELINE_WEEKLY_REVENUE = 250_000
NOISE_SD_FRAC = 0.05  # gaussian noise as a fraction of expected revenue


def geometric_adstock(x: np.ndarray, decay: float) -> np.ndarray:
    """Carryover: each week inherits `decay` * the previous (adstocked) week."""
    out = np.zeros_like(x, dtype=float)
    out[0] = x[0]
    for t in range(1, len(x)):
        out[t] = x[t] + decay * out[t - 1]
    return out


def hill_saturate(x: np.ndarray, half: float) -> np.ndarray:
    """Diminishing returns: 0 at 0 spend, -> 1 as spend grows, 0.5 at `half`."""
    return x / (x + half)


def main() -> None:
    rng = np.random.default_rng(SEED)
    weeks = pd.date_range(START, periods=N_WEEKS, freq="W-MON")

    month = weeks.month.to_numpy()
    day = weeks.day.to_numpy()

    # control flags (mirror sql/03_control_vars.sql)
    is_holiday = np.isin(month, [12]) & (day >= 22)  # Christmas week
    is_black_friday = (month == 11) & (day >= 20) & (day <= 30)
    is_summer = np.isin(month, [7, 8])
    is_promo = rng.random(N_WEEKS) < 0.10  # ~10% of weeks are promo weeks

    # seasonality multiplier on baseline revenue
    season = (
        1.0
        + 0.25 * is_black_friday
        + 0.15 * is_holiday
        - 0.10 * is_summer
        + 0.08 * is_promo
        + 0.05 * np.sin(2 * np.pi * np.arange(N_WEEKS) / 52.0)  # annual cycle
    )

    revenue = BASELINE_WEEKLY_REVENUE * season

    spend_by_channel: dict[str, np.ndarray] = {}
    contribution_by_channel: dict[str, np.ndarray] = {}

    for ch, (true_roi, decay, half, base) in CHANNELS.items():
        # spend wanders around its base with a slow trend + weekly variation,
        # and gets a bump on promo / Black Friday weeks
        trend = np.linspace(0.85, 1.15, N_WEEKS)
        wiggle = 1.0 + 0.20 * rng.standard_normal(N_WEEKS)
        promo_bump = 1.0 + 0.30 * is_promo + 0.40 * is_black_friday
        spend = np.clip(base * trend * wiggle * promo_bump, 0, None)

        adstocked = geometric_adstock(spend, decay)
        sat = hill_saturate(adstocked, half)

        # Scale contribution so that incremental revenue / spend ≈ true_roi.
        # mean(sat) is the average saturation level; dividing by it makes the
        # period-level ROI land on true_roi regardless of the saturation shape.
        scale = true_roi * spend.mean() / max(sat.mean(), 1e-9)
        contribution = scale * sat

        spend_by_channel[ch] = spend
        contribution_by_channel[ch] = contribution
        revenue = revenue + contribution

    # additive gaussian noise
    revenue = revenue + rng.normal(0, NOISE_SD_FRAC * revenue.mean(), N_WEEKS)
    revenue = np.clip(revenue, 0, None)

    # ── emit LONG format (one row per week per channel) ──
    rows = []
    for ch, spend in spend_by_channel.items():
        impressions = np.round(spend / CPM[ch] * 1000).astype(int)
        clicks = np.round(impressions * rng.uniform(0.005, 0.03, N_WEEKS)).astype(int)
        for i, wk in enumerate(weeks):
            rows.append(
                {
                    "week_start": wk.date().isoformat(),
                    "channel": ch,
                    "spend": round(float(spend[i]), 2),
                    "impressions": int(impressions[i]),
                    "clicks": int(clicks[i]),
                    # revenue is a WEEK-level value, repeated on each channel row
                    # (this matches what a JOIN of the spend + KPI tables yields)
                    "revenue": round(float(revenue[i]), 2),
                    "is_holiday": int(is_holiday[i]),
                    "is_black_friday_week": int(is_black_friday[i]),
                    "is_summer": int(is_summer[i]),
                    "is_promo_period": int(is_promo[i]),
                    "month_num": int(weeks[i].month),
                }
            )

    df = pd.DataFrame(rows).sort_values(["week_start", "channel"]).reset_index(drop=True)
    df.to_csv("mmm_input.csv", index=False)

    # ── report the ground truth so the README/GUIDE can reference it ──
    print(f"Wrote mmm_input.csv: {len(df)} rows, {N_WEEKS} weeks, {len(CHANNELS)} channels")
    print(f"Date range: {df['week_start'].min()} to {df['week_start'].max()}")
    print(f"Total revenue: EUR {revenue.sum():,.0f}")
    print()
    print("Ground-truth ROI baked into the data (Meridian should recover ~these):")
    print(f"{'channel':<10}{'true_roi':>10}{'total_spend':>14}{'incr_revenue':>14}")
    for ch, (true_roi, *_rest) in CHANNELS.items():
        sp = spend_by_channel[ch].sum()
        contrib = contribution_by_channel[ch].sum()
        print(f"{ch:<10}{true_roi:>10.2f}{sp:>14,.0f}{contrib:>14,.0f}")


if __name__ == "__main__":
    main()
