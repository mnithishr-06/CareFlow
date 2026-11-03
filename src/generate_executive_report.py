"""Compile processed CareFlow metrics into an executive Markdown briefing."""

import argparse
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import pandas as pd


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROCESSED_DIR = REPOSITORY_ROOT / "data" / "processed"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "reports" / "clinical_executive_brief.md"
INPUT_FILES = {
    "transitions": "transition_metrics.csv",
    "sla_violations": "sla_violations.csv",
    "conformance": "conformance_scores.csv",
    "simulation": "simulation_results.csv",
}
REQUIRED_COLUMNS = {
    "transitions": {
        "metric",
        "stage",
        "from_stage",
        "to_stage",
        "patient_count",
        "mean_duration_hours",
        "median_duration_hours",
    },
    "sla_violations": {
        "case_id",
        "source",
        "target",
        "department",
        "actual_waiting_hours",
        "sla_target_hours",
        "breach_hours",
    },
    "conformance": {"case_id", "trace_is_fit", "trace_fitness"},
    "simulation": {
        "scenario",
        "discharge_delay_reduction_percentage",
        "patient_count",
        "baseline_mean_los_hours",
        "simulated_mean_los_hours",
        "mean_los_improvement_hours",
        "total_bed_hours_saved",
    },
}


def load_processed_metrics(processed_dir):
    """Load required inputs and fail clearly when files or fields are missing."""
    data = {}
    for key, filename in INPUT_FILES.items():
        path = processed_dir / filename
        if not path.is_file():
            raise FileNotFoundError(f"Required processed metrics file not found: {path}")
        frame = pd.read_csv(path)
        missing_columns = REQUIRED_COLUMNS[key] - set(frame.columns)
        if missing_columns:
            raise ValueError(
                f"{path} is missing required columns: {sorted(missing_columns)}"
            )
        if key != "sla_violations" and frame.empty:
            raise ValueError(f"Required processed metrics file is empty: {path}")
        data[key] = frame
    return data


def _single_row(frame, condition, label):
    matches = frame.loc[condition]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one {label} row; found {len(matches)}")
    return matches.iloc[0]


def _stage_label(stage):
    return str(stage).replace("_", " ")


def _format_hours(value):
    rounded = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{rounded:,.2f} h"


def _format_number(value):
    rounded = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{rounded:,.2f}"


def build_report(data):
    """Render a concise executive report from validated processed metrics."""
    transitions = data["transitions"]
    los = _single_row(
        transitions,
        transitions["metric"] == "patient_los",
        "patient length-of-stay",
    )
    transition_rows = transitions.loc[transitions["metric"] == "transition_wait"]
    if transition_rows.empty:
        raise ValueError("Transition metrics contain no transition_wait rows")
    bottleneck = transition_rows.loc[
        transition_rows["mean_duration_hours"].astype(float).idxmax()
    ]

    conformance = data["conformance"].copy()
    conformance["trace_fitness"] = pd.to_numeric(
        conformance["trace_fitness"], errors="raise"
    )
    if not conformance["trace_fitness"].between(0, 1).all():
        raise ValueError("Conformance trace_fitness values must be between 0 and 1")
    fitness_values = conformance["trace_fitness"]
    fit_values = conformance["trace_is_fit"].astype(str).str.lower().map(
        {"true": True, "false": False}
    )
    if fit_values.isna().any():
        raise ValueError("Conformance trace_is_fit must contain only true or false")
    fitting_cases = int(fit_values.sum())
    conformance_case_count = len(conformance)

    simulation = data["simulation"].copy()
    simulation["discharge_delay_reduction_percentage"] = pd.to_numeric(
        simulation["discharge_delay_reduction_percentage"], errors="raise"
    )
    simulation_50 = _single_row(
        simulation,
        simulation["discharge_delay_reduction_percentage"] == 50,
        "50% simulation",
    )

    violations = data["sla_violations"].copy()
    breach_count = len(violations)
    if breach_count:
        for column in ("actual_waiting_hours", "sla_target_hours", "breach_hours"):
            violations[column] = pd.to_numeric(violations[column], errors="raise")
        transition_breaches = (
            violations.groupby(["source", "target"], sort=True)
            .agg(
                breach_count=("case_id", "size"),
                mean_actual_wait_hours=("actual_waiting_hours", "mean"),
                target_hours=("sla_target_hours", "first"),
                mean_excess_hours=("breach_hours", "mean"),
                max_excess_hours=("breach_hours", "max"),
            )
            .reset_index()
        )
        department_breaches = (
            violations.groupby("department", sort=True)
            .size()
            .sort_values(ascending=False)
        )
        unique_breach_cases = violations["case_id"].nunique()
    else:
        transition_breaches = pd.DataFrame(
            columns=[
                "source",
                "target",
                "breach_count",
                "mean_actual_wait_hours",
                "target_hours",
                "mean_excess_hours",
                "max_excess_hours",
            ]
        )
        department_breaches = pd.Series(dtype="int64")
        unique_breach_cases = 0

    patient_count = int(los["patient_count"])
    if patient_count != conformance_case_count:
        raise ValueError(
            "Transition and conformance inputs disagree on patient case count "
            f"({patient_count} vs {conformance_case_count})"
        )
    if int(simulation_50["patient_count"]) != patient_count:
        raise ValueError(
            "Simulation and transition inputs disagree on patient case count "
            f"({int(simulation_50['patient_count'])} vs {patient_count})"
        )

    lines = [
        "# Clinical Pathway Executive Briefing",
        "",
        "## Executive summary",
        "",
        (
            f"This briefing summarizes processed analytics for **{patient_count:,} "
            "synthetic patient cases**. The baseline median length of stay (LoS) is "
            f"**{_format_hours(los['median_duration_hours'])}**. The longest mean "
            f"stage wait is **{_format_hours(bottleneck['mean_duration_hours'])}** "
            f"from **{_stage_label(bottleneck['from_stage'])}** to "
            f"**{_stage_label(bottleneck['to_stage'])}**. A modeled 50% reduction "
            f"in that discharge delay corresponds to **"
            f"{_format_hours(simulation_50['mean_los_improvement_hours'])} mean "
            f"LoS improvement per case** and **"
            f"{_format_number(simulation_50['total_bed_hours_saved'])} "
            "bed-hours saved** across the cohort."
        ),
        "",
        "> **Scope:** All source records and results are synthetic. These analyses are operational demonstrations, not estimates of actual hospital performance, validated clinical guidance, or patient-care recommendations.",
        "",
        "## Key clinical KPIs",
        "",
        "| KPI | Result |",
        "|---|---:|",
        f"| Patient cases analyzed | {patient_count:,} |",
        f"| Median admission-to-discharge LoS | {_format_hours(los['median_duration_hours'])} |",
        f"| Mean admission-to-discharge LoS | {_format_hours(los['mean_duration_hours'])} |",
        f"| Mean wait at longest transition | {_format_hours(bottleneck['mean_duration_hours'])} |",
        f"| Mean fitness against configured canonical path | {fitness_values.mean():.3f} |",
        f"| Cases fitting configured canonical path | {fitting_cases:,} / {conformance_case_count:,} ({100 * fitting_cases / conformance_case_count:.2f}%) |",
        "",
        "## Bottleneck diagnostics",
        "",
        (
            f"The longest mean wait occurs between **{_stage_label(bottleneck['from_stage'])}** "
            f"and **{_stage_label(bottleneck['to_stage'])}**: mean "
            f"{_format_hours(bottleneck['mean_duration_hours'])}, median "
            f"{_format_hours(bottleneck['median_duration_hours'])}, across "
            f"{int(bottleneck['patient_count']):,} cases."
        ),
        "",
        "| Transition | Mean wait | Median wait | Cases |",
        "|---|---:|---:|---:|",
    ]
    for _, row in transition_rows.sort_values(
        "mean_duration_hours", ascending=False
    ).iterrows():
        lines.append(
            f"| {_stage_label(row['from_stage'])} → {_stage_label(row['to_stage'])} "
            f"| {_format_hours(row['mean_duration_hours'])} "
            f"| {_format_hours(row['median_duration_hours'])} "
            f"| {int(row['patient_count']):,} |"
        )

    lines.extend(
        [
            "",
            "## Compliance audit findings",
            "",
            (
                f"The breach-only SLA audit contains **{breach_count:,} flagged "
                f"transition records** across **{unique_breach_cases:,} cases**."
            ),
        ]
    )
    if breach_count:
        lines.extend(
            [
                "",
                "| SLA transition | Target | Breaches | Mean observed wait | Mean excess | Maximum excess |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )
        for _, row in transition_breaches.iterrows():
            lines.append(
                f"| {_stage_label(row['source'])} → {_stage_label(row['target'])} "
                f"| {_format_hours(row['target_hours'])} "
                f"| {int(row['breach_count']):,} "
                f"| {_format_hours(row['mean_actual_wait_hours'])} "
                f"| {_format_hours(row['mean_excess_hours'])} "
                f"| {_format_hours(row['max_excess_hours'])} |"
            )
        department_summary = ", ".join(
            f"{department}: {count:,}"
            for department, count in department_breaches.items()
        )
        lines.extend(["", f"Breaches by destination department: {department_summary}."])
    else:
        lines.extend(["", "No SLA breach records were present in the input file."])
    lines.extend(
        [
            "",
            "The supplied SLA file contains breaches only, not all evaluated compliant and non-compliant transitions. Therefore this briefing does not infer a compliance rate or denominator from that file. Thresholds should be treated as illustrative unless approved by clinical and operational owners.",
            "",
            "## Conformance review",
            "",
            (
                f"Token-replay scores show {fitting_cases:,} of "
                f"{conformance_case_count:,} cases fitting the configured canonical "
                f"seven-stage pathway. Mean trace fitness is "
                f"{fitness_values.mean():.3f} (median {fitness_values.median():.3f}). "
                "This checks the generated traces against the configured model; it "
                "does not establish adherence to an independently approved clinical SOP."
            ),
            "",
            "## What-if capacity scenario",
            "",
            (
                f"The 50% discharge-delay reduction scenario reduces mean LoS from "
                f"{_format_hours(simulation_50['baseline_mean_los_hours'])} to "
                f"{_format_hours(simulation_50['simulated_mean_los_hours'])}, an "
                f"average improvement of "
                f"{_format_hours(simulation_50['mean_los_improvement_hours'])} "
                f"per case and {_format_number(simulation_50['total_bed_hours_saved'])} "
                "aggregate bed-hours saved."
            ),
            "",
            "This is a proportional what-if calculation on synthetic transfer-to-discharge waits, not a forecast of realized throughput, occupancy, or capacity expansion.",
            "",
            "## Strategic operational recommendations",
            "",
            "1. **Validate the signal on governed operational data.** Confirm timestamp semantics, pathway definitions, department ownership, case completeness, and metric denominators before interpreting the bottleneck or breach patterns.",
            "2. **Investigate discharge coordination as a hypothesis.** On validated data, examine readiness documentation, medication reconciliation, transport, placement, and downstream bed constraints; do not infer causes from elapsed time alone.",
            "3. **Review and approve SLA definitions.** Confirm target thresholds, clock start/stop events, exclusions, and department attribution with clinical and operational stakeholders, then report both breaches and all evaluated transitions.",
            "4. **Treat scenario savings as capacity hypotheses.** Pilot an explicitly defined process change and measure observed LoS, occupancy, demand, and throughput before making capacity claims.",
            "5. **Use an approved SOP and realistic pathway variation for conformance.** Define permitted exceptions and evaluate detours, incomplete traces, and rework before treating conformance scores as operational evidence.",
            "",
            "## Data sources",
            "",
            "- `data/processed/transition_metrics.csv`",
            "- `data/processed/sla_violations.csv`",
            "- `data/processed/conformance_scores.csv`",
            "- `data/processed/simulation_results.csv`",
            "",
        ]
    )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Generate a Markdown executive briefing from processed metrics."
    )
    parser.add_argument("--processed-dir", type=Path, default=DEFAULT_PROCESSED_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    data = load_processed_metrics(args.processed_dir)
    report = build_report(data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(f"Wrote clinical executive briefing to {args.output}.")


if __name__ == "__main__":
    main()
