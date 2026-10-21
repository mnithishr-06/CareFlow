"""Evaluate clinical transition SLAs and summarize breaches by department."""

import argparse
from pathlib import Path

import pandas as pd

from data_loader import EXPECTED_MILESTONES, load_event_log


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = REPOSITORY_ROOT / "data" / "raw" / "clinical_events.csv"
DEFAULT_VIOLATIONS_OUTPUT = (
    REPOSITORY_ROOT / "data" / "processed" / "sla_violations.csv"
)
DEFAULT_SUMMARY_OUTPUT = (
    REPOSITORY_ROOT / "data" / "processed" / "department_breach_summary.csv"
)

# Department attribution uses the department recorded on the destination event.
SLA_TARGETS = (
    {
        "source": "Triage_Assessment",
        "target": "Physician_Consultation",
        "target_hours": 1.0,
    },
    {
        "source": "Inpatient_Ward_Transfer",
        "target": "Discharge",
        "target_hours": 4.0,
    },
)


def evaluate_sla(events):
    """Return detailed breach rows and compliance metrics per destination department."""
    target_by_transition = {
        (target["source"], target["target"]): target["target_hours"]
        for target in SLA_TARGETS
    }
    evaluated_by_department = {}
    violations = []

    for case_id, case_events in events.groupby("case_id", sort=False):
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
        for (source, target), target_hours in target_by_transition.items():
            from_event = case_events.loc[source]
            to_event = case_events.loc[target]
            elapsed_hours = (
                to_event["event_timestamp"] - from_event["event_timestamp"]
            ).total_seconds() / 3600
            if elapsed_hours < 0:
                raise ValueError(
                    f"Case {case_id} has {source} after {target} in timestamp order"
                )

            department = str(to_event["department"])
            department_metrics = evaluated_by_department.setdefault(
                department,
                {
                    "transitions_evaluated": 0,
                    "breaches": 0,
                    "total_waiting_hours": 0.0,
                    "max_waiting_hours": 0.0,
                    "total_breach_hours": 0.0,
                },
            )
            department_metrics["transitions_evaluated"] += 1
            department_metrics["total_waiting_hours"] += elapsed_hours
            department_metrics["max_waiting_hours"] = max(
                department_metrics["max_waiting_hours"], elapsed_hours
            )

            if elapsed_hours > target_hours:
                breach_hours = elapsed_hours - target_hours
                department_metrics["breaches"] += 1
                department_metrics["total_breach_hours"] += breach_hours
                violations.append(
                    {
                        "case_id": case_id,
                        "patient_id": to_event["patient_id"],
                        "source": source,
                        "target": target,
                        "department": department,
                        "actual_waiting_hours": elapsed_hours,
                        "sla_target_hours": target_hours,
                        "breach_hours": breach_hours,
                    }
                )

    summary = [
        {
            "department": department,
            "transitions_evaluated": metrics["transitions_evaluated"],
            "breaches": metrics["breaches"],
            "compliant_transitions": (
                metrics["transitions_evaluated"] - metrics["breaches"]
            ),
            "compliance_percentage": (
                100
                * (metrics["transitions_evaluated"] - metrics["breaches"])
                / metrics["transitions_evaluated"]
            ),
            "mean_waiting_hours": (
                metrics["total_waiting_hours"] / metrics["transitions_evaluated"]
            ),
            "max_waiting_hours": metrics["max_waiting_hours"],
            "total_breach_hours": metrics["total_breach_hours"],
        }
        for department, metrics in sorted(evaluated_by_department.items())
    ]
    return pd.DataFrame(violations), pd.DataFrame(summary)


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate clinical transition SLAs and summarize department breaches."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument(
        "--violations-output", type=Path, default=DEFAULT_VIOLATIONS_OUTPUT
    )
    parser.add_argument(
        "--summary-output", type=Path, default=DEFAULT_SUMMARY_OUTPUT
    )
    args = parser.parse_args()

    events = load_event_log(str(args.input))
    violations, summary = evaluate_sla(events)
    args.violations_output.parent.mkdir(parents=True, exist_ok=True)
    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    violations.to_csv(args.violations_output, index=False)
    summary.to_csv(args.summary_output, index=False)

    evaluated_transitions = int(summary["transitions_evaluated"].sum())
    total_breaches = len(violations)
    overall_compliance = (
        100 * (evaluated_transitions - total_breaches) / evaluated_transitions
        if evaluated_transitions
        else 0.0
    )
    print(f"Evaluated {evaluated_transitions} SLA-targeted transitions.")
    print(
        f"Found {total_breaches} breaches; overall compliance: "
        f"{overall_compliance:.2f}%."
    )
    print(f"Wrote breach records to {args.violations_output}.")
    print(f"Wrote department metrics to {args.summary_output}.")


if __name__ == "__main__":
    main()
