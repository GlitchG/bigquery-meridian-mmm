# Architecture Decisions — bigquery-meridian-mmm

| Date | Decision | Rationale | Trade-offs |
|------|----------|-----------|------------|
| 2026-04 | Google Meridian over custom Bayesian model | Meridian is Google's production MMM framework used by major advertisers. Using it shows familiarity with industry-standard tools, not just theoretical knowledge. | Heavier dependency (PyMC + JAX). Installation is non-trivial (requires C compiler). |
| 2026-04 | Bayesian over frequentist | Full posterior distributions for ROI give clients credible intervals, not just point estimates. P(ROI>1) is directly interpretable by non-technical stakeholders. | Slower to run (MCMC vs OLS). Requires convergence diagnostics. More complex to explain. |
| 2026-04 | SQL data prep, Python modelling | Separation of concerns: analysts can inspect and modify SQL without touching Python. BigQuery does the heavy lifting on GA4's nested event data. | Requires BigQuery access. Two languages to maintain. |
| 2026-04 | GUIDE.md as separate doc, not just docstrings | README is for "what and why." GUIDE is for "how." Keeps README scannable while providing full walkthrough for evaluation. | Two docs to keep in sync. GUIDE is ~200 lines; manageable. |
| 2026-04-30 | Split from simple-marketing-mix-model | The original repo was named "meridian" but used no Meridian code. Renamed to simple-marketing-mix-model. This is the actual Meridian implementation. | Two repos to maintain. Clear separation of "quick check" vs "production MMM." |
| 2026-04-30 | Portuguese holiday controls in SQL | Default control variables target Portuguese/European market. Non-Portuguese users edit the holiday list. | Slightly less universal. But default that works for Gleb's client base is better than generic. |
