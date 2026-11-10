"""Query CareFlow patient journeys and operational metrics from the terminal."""

import argparse
from pathlib import Path

import pandas as pd


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROCESSED_DIR = REPOSITORY_ROOT / "data" / "processed"
DEFAULT_EVENT_LOG = REPOSITORY_ROOT / "data" / "raw" / "clinical_events.csv"

REQUIRED_EVENT_COLUMNS = {
    "case_id",
    "patient_id",
    "event_name",
    "event_timestamp",
    "department",
}
REQUIRED_BREACH_COLUMNS = {
    "case_id",
    "source",
    "target",
    "department",
    "actual_waiting_hours",
    "sla_target_hours",
    "breach_hours",
}
REQUIRED_TRANSITION_COLUMNS = {
    "metric",
    "stage",
    "from_stage",
    "to_stage",
    "patient_count",
    "mean_duration_hours",
    "median_duration_hours",
}
REQUIRED_DEPARTMENT_COLUMNS = {
    "department",
    "transitions_evaluated",
    "breaches",
    "compliant_transitions",
    "compliance_percentage",
    "mean_waiting_hours",
    "max_waiting_hours",
    "total_breach_hours",
}
REQUIRED_CONFORMANCE_COLUMNS = {
    "case_id",
    "trace_is_fit",
    "trace_fitness",
    "missing_tokens",
    "remaining_tokens",
}


def _read_csv(path, required_columns):
    """Read a CSV and report absent files or schema fields clearly."""
    if not path.is_file():
        raise FileNotFoundError(f"Required query data file not found: {path}")
    frame = pd.read_csv(path)
    missing = required_columns - set(frame.columns)
    if missing:
        raise ValueError(f"{path} is missing required columns: {sorted(missing)}")
    return frame


def query_patient(patient_id, event_log_path, processed_dir):
    """Return ordered patient events, conformance scores, and SLA breaches."""
    events = _read_csv(event_log_path, REQUIRED_EVENT_COLUMNS)
    matches = events.loc[events["patient_id"].astype(str) == str(patient_id)].copy()
    if matches.empty:
        raise ValueError(f"No patient found with ID {patient_id!r}")

    matches["event_timestamp"] = pd.to_datetime(
        matches["event_timestamp"], errors="raise"
    )
    matches = matches.sort_values(
        ["case_id", "event_timestamp"], kind="mergesort"
    ).reset_index(drop=True)
    matches["transition_wait_hours"] = (
        matches.groupby("case_id")["event_timestamp"]
        .diff()
        .dt.total_seconds()
        .div(3600)
    )

    case_ids = matches["case_id"].astype(str).unique()
    breaches = _read_csv(
        processed_dir / "sla_violations.csv", REQUIRED_BREACH_COLUMNS
    )
    breaches = breaches.loc[breaches["case_id"].astype(str).isin(case_ids)]
    conformance = _read_csv(
        processed_dir / "conformance_scores.csv", REQUIRED_CONFORMANCE_COLUMNS
    )
    conformance = conformance.loc[
        conformance["case_id"].astype(str).isin(case_ids)
    ]
    return matches, conformance, breaches


def _normalize_stage(value):
    return str(value).strip().lower().replace(" ", "_")


def query_stage(stage, processed_dir):
    """Return transition metrics and/or department summary for a stage/dept."""
    transitions = _read_csv(
        processed_dir / "transition_metrics.csv", REQUIRED_TRANSITION_COLUMNS
    )
    departments = _read_csv(
        processed_dir / "department_breach_summary.csv",
        REQUIRED_DEPARTMENT_COLUMNS,
    )
    breaches = _read_csv(
        processed_dir / "sla_violations.csv", REQUIRED_BREACH_COLUMNS
    )

    requested_stage = _normalize_stage(stage)
    stage_metrics = transitions.loc[
        (transitions["metric"] == "transition_wait")
        & (
            (transitions["stage"].map(_normalize_stage) == requested_stage)
            | (transitions["to_stage"].map(_normalize_stage) == requested_stage)
        )
    ]
    department_metrics = departments.loc[
        departments["department"].astype(str).str.casefold()
        == str(stage).strip().casefold()
    ]

    if stage_metrics.empty and department_metrics.empty:
        available_stages = sorted(
            transitions.loc[transitions["metric"] == "transition_wait", "stage"]
            .dropna()
            .unique()
            .tolist()
        )
        available_departments = sorted(
            departments["department"].dropna().astype(str).unique().tolist()
        )
        raise ValueError(
            f"No stage or department matches {stage!r}. "
            f"Stages: {', '.join(available_stages)}. "
            f"Departments: {', '.join(available_departments)}."
        )

    if not stage_metrics.empty:
        stage_metrics = stage_metrics.copy()
        if len(stage_metrics) != 1:
            raise ValueError(
                f"Expected one transition metric for {stage!r}, found "
                f"{len(stage_metrics)}"
            )
        transition = stage_metrics.iloc[0]
        stage_breaches = breaches.loc[
            (
                breaches["source"].map(_normalize_stage)
                == _normalize_stage(transition["from_stage"])
            )
            & (
                breaches["target"].map(_normalize_stage)
                == _normalize_stage(transition["to_stage"])
            )
        ]
        breach_departments = (
            stage_breaches.groupby("department", dropna=False)
            .size()
            .rename("breach_count")
            .reset_index()
            .sort_values("breach_count", ascending=False)
        )
    else:
        breach_departments = pd.DataFrame(
            columns=["department", "breach_count"]
        )

    return stage_metrics, department_metrics, breach_departments


def query_top_deviations(limit, processed_dir):
    """Return the lowest-fitness non-fitting cases, capped at the requested count."""
    if limit <= 0:
        raise ValueError("--top-deviations must be a positive integer")
    conformance = _read_csv(
        processed_dir / "conformance_scores.csv", REQUIRED_CONFORMANCE_COLUMNS
    ).copy()
    conformance["trace_fitness"] = pd.to_numeric(
        conformance["trace_fitness"], errors="raise"
    )
    conformance["trace_is_fit"] = (
        conformance["trace_is_fit"].astype(str).str.strip().str.lower()
    )
    invalid_fit_values = ~conformance["trace_is_fit"].isin({"true", "false"})
    if invalid_fit_values.any():
        raise ValueError("trace_is_fit must contain only true or false values")
    deviations = conformance.loc[conformance["trace_is_fit"] == "false"].copy()
    return deviations.sort_values(
        ["trace_fitness", "missing_tokens", "remaining_tokens", "case_id"],
        ascending=[True, False, False, True],
        kind="mergesort",
    ).head(limit)


def _print_table(frame, columns=None):
    if frame.empty:
        print("No matching records.")
        return
    if columns is not None:
        frame = frame.loc[:, columns]
    print(frame.to_string(index=False))


def _show_patient(patient_id, event_log_path, processed_dir):
    events, conformance, breaches = query_patient(
        patient_id, event_log_path, processed_dir
    )
    print(f"Patient {patient_id} journey:")
    _print_table(
        events,
        [
            "case_id",
            "event_name",
            "event_timestamp",
            "department",
            "transition_wait_hours",
        ],
    )
    for case_id in events["case_id"].astype(str).unique():
        case_conformance = conformance.loc[
            conformance["case_id"].astype(str) == case_id
        ]
        if not case_conformance.empty:
            row = case_conformance.iloc[0]
            print(
                f"\nConformance for {case_id}: "
                f"fit={str(row['trace_is_fit']).lower()}, "
                f"fitness={float(row['trace_fitness']):.3f}, "
                f"missing_tokens={row['missing_tokens']}, "
                f"remaining_tokens={row['remaining_tokens']}"
            )
        case_breaches = breaches.loc[breaches["case_id"].astype(str) == case_id]
        print(f"\nSLA breaches for {case_id}:")
        _print_table(
            case_breaches,
            [
                "source",
                "target",
                "department",
                "actual_waiting_hours",
                "sla_target_hours",
                "breach_hours",
            ],
        )


def _show_stage(stage, processed_dir):
    stage_metrics, department_metrics, breach_departments = query_stage(
        stage, processed_dir
    )
    if not stage_metrics.empty:
        row = stage_metrics.iloc[0]
        print(
            f"Transition metrics for {_normalize_stage(stage).replace('_', ' ')}:"
        )
        _print_table(
            stage_metrics,
            [
                "from_stage",
                "to_stage",
                "patient_count",
                "mean_duration_hours",
                "median_duration_hours",
            ],
        )
        print("\nSLA breach counts by destination department for this transition:")
        _print_table(breach_departments)

    if not department_metrics.empty:
        print(f"Department SLA summary for {stage}:")
        _print_table(department_metrics)


def main():
    parser = argparse.ArgumentParser(
        description="Query patient journeys and processed CareFlow operational metrics."
    )
    queries = parser.add_mutually_exclusive_group(required=True)
    queries.add_argument(
        "--patient-id",
        help="Display the patient's timestamped journey, conformance, and SLA breaches.",
    )
    queries.add_argument(
        "--stage",
        help="Inspect transition metrics for a clinical stage or SLA summary for a department.",
    )
    queries.add_argument(
        "--top-deviations",
        type=int,
        metavar="N",
        help="List up to N non-fitting cases, ranked by lowest trace fitness.",
    )
    parser.add_argument(
        "--processed-dir",
        type=Path,
        default=DEFAULT_PROCESSED_DIR,
        help="Directory containing processed analytics CSVs.",
    )
    parser.add_argument(
        "--event-log",
        type=Path,
        default=DEFAULT_EVENT_LOG,
        help="Raw event log CSV used for patient journey queries.",
    )
    args = parser.parse_args()

    try:
        if args.patient_id is not None:
            _show_patient(args.patient_id, args.event_log, args.processed_dir)
        elif args.stage is not None:
            _show_stage(args.stage, args.processed_dir)
        else:
            deviations = query_top_deviations(
                args.top_deviations, args.processed_dir
            )
            if deviations.empty:
                print("No non-conforming pathway cases found.")
            else:
                print(f"Top {len(deviations)} non-conforming pathway cases:")
                _print_table(
                    deviations,
                    [
                        "case_id",
                        "trace_fitness",
                        "missing_tokens",
                        "remaining_tokens",
                    ],
                )
    except (FileNotFoundError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
