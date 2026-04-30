-- sql/00_setup_media_tables.sql
-- Schema for importing ad platform spend data into BigQuery.
-- Run this once to create the table, then import your data via CSV upload or scheduled pipeline.
--
-- Expected source: Facebook Ads, Google Ads, TikTok Ads, TV bookings, radio bookings, OOH bookings
-- Granularity: weekly, per channel

CREATE TABLE IF NOT EXISTS `your_project.your_dataset.media_spend` (
  week_start DATE NOT NULL,        -- First day of the week (Monday)
  channel STRING NOT NULL,         -- 'facebook', 'google', 'tiktok', 'tv', 'radio', 'ooh'
  spend FLOAT64 NOT NULL,          -- Total spend in EUR for the week
  impressions INT64,               -- Optional: total impressions
  clicks INT64,                    -- Optional: total clicks
  source STRING                    -- Optional: 'facebook_ads_export', 'google_ads_report', etc.
)
PARTITION BY week_start
CLUSTER BY channel;

-- Index for performance
-- BigQuery doesn't support CREATE INDEX; clustering on channel handles this

-- Example insert (replace with your actual data pipeline):
-- INSERT INTO media_spend VALUES
--   ('2024-01-01', 'facebook', 1500.00, 450000, 3200, 'facebook_ads_export'),
--   ('2024-01-01', 'google', 2200.00, 180000, 5600, 'google_ads_report'),
--   ...
