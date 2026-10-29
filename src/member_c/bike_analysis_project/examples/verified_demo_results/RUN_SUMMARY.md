# Run summary

Synthetic demonstration: True

Input rows: 3405; selected stations: 4
Input clock convention: SYNTHETIC local clock; no real city or timezone claims

## Validation-selected model results

| Target | Selected on validation | Test MAE | Test RMSE |
|---|---|---:|---:|
| departures | hgb_calendar | 0.7985 | 1.0837 |
| arrivals | hgb_calendar | 0.8384 | 1.1160 |

## Boundaries

- Forecasts are rolling one-hour-ahead predictions, NOT a day-ahead plan.
- Candidates and simulation policies are fixed; the chosen model uses validation MAE only.
- All model comparisons use the same complete-feature rows; warm-up/gap exclusions are logged.
- Cohort selection uses data before the earliest rolling-validation window.
- Nominal 90% intervals have no guaranteed coverage; see empirical coverage and width.
- Coverage assumptions must be audited. Calendar-normalized overall counts are descriptive, not corrected demand.
- Simulation uses assumed capacity/inventory and observed trips as fixed requests.
- Hourly moves are instantaneous, bikes are pooled, and bike-km is only a cost proxy.
- Overflow bikes remain in a holding pool and are not automatically recirculated.
- Boundary arrivals/departures are explicitly logged; no actual unmet demand or financial savings are inferred.
- A single month cannot establish annual seasonality or generalization to other cities.