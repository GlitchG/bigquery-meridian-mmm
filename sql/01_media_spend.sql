-- sql/01_media_spend.sql
-- Aggregate weekly media spend by channel.
-- Assumes media_spend table exists (see 00_setup_media_tables.sql for schema).
-- Adjust date range and channels to match your data.

SELECT
  week_start,
  channel,
  SUM(spend) AS spend,
  SUM(impressions) AS impressions,
  SUM(clicks) AS clicks
FROM `your_project.your_dataset.media_spend`
WHERE week_start BETWEEN '2024-01-01' AND '2026-01-01'  -- adjust to your data range
  AND channel IN ('facebook', 'google', 'tiktok', 'tv', 'radio', 'ooh')  -- your channels
GROUP BY week_start, channel
ORDER BY week_start, channel;
