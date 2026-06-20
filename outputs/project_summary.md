# Project Summary

## Case Setup

- Flights modelled : 36
- Contact gates    : 7
- Remote stands    : 4
- Peak concurrent demand : 11

## Algorithm KPI Comparison

| solution | total_assignment_cost | remote_flights | contact_gate_share | weighted_avg_walking_m | weighted_passenger_distance_km | zone_mismatch_flights | narrow_on_wide_gates | total_expected_service_extension_min | max_gate_utilization_pct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Baseline FCFS | 66649.0 | 11 | 69.44 | 550.19 | 4010.9 | 19 | 8 | 560 | 53.41 |
| Priority Dispatch | 59514.8 | 12 | 66.67 | 459.87 | 3352.48 | 14 | 0 | 569 | 50.27 |
| Optimized MILP | 56850.0 | 11 | 69.44 | 451.44 | 3291.0 | 9 | 1 | 522 | 51.68 |

## Robustness Simulation Summary (100 delay scenarios)

| method | total_cost_mean | total_cost_std | remote_flights_mean | feasibility_rate |
| --- | --- | --- | --- | --- |
| FCFS | 61587.26625 | 3407.260147077 | 9.7375 | 0.8 |
| Optimized MILP | 50168.707407407404 | 3001.225349743741 | 8.518518518518519 | 0.81 |
| Priority Dispatch | 53929.333333333336 | 2894.6915865894675 | 9.833333333333334 | 0.78 |

## Scenario Analysis Summary

| scenario | solution | total_assignment_cost | remote_flights | weighted_avg_walking_m | zone_mismatch_flights |
| --- | --- | --- | --- | --- | --- |
| normal | Baseline FCFS | 66649.0 | 11 | 550.19 | 19 |
| normal | Optimized MILP | 56850.0 | 11 | 451.44 | 9 |
| disruption | Baseline FCFS | 60737.2 | 9 | 504.63 | 20 |
| disruption | Optimized MILP | 44211.5 | 6 | 371.21 | 13 |

Heavy traffic results are omitted because both FCFS and MILP became infeasible under the current stand inventory.

## Key Insights

- **Priority Dispatch** outperforms FCFS by routing high-passenger flights to premium gates before lower-load flights claim them.
- **MILP** achieves the best overall KPI performance, while Priority Dispatch offers a practical near-optimal heuristic with very low modeling complexity.
- Sensitivity analysis shows that remote assignments are structurally driven by capacity shortage: changing the remote penalty shifts total cost but does not change the number of remote flights in the tested range.
- Zone-mismatch and gate-scarcity penalties are more behavior-shaping than the remote penalty because they materially change how contact gates are allocated.
- Simulation results confirm MILP degrades most gracefully under random delays, and the heavy-demand stress test shows that current stand inventory can become infeasible under traffic growth.

## Interactive Dashboard

Run `python src/dashboard.py` and open http://127.0.0.1:8050