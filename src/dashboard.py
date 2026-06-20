"""dashboard.py — Interactive Plotly/Dash application.

Runs a local web server with four tabs:
  Tab 1 — Solution Comparison: interactive Gantt + KPI bars for all 3 algorithms
  Tab 2 — Sensitivity Analysis: parameter sweep line charts
  Tab 3 — Robustness Simulation: box plots from 100 delay scenarios
  Tab 4 — Scenario Analysis: normal / heavy / disruption comparison

Usage:
    cd src
    python dashboard.py

Then open  http://127.0.0.1:8050  in your browser.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make sure imports resolve when run from /src
sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from project_data import create_flights, create_gates, create_scenario_flights
from project_model import (
    CostWeights,
    greedy_fcfs_assignment,
    optimize_gate_assignment,
    priority_dispatch_assignment,
    summarize_solution,
)
from sensitivity import run_full_sensitivity
from simulation import run_simulation, summarize_simulation

# ---------------------------------------------------------------------------
# Colour palette (consistent with static charts)
# ---------------------------------------------------------------------------
COLORS = {
    "Baseline FCFS":    "#CC5A3C",
    "Priority Dispatch":"#E8A838",
    "Optimized MILP":   "#1F5E7A",
    "contact":          "#2A7F62",
    "remote":           "#D78C1F",
    "normal":           "#1F5E7A",
    "heavy":            "#CC5A3C",
    "disruption":       "#E8A838",
}
METHOD_ORDER = ["Baseline FCFS", "Priority Dispatch", "Optimized MILP"]

# ---------------------------------------------------------------------------
# Data preparation (runs once at startup)
# ---------------------------------------------------------------------------

ROOT      = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
OUTPUTS   = ROOT / "outputs"

# Files written by run_project.py. If they all exist we load them (instant
# startup, the right behaviour for a deployed web app); otherwise we compute
# everything live (first local run / regeneration).
_CACHE = {
    "flights":     PROCESSED / "flights.csv",
    "gates":       PROCESSED / "gates.csv",
    "baseline":    PROCESSED / "baseline_assignments.csv",
    "priority":    PROCESSED / "priority_assignments.csv",
    "optimized":   PROCESSED / "optimized_assignments.csv",
    "kpi":         OUTPUTS / "kpi_summary.csv",
    "sensitivity": OUTPUTS / "sensitivity_results.csv",
    "simulation":  OUTPUTS / "simulation_results.csv",
    "scenario":    OUTPUTS / "scenario_kpi.csv",
}


def _compute_all() -> dict:
    """Run the full pipeline in-process (used when no cached CSVs are present)."""
    print("Preparing data (live compute) …")
    flights = create_flights()
    gates   = create_gates()

    print("  Running assignment algorithms …")
    baseline  = greedy_fcfs_assignment(flights, gates)
    priority  = priority_dispatch_assignment(flights, gates)
    optimized = optimize_gate_assignment(flights, gates)

    h_start = int(flights["arrival_min"].min())
    h_end   = int(flights["occupied_until_min"].max())
    kpi = pd.concat(
        [summarize_solution(a, h_start, h_end) for a in [baseline, priority, optimized]],
        ignore_index=True,
    )

    print("  Running sensitivity analysis …")
    sensitivity = run_full_sensitivity(flights, gates)

    print("  Running simulation (100 scenarios) …")
    simulation = run_simulation(flights, gates, n_scenarios=100)

    print("  Running scenario analysis …")
    scenario_parts = []
    for sc in ["normal", "heavy", "disruption"]:
        sc_flights = create_scenario_flights(sc)
        sc_h_start = int(sc_flights["arrival_min"].min())
        sc_h_end   = int(sc_flights["occupied_until_min"].max())
        for func in [greedy_fcfs_assignment, optimize_gate_assignment]:
            try:
                s = summarize_solution(func(sc_flights, gates), sc_h_start, sc_h_end)
                s["scenario"] = sc
                scenario_parts.append(s)
            except Exception:
                pass

    return {
        "flights": flights, "gates": gates,
        "baseline": baseline, "priority": priority, "optimized": optimized,
        "kpi": kpi, "sensitivity": sensitivity, "simulation": simulation,
        "scenario": pd.concat(scenario_parts, ignore_index=True),
    }


def _load_data() -> dict:
    if all(p.exists() for p in _CACHE.values()):
        print("Loading precomputed results from disk …")
        return {key: pd.read_csv(path) for key, path in _CACHE.items()}
    return _compute_all()


_data = _load_data()
flights        = _data["flights"]
gates          = _data["gates"]
baseline       = _data["baseline"]
priority       = _data["priority"]
optimized      = _data["optimized"]
all_assign     = pd.concat([baseline, priority, optimized], ignore_index=True)
kpi_df         = _data["kpi"]
sensitivity_df = _data["sensitivity"]
sim_df         = _data["simulation"]
scenario_kpi_df = _data["scenario"]

print("Data ready. Starting Dash …\n")

# ---------------------------------------------------------------------------
# Helper: minute → HH:MM
# ---------------------------------------------------------------------------

def _clock(minute: float) -> str:
    m = int(minute)
    return f"{m // 60:02d}:{m % 60:02d}"


# ---------------------------------------------------------------------------
# Tab 1 helpers — Gantt + KPI
# ---------------------------------------------------------------------------

def make_gantt(assignment_df: pd.DataFrame) -> go.Figure:
    df = assignment_df.copy()
    df["start_dt"] = pd.to_datetime("2025-01-01") + pd.to_timedelta(df["arrival_min"],       unit="m")
    df["end_dt"]   = pd.to_datetime("2025-01-01") + pd.to_timedelta(df["occupied_until_min"], unit="m")
    df["tooltip"]  = (
        df["flight_id"] + " | " + df["airline"]
        + " | " + df["aircraft_size"]
        + " | " + df["passengers"].astype(str) + " pax"
        + " | " + df["arrival_clock"] + "→" + df["departure_clock"]
    )

    gate_order = (
        df[["gate_id", "gate_type"]]
        .drop_duplicates()
        .sort_values(["gate_type", "gate_id"])["gate_id"]
        .tolist()
    )

    fig = px.timeline(
        df,
        x_start="start_dt", x_end="end_dt",
        y="gate_id",
        color="aircraft_size",
        color_discrete_map={"narrow": "#4C78A8", "wide": "#F58518"},
        hover_data={"tooltip": True, "gate_id": False, "aircraft_size": False,
                    "start_dt": False, "end_dt": False},
        category_orders={"gate_id": gate_order},
        labels={"aircraft_size": "Aircraft"},
    )
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(
        title=f"Gate Schedule — {df['solution'].iat[0]}",
        xaxis_title="Time of day",
        yaxis_title="Gate / Stand",
        height=420,
        margin=dict(l=60, r=20, t=50, b=40),
        legend_title_text="Aircraft type",
    )
    # x-axis as HH:MM
    tick_vals = pd.date_range("2025-01-01 06:00", "2025-01-01 21:00", freq="1h")
    fig.update_xaxes(
        tickvals=tick_vals,
        ticktext=[t.strftime("%H:%M") for t in tick_vals],
        tickangle=45,
    )
    return fig


def make_kpi_bars(kpi_df: pd.DataFrame) -> go.Figure:
    metrics = [
        ("total_assignment_cost",               "Total Cost"),
        ("weighted_avg_walking_m",              "Avg Walk (m)"),
        ("zone_mismatch_flights",               "Zone Mismatches"),
        ("narrow_on_wide_gates",                "Narrow→Wide Gates"),
        ("total_expected_service_extension_min","Service Ext (min)"),
        ("remote_flights",                      "Remote Flights"),
    ]
    present = [m for m in METHOD_ORDER if m in kpi_df["solution"].values]
    fig = make_subplots(rows=2, cols=3, subplot_titles=[m[1] for m in metrics])
    for idx, (col, label) in enumerate(metrics):
        row, col_idx = divmod(idx, 3)
        for method in present:
            val = kpi_df.loc[kpi_df["solution"] == method, col]
            if len(val):
                fig.add_trace(
                    go.Bar(
                        name=method,
                        x=[method],
                        y=[val.iloc[0]],
                        marker_color=COLORS[method],
                        showlegend=(idx == 0),
                    ),
                    row=row + 1, col=col_idx + 1,
                )
    fig.update_layout(
        height=550,
        title_text="KPI Comparison — All Algorithms",
        barmode="group",
        margin=dict(l=40, r=20, t=80, b=40),
        legend_title_text="Algorithm",
    )
    return fig


# ---------------------------------------------------------------------------
# Tab 2 helper — Sensitivity
# ---------------------------------------------------------------------------

def make_sensitivity_fig(sensitivity_df: pd.DataFrame) -> go.Figure:
    params = sensitivity_df["param_label"].unique()
    n = len(params)
    cols = 2
    rows = (n + 1) // cols
    fig = make_subplots(
        rows=rows, cols=cols,
        specs=[[{"secondary_y": True} for _ in range(cols)] for _ in range(rows)],
        subplot_titles=list(params),
        shared_xaxes=False,
    )
    kpi_styles = [
        ("total_assignment_cost", "Total Cost", COLORS["Optimized MILP"], "solid", False),
        ("zone_mismatch_flights", "Zone Mismatches", COLORS["Baseline FCFS"], "dash", False),
        ("weighted_avg_walking_m", "Avg Walk (m)", COLORS["Priority Dispatch"], "dot", True),
    ]
    for i, param in enumerate(params):
        row, col = divmod(i, 2)
        sub = sensitivity_df[sensitivity_df["param_label"] == param]
        for kpi_col, kpi_label, color, dash, secondary_y in kpi_styles:
            fig.add_trace(
                go.Scatter(
                    x=sub["param_value"], y=sub[kpi_col],
                    mode="lines+markers",
                    name=kpi_label,
                    line=dict(color=color, dash=dash, width=2),
                    marker=dict(size=7),
                    showlegend=(i == 0),
                    legendgroup=kpi_label,
                ),
                row=row + 1, col=col + 1, secondary_y=secondary_y,
            )

        default_val = getattr(CostWeights(), sub["param_name"].iat[0])
        fig.add_vline(
            x=default_val,
            row=row + 1,
            col=col + 1,
            line_color="#aaaaaa",
            line_dash="dot",
            line_width=1.5,
            annotation_text=f"Default ({default_val:g})",
            annotation_position="top",
            annotation_font_size=10,
            annotation_font_color="#777777",
        )
        fig.update_yaxes(
            title_text="Cost / Mismatch count",
            row=row + 1, col=col + 1, secondary_y=False,
        )
        fig.update_yaxes(
            title_text="Avg Walk (m)",
            row=row + 1, col=col + 1, secondary_y=True,
        )
        fig.update_xaxes(title_text="Parameter value", row=row + 1, col=col + 1)

    fig.update_layout(
        height=600,
        title_text="Sensitivity Analysis — MILP Cost Weights",
        margin=dict(l=40, r=20, t=80, b=40),
    )
    return fig


# ---------------------------------------------------------------------------
# Tab 3 helper — Simulation
# ---------------------------------------------------------------------------

def make_simulation_fig(sim_df: pd.DataFrame) -> go.Figure:
    feasible = sim_df[sim_df["feasible"]].copy()
    present  = [m for m in METHOD_ORDER if m in feasible["method"].unique()]
    metrics  = [
        ("total_cost",      "Total Assignment Cost"),
        ("remote_flights",  "Remote Flights"),
        ("zone_mismatches", "Zone Mismatches"),
        ("weighted_walk_m", "Weighted Avg Walk (m)"),
    ]
    fig = make_subplots(rows=2, cols=2, subplot_titles=[m[1] for m in metrics])
    for idx, (col, label) in enumerate(metrics):
        row, col_idx = divmod(idx, 2)
        for method in present:
            vals = feasible.loc[feasible["method"] == method, col].dropna()
            fig.add_trace(
                go.Box(
                    y=vals,
                    name=method,
                    marker_color=COLORS[method],
                    showlegend=(idx == 0),
                    legendgroup=method,
                    boxmean="sd",
                ),
                row=row + 1, col=col_idx + 1,
            )
    n_sc = sim_df["scenario"].nunique()
    feas = sim_df.groupby("method")["feasible"].mean()
    feas_str = " | ".join(f"{m}: {feas.get(m,0):.0%}" for m in present)
    fig.update_layout(
        height=600,
        title_text=f"Robustness Simulation — {n_sc} Delay Scenarios   ({feas_str})",
        boxmode="group",
        margin=dict(l=40, r=20, t=80, b=40),
    )
    return fig


# ---------------------------------------------------------------------------
# Tab 4 helper — Scenario comparison
# ---------------------------------------------------------------------------

def make_scenario_fig(scenario_kpi_df: pd.DataFrame) -> go.Figure:
    metrics = [
        ("total_assignment_cost",  "Total Cost"),
        ("remote_flights",         "Remote Flights"),
        ("weighted_avg_walking_m", "Avg Walk (m)"),
        ("zone_mismatch_flights",  "Zone Mismatches"),
    ]
    fig = make_subplots(rows=2, cols=2, subplot_titles=[m[1] for m in metrics])
    scenarios = ["normal", "heavy", "disruption"]
    solutions = ["Baseline FCFS", "Optimized MILP"]
    for idx, (col, label) in enumerate(metrics):
        row, col_idx = divmod(idx, 2)
        for sol in solutions:
            sub = scenario_kpi_df[scenario_kpi_df["solution"] == sol]
            fig.add_trace(
                go.Bar(
                    name=sol,
                    x=[s.capitalize() for s in scenarios],
                    y=[sub.loc[sub["scenario"] == s, col].iloc[0]
                       if len(sub.loc[sub["scenario"] == s]) else 0
                       for s in scenarios],
                    marker_color=COLORS[sol],
                    showlegend=(idx == 0),
                    legendgroup=sol,
                ),
                row=row + 1, col=col_idx + 1,
            )
    fig.update_layout(
        height=600,
        title_text="Performance Across Operating Scenarios",
        barmode="group",
        margin=dict(l=40, r=20, t=80, b=40),
    )
    return fig


# ---------------------------------------------------------------------------
# Dash layout
# ---------------------------------------------------------------------------

try:
    from dash import Dash, dcc, html, Input, Output
    import dash_bootstrap_components as dbc
    USE_BOOTSTRAP = True
except ImportError:
    from dash import Dash, dcc, html, Input, Output
    USE_BOOTSTRAP = False

external = ["https://cdn.jsdelivr.net/npm/bootswatch@5.3.0/dist/flatly/bootstrap.min.css"] if USE_BOOTSTRAP else []

app = Dash(
    __name__,
    external_stylesheets=external,
    title="Airport Gate Optimization Dashboard",
)

# WSGI entry point for gunicorn (Render / Hugging Face / any prod host):
#   gunicorn src.dashboard:server
server = app.server

_GANTT_OPTIONS = [{"label": m, "value": m} for m in METHOD_ORDER]

app.layout = html.Div([
    html.H2(
        "Airport Gate Optimization — Interactive Dashboard",
        style={"textAlign": "center", "marginTop": "20px",
               "fontFamily": "Arial, sans-serif", "color": "#1F5E7A"},
    ),
    dcc.Tabs(
        id="tabs", value="tab-compare",
        children=[
            dcc.Tab(label="Solution Comparison", value="tab-compare"),
            dcc.Tab(label="Sensitivity Analysis", value="tab-sensitivity"),
            dcc.Tab(label="Robustness Simulation", value="tab-simulation"),
            dcc.Tab(label="Scenario Analysis", value="tab-scenario"),
        ],
        style={"fontFamily": "Arial, sans-serif"},
    ),
    html.Div(id="tab-content", style={"padding": "16px"}),
], style={"maxWidth": "1200px", "margin": "0 auto"})


@app.callback(Output("tab-content", "children"), Input("tabs", "value"))
def render_tab(tab: str):
    if tab == "tab-compare":
        return html.Div([
            html.Div([
                html.Label("Select algorithm for Gantt view:",
                           style={"fontWeight": "bold"}),
                dcc.Dropdown(
                    id="gantt-selector",
                    options=_GANTT_OPTIONS,
                    value="Optimized MILP",
                    clearable=False,
                    style={"width": "300px"},
                ),
            ], style={"marginBottom": "12px"}),
            dcc.Graph(id="gantt-graph", figure=make_gantt(optimized)),
            dcc.Graph(figure=make_kpi_bars(kpi_df)),
        ])

    if tab == "tab-sensitivity":
        return dcc.Graph(figure=make_sensitivity_fig(sensitivity_df), style={"height": "650px"})

    if tab == "tab-simulation":
        return html.Div([
            html.P(
                "Each box spans 100 independently drawn delay scenarios "
                "(30% of flights delayed 10–60 min). "
                "Lower boxes = more robust performance.",
                style={"color": "#555", "marginBottom": "8px"},
            ),
            dcc.Graph(figure=make_simulation_fig(sim_df), style={"height": "650px"}),
        ])

    if tab == "tab-scenario":
        return html.Div([
            html.P(
                "Normal (36 flights) vs Heavy (+36% traffic) vs Disruption "
                "(35% of flights delayed 15–50 min).",
                style={"color": "#555", "marginBottom": "8px"},
            ),
            dcc.Graph(figure=make_scenario_fig(scenario_kpi_df), style={"height": "650px"}),
        ])

    return html.Div("Select a tab.")


@app.callback(Output("gantt-graph", "figure"), Input("gantt-selector", "value"))
def update_gantt(method: str):
    mapping = {
        "Baseline FCFS":    baseline,
        "Priority Dispatch": priority,
        "Optimized MILP":   optimized,
    }
    return make_gantt(mapping.get(method, optimized))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os

    port = int(os.environ.get("PORT", 8050))
    print(f"Dashboard ready at  http://127.0.0.1:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
