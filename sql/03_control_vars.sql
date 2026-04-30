-- sql/03_control_vars.sql
-- Generate weekly control variables for seasonality, holidays, and promotions.
-- Run this for your date range. The output is a week-level table with boolean flags.
-- Meridian uses these to separate seasonal effects from true channel impact.

WITH weeks AS (
  SELECT week_start
  FROM UNNEST(GENERATE_DATE_ARRAY('2024-01-01', '2026-01-01', INTERVAL 1 WEEK)) AS week_start
)

SELECT
  week_start,

  -- Portuguese national holidays (fixed dates — add your own country's holidays)
  (EXTRACT(MONTH FROM week_start) = 1 AND EXTRACT(DAY FROM week_start) = 1)   -- Ano Novo
  OR (EXTRACT(MONTH FROM week_start) = 4 AND EXTRACT(DAY FROM week_start) = 25)  -- 25 de Abril
  OR (EXTRACT(MONTH FROM week_start) = 5 AND EXTRACT(DAY FROM week_start) = 1)   -- Dia do Trabalhador
  OR (EXTRACT(MONTH FROM week_start) = 6 AND EXTRACT(DAY FROM week_start) = 10)  -- Dia de Portugal
  OR (EXTRACT(MONTH FROM week_start) = 8 AND EXTRACT(DAY FROM week_start) = 15)  -- Assunção de N. Sra.
  OR (EXTRACT(MONTH FROM week_start) = 10 AND EXTRACT(DAY FROM week_start) = 5)  -- Implantação da República
  OR (EXTRACT(MONTH FROM week_start) = 11 AND EXTRACT(DAY FROM week_start) = 1)  -- Todos os Santos
  OR (EXTRACT(MONTH FROM week_start) = 12 AND EXTRACT(DAY FROM week_start) = 1)  -- Restauração
  OR (EXTRACT(MONTH FROM week_start) = 12 AND EXTRACT(DAY FROM week_start) = 8)  -- Imaculada Conceição
  OR (EXTRACT(MONTH FROM week_start) = 12 AND EXTRACT(DAY FROM week_start) = 25) -- Natal
  AS is_holiday_week,

  -- Black Friday week (4th Friday of November ± a few days)
  (EXTRACT(MONTH FROM week_start) = 11
   AND EXTRACT(DAY FROM week_start) BETWEEN 20 AND 30) AS is_black_friday_week,

  -- Summer period (July-August): many businesses see seasonal shifts
  (EXTRACT(MONTH FROM week_start) IN (7, 8)) AS is_summer,

  -- December holiday season
  (EXTRACT(MONTH FROM week_start) = 12) AS is_december,

  -- Custom promo period flag — set based on your own promo calendar
  FALSE AS is_promo_period,  -- override with your actual promo dates

  -- Month number (1-12) for residual seasonality
  EXTRACT(MONTH FROM week_start) AS month_num,

  -- Year
  EXTRACT(YEAR FROM week_start) AS year_num

FROM weeks
ORDER BY week_start;
