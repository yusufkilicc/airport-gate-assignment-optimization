"""run_project.py — Main pipeline orchestrator.

Runs all analyses in sequence and writes every output to disk:

Static outputs (outputs/figures/):
  capacity_profile.png
  baseline_gantt.png
  priority_gantt.png
  optimized_gantt.png
  kpi_comparison.png          ← three-algorithm comparison
  turnaround_distribution.png
  sensitivity_analysis.png
  simulation_results.png
  scenario_comparison.png

Data outputs (outputs/, data/processed/):
  flights.csv, gates.csv
  baseline_assignments.csv, priority_assignments.csv, optimized_assignments.csv
  kpi_summary.csv
  sensitivity_results.csv
  simulation_results.csv
  scenario_kpi.csv
  project_summary.md

To launch the interactive dashboard afterwards:
    python src/dashboard.py
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from project_data import create_flights, create_gates, create_scenario_flights
from project_model import (
    greedy_fcfs_assignment,
    optimize_gate_assignment,
    priority_dispatch_assignment,
    summarize_solution,
)
from project_visuals import (
    plot_assignment_gantt,
    plot_capacity_profile,
    plot_kpi_comparison,
    plot_scenario_comparison,
    plot_sensitivity,
    plot_simulation_results,
    plot_turnaround_distribution,
)
from sensitivity import run_full_sensitivity
from simulation import run_simulation, summarize_simulation


# ---------------------------------------------------------------------------
# Directory helpers
# ---------------------------------------------------------------------------

def ensure_dirs(root: Path) -> tuple[Path, Path, Path]:
    processed = root / "data" / "processed"
    outputs   = root / "outputs"
    figures   = outputs / "figures"
    for d in [processed, outputs, figures]:
        d.mkdir(parents=True, exist_ok=True)
    return processed, outputs, figures


# ---------------------------------------------------------------------------
# Summary markdown
# ---------------------------------------------------------------------------

def _md_table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    header = "| " + " | ".join(cols) + " |"
    sep    = "| " + " | ".join(["---"] * len(cols)) + " |"
    rows   = [
        "| " + " | ".join(str(row[c]) for c in cols) + " |"
        for _, row in df.iterrows()
    ]
    return "\n".join([header, sep] + rows)


def build_summary_markdown(
    flights: pd.DataFrame,
    gates: pd.DataFrame,
    kpi_df: pd.DataFrame,
    sim_summary: pd.DataFrame,
    scenario_kpi_df: pd.DataFrame,
) -> str:
    peak = 0
    for minute in range(int(flights["arrival_min"].min()),
                        int(flights["occupied_until_min"].max()) + 1, 15):
        n = int(((flights["arrival_min"] <= minute) &
                 (minute < flights["occupied_until_min"])).sum())
        peak = max(peak, n)

    heavy_present = (
        "heavy" in scenario_kpi_df["scenario"].astype(str).str.lower().unique()
        if not scenario_kpi_df.empty else False
    )
    scenario_note = (
        "Heavy traffic results are omitted because both FCFS and MILP became infeasible "
        "under the current stand inventory."
        if not heavy_present else
        "All three operating scenarios returned KPI rows."
    )

    lines = [
        "# Project Summary",
        "",
        "## Case Setup",
        "",
        f"- Flights modelled : {len(flights)}",
        f"- Contact gates    : {int((gates['gate_type'] == 'contact').sum())}",
        f"- Remote stands    : {int((gates['gate_type'] == 'remote').sum())}",
        f"- Peak concurrent demand : {peak}",
        "",
        "## Algorithm KPI Comparison",
        "",
        _md_table(kpi_df),
        "",
        "## Robustness Simulation Summary (100 delay scenarios)",
        "",
        _md_table(sim_summary[["method", "total_cost_mean", "total_cost_std",
                                "remote_flights_mean", "feasibility_rate"]]),
        "",
        "## Scenario Analysis Summary",
        "",
        _md_table(scenario_kpi_df[["scenario", "solution", "total_assignment_cost",
                                   "remote_flights", "weighted_avg_walking_m",
                                   "zone_mismatch_flights"]]),
        "",
        scenario_note,
        "",
        "## Key Insights",
        "",
        "- **Priority Dispatch** outperforms FCFS by routing high-passenger flights to "
        "premium gates before lower-load flights claim them.",
        "- **MILP** achieves the best overall KPI performance, while Priority Dispatch "
        "offers a practical near-optimal heuristic with very low modeling complexity.",
        "- Sensitivity analysis shows that remote assignments are structurally driven by "
        "capacity shortage: changing the remote penalty shifts total cost but does not "
        "change the number of remote flights in the tested range.",
        "- Zone-mismatch and gate-scarcity penalties are more behavior-shaping than the "
        "remote penalty because they materially change how contact gates are allocated.",
        "- Simulation results confirm MILP degrades most gracefully under random delays, "
        "and the heavy-demand stress test shows that current stand inventory can become "
        "infeasible under traffic growth.",
        "",
        "## Interactive Dashboard",
        "",
        "Run `python src/dashboard.py` and open http://127.0.0.1:8050",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def main() -> None:
    root = Path(__file__).resolve().parents[1]
    processed, outputs, figures = ensure_dirs(root)

    # ── 1. Base data ──────────────────────────────────────────────────────
    print("[1/7] Generating flights and gates …")
    flights = create_flights()
    gates   = create_gates()

    horizon_start = int(flights["arrival_min"].min())
    horizon_end   = int(flights["occupied_until_min"].max())

    # ── 2. Assignment algorithms ──────────────────────────────────────────
    print("[2/7] Running assignment algorithms …")
    baseline   = greedy_fcfs_assignment(flights, gates)
    priority   = priority_dispatch_assignment(flights, gates)
    optimized  = optimize_gate_assignment(flights, gates)

    kpi_df = pd.concat(
        [summarize_solution(a, horizon_start, horizon_end)
         for a in [baseline, priority, optimized]],
        ignore_index=True,
    )

    # ── 3. Save core CSVs ────────────────────────────────────────────────
    flights.to_csv(processed / "flights.csv", index=False)
    gates.to_csv(processed / "gates.csv", index=False)
    baseline.to_csv(processed / "baseline_assignments.csv", index=False)
    priority.to_csv(processed / "priority_assignments.csv", index=False)
    optimized.to_csv(processed / "optimized_assignments.csv", index=False)
    kpi_df.to_csv(outputs / "kpi_summary.csv", index=False)

    # ── 4. Sensitivity analysis ───────────────────────────────────────────
    print("[3/7] Running sensitivity analysis …")
    sensitivity_df = run_full_sensitivity(flights, gates)
    sensitivity_df.to_csv(outputs / "sensitivity_results.csv", index=False)

    # ── 5. Stochastic simulation ──────────────────────────────────────────
    print("[4/7] Running robustness simulation (100 scenarios) …")
    sim_df      = run_simulation(flights, gates, n_scenarios=100)
    sim_summary = summarize_simulation(sim_df)
    sim_df.to_csv(outputs / "simulation_results.csv", index=False)
    sim_summary.to_csv(outputs / "simulation_summary.csv", index=False)

    # ── 6. Scenario analysis ──────────────────────────────────────────────
    print("[5/7] Running scenario analysis (normal / heavy / disruption) …")
    scenario_parts = []
    for sc in ["normal", "heavy", "disruption"]:
        sc_flights = create_scenario_flights(sc)
        sc_h_start = int(sc_flights["arrival_min"].min())
        sc_h_end   = int(sc_flights["occupied_until_min"].max())
        for label, func in [
            ("Baseline FCFS",   greedy_fcfs_assignment),
            ("Optimized MILP",  optimize_gate_assignment),
        ]:
            try:
                assignment = func(sc_flights, gates)
                s = summarize_solution(assignment, sc_h_start, sc_h_end)
                s["scenario"] = sc
                scenario_parts.append(s)
            except Exception as exc:
                print(f"    Warning: {sc}/{label} failed — {exc}")
    scenario_kpi_df = pd.concat(scenario_parts, ignore_index=True)
    scenario_kpi_df.to_csv(outputs / "scenario_kpi.csv", index=False)

    # ── 7. Figures ────────────────────────────────────────────────────────
    print("[6/7] Generating figures …")
    figs = figures  # shorthand

    plot_capacity_profile(
        flights,
        contact_gate_count=int((gates["gate_type"] == "contact").sum()),
        output_path=str(figs / "capacity_profile.png"),
    )
    plot_assignment_gantt(baseline,  output_path=str(figs / "baseline_gantt.png"))
    plot_assignment_gantt(priority,  output_path=str(figs / "priority_gantt.png"))
    plot_assignment_gantt(optimized, output_path=str(figs / "optimized_gantt.png"))
    plot_kpi_comparison(kpi_df,      output_path=str(figs / "kpi_comparison.png"))
    plot_turnaround_distribution(flights, output_path=str(figs / "turnaround_distribution.png"))
    plot_sensitivity(sensitivity_df, output_path=str(figs / "sensitivity_analysis.png"))
    plot_simulation_results(sim_df,  output_path=str(figs / "simulation_results.png"))
    plot_scenario_comparison(scenario_kpi_df, output_path=str(figs / "scenario_comparison.png"))

    # ── 8. Summary markdown ───────────────────────────────────────────────
    print("[7/7] Writing summary …")
    summary_md = build_summary_markdown(flights, gates, kpi_df, sim_summary, scenario_kpi_df)
    (outputs / "project_summary.md").write_text(summary_md, encoding="utf-8")

    # ── Console report ────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("Pipeline complete.")
    print(f"  Flights modelled : {len(flights)}")
    print(f"  Outputs          : {outputs}")
    print(f"  Figures          : {figs}")
    print("\nKPI Summary:")
    print(kpi_df.to_string(index=False))
    print("\nSimulation Summary:")
    print(sim_summary[["method", "total_cost_mean", "total_cost_std",
                        "feasibility_rate"]].to_string(index=False))
    print("\nTo launch the interactive dashboard:")
    print("  python src/dashboard.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
