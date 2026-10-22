"""Compare length of stay, transition waits, and SLA breaches by patient cohort."""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from data_loader import EXPECTED_MILESTONES, load_event_log
from sla_compliance import SLA_TARGETS


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = REPOSITORY_ROOT / "data" / "raw" / "clinical_events.csv"
DEFAULT_SUMMARY_OUTPUT = (
    REPOSITORY_ROOT / "data" / "processed" / "cohort_metrics.csv"
)
DEFAULT_VISUAL_OUTPUT = (
    REPOSITORY_ROOT / "visuals" / "cohort_los_comparison.png"
)


def analyze_cohorts(events, cohort_column="severity"):
    """Return cohort-level metrics and patient LoS distributions."""
    if cohort_column not in events.columns:
        raise ValueError(
            f"Missing cohort column {cohort_column!r}; "
            "provide a patient-level cohort such as severity or admission_type"
        )
    if events[cohort_column].isna().any():
        raise ValueError(f"Cohort column {cohort_column!r} contains empty values")

    targets = {
        (target["source"], target["target"]): target["target_hours"]
        for target in SLA_TARGETS
    }
    patient_records = []

    for case_id, case_events in events.groupby("case_id", sort=False):
        if case_events[cohort_column].nunique() != 1:
            raise ValueError(
                f"Patient case {case_id} has inconsistent {cohort_column!r} values"
            )
        event_counts = case_events["event_name"].value_counts()
        invalid = {
            milestone: int(event_counts.get(milestone, 0))
            for milestone in EXPECTED_MILESTONES
            if event_counts.get(milestone, 0) != 1
        }
        if invalid or len(case_events) != len(EXPECTED_MILESTONES):
            raise ValueError(
                f"Case {case_id} must contain each expected milestone exactly once; "
                f"invalid counts: {invalid or 'unexpected extra events'}"
            )

        case_events = case_events.set_index("event_name")
        ordered_events = case_events.loc[EXPECTED_MILESTONES]
        timestamps = ordered_events["event_timestamp"].tolist()
        if any(earlier > later for earlier, later in zip(timestamps, timestamps[1:])):
            raise ValueError(f"Case {case_id} has milestones out of clinical pathway order")

        transition_waits = [
            (later - earlier).total_seconds() / 3600
            for earlier, later in zip(timestamps, timestamps[1:])
        ]
        if any(wait < 0 for wait in transition_waits):
            raise ValueError(f"Case {case_id} contains a negative transition wait")

        breach_count = 0
        for (source, target), target_hours in targets.items():
            wait_hours = (
                case_events.loc[target, "event_timestamp"]
                - case_events.loc[source, "event_timestamp"]
            ).total_seconds() / 3600
            if wait_hours > target_hours:
                breach_count += 1

        patient_records.append(
            {
                "case_id": case_id,
                "cohort": str(case_events[cohort_column].iloc[0]),
                "length_of_stay_hours": (
                    timestamps[-1] - timestamps[0]
                ).total_seconds()
                / 3600,
                "mean_transition_wait_hours": sum(transition_waits)
                / len(transition_waits),
                "sla_transitions_evaluated": len(targets),
                "sla_breaches": breach_count,
            }
        )

    if not patient_records:
        raise ValueError("The event log contains no patient cases")

    patients = pd.DataFrame(patient_records)
    grouped = patients.groupby("cohort", sort=True)
    summary = grouped.agg(
        patient_count=("case_id", "nunique"),
        median_los_hours=("length_of_stay_hours", "median"),
        mean_transition_wait_hours=("mean_transition_wait_hours", "mean"),
        sla_transitions_evaluated=("sla_transitions_evaluated", "sum"),
        sla_breaches=("sla_breaches", "sum"),
    ).reset_index()
    summary["sla_compliant_transitions"] = (
        summary["sla_transitions_evaluated"] - summary["sla_breaches"]
    )
    summary["sla_breach_rate_percentage"] = (
        100 * summary["sla_breaches"] / summary["sla_transitions_evaluated"]
    )
    return summary, patients


def plot_los_comparison(patients, output_path):
    """Save a box plot comparing patient LoS distributions by cohort."""
    cohorts = sorted(patients["cohort"].unique())
    los_by_cohort = [
        patients.loc[patients["cohort"] == cohort, "length_of_stay_hours"].tolist()
        for cohort in cohorts
    ]

    figure, axis = plt.subplots(figsize=(9, 5.5))
    axis.boxplot(los_by_cohort, tick_labels=cohorts, showmeans=True)
    axis.set_title("Length of Stay by Synthetic Severity Cohort")
    axis.set_xlabel("Patient cohort")
    axis.set_ylabel("Length of stay (hours)")
    axis.grid(axis="y", linestyle=":", alpha=0.5)
    figure.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(figure)


def main():
    parser = argparse.ArgumentParser(
        description="Compare LoS, transition waits, and SLA breaches by cohort."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--summary-output", type=Path, default=DEFAULT_SUMMARY_OUTPUT)
    parser.add_argument("--visual-output", type=Path, default=DEFAULT_VISUAL_OUTPUT)
    parser.add_argument(
        "--cohort-column",
        default="severity",
        help="Patient-level cohort column in the event log (default: severity).",
    )
    args = parser.parse_args()

    events = load_event_log(str(args.input))
    summary, patients = analyze_cohorts(events, args.cohort_column)
    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(args.summary_output, index=False)
    plot_los_comparison(patients, args.visual_output)

    print(
        f"Analyzed {len(patients)} patients across "
        f"{summary['cohort'].nunique()} {args.cohort_column} cohorts."
    )
    print(f"Wrote cohort metrics to {args.summary_output}.")
    print(f"Wrote LoS comparison chart to {args.visual_output}.")


if __name__ == "__main__":
    main()
