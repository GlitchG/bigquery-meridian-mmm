-- sql/02_kpi_prep.sql
-- Extract weekly ecommerce revenue from GA4 BigQuery export.
-- Uses the standard GA4 event schema. Adjust table names if you use a different setup.
-- If your KPI is not revenue (e.g. leads, subscriptions), modify the metric extraction.

WITH purchase_events AS (
  SELECT
    PARSE_DATE('%Y%m%d', event_date) AS event_date,
    ecommerce.purchase_revenue AS revenue,
    ecommerce.transaction_id,
    (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'session_id') AS session_id
  FROM `your_project.analytics_123456789.events_*`  -- replace with your GA4 events table
  WHERE event_name = 'purchase'
    AND _TABLE_SUFFIX BETWEEN '20240101' AND '20260101'  -- adjust to your date range
)

SELECT
  DATE_TRUNC(event_date, WEEK(MONDAY)) AS week_start,
  SUM(revenue) AS total_revenue,
  COUNT(DISTINCT transaction_id) AS transactions,
  SAFE_DIVIDE(SUM(revenue), COUNT(DISTINCT transaction_id)) AS avg_order_value,
  COUNT(DISTINCT session_id) AS sessions_with_purchase
FROM purchase_events
GROUP BY week_start
ORDER BY week_start;
