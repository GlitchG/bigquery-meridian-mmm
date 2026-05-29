# `output/`

This folder is populated by `models/meridian_mmm.py`. Running it produces:

- `roi_summary.txt` — posterior ROI per channel (median, 90% CI, P(ROI>1))
- `summary_output.html` — Meridian's full report: model fit, R-hat, response curves

Those generated files are git-ignored; only the committed example below is tracked.

## `example_roi_summary.txt`

A **representative** ROI table for the synthetic dataset (`generate_sample_data.py`),
showing the shape and the kind of numbers a converged fit produces. It is hand-written
to sit near the generator's baked-in ground truth (search ≈ 3.0, tv ≈ 2.4, digital ≈ 1.8,
tiktok ≈ 1.5, ooh ≈ 1.2, social ≈ 0.9) — it is **not** a captured run, because the MMM fit
requires TensorFlow (Python 3.10–3.12) and several minutes of MCMC. Run the script yourself
to get real, slightly different numbers.
