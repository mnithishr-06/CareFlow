"""Model length-of-stay and capacity gains from reducing discharge delays."""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from data_loader import EXPECTED_MILESTONES, load_event_log


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = REPOSITORY_ROOT / "data" / "raw" / "clinical_events.csv"
DEFAULT_OUTPUT = (
    REPOSITORY_ROOT / "data" / "processed" / "simulation_results.csv"
)
DEFAULT_VISUAL_OUTPUT = (
    REPOSITORY_ROOT / "visuals" / "simulation_capacity_gain.png"
)
REDUCTION_SCENARIOS = (0, 30, 50, 70)


def build_patient_metrics(events):
    """Return each patient's baseline LoS and transfer-to-discharge delay."""
    patient_metrics = []

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

        ordered = case_events.set_index("event_name").loc[EXPECTED_MILESTONES]
        timestamps = ordered["event_timestamp"].tolist()
        if any(earlier > later for earlier, later in zip(timestamps, timestamps[1:])):
            raise ValueError(f"Case {case_id} has milestones out of clinical pathway order")

        baseline_los = (timestamps[-1] - timestamps[0]).total_seconds() / 3600
        discharge_delay = (timestamps[-1] - timestamps[-2]).total_seconds() / 3600
        if baseline_los < 0 or discharge_delay < 0:
            raise ValueError(f"Case {case_id} contains a negative duration")

        patient_metrics.append(
            {
                "case_id": case_id,
                "baseline_los_hours": baseline_los,
                "discharge_delay_hours": discharge_delay,
            }
        )

    if not patient_metrics:
        raise ValueError("The event log contains no patient cases")

    return pd.DataFrame(patient_metrics)


def simulate_reductions(patient_metrics, reduction_percentages=REDUCTION_SCENARIOS):
    """Summarize baseline and reduced-delay LoS and bed-hours for each scenario."""
    if not reduction_percentages:
        raise ValueError("At least one reduction scenario is required")
    if any(not 0 <= percentage <= 100 for percentage in reduction_percentages):
        raise ValueError("Reduction percentages must be between 0 and 100")

    patient_count = patient_metrics["case_id"].nunique()
    baseline_los = patient_metrics["baseline_los_hours"]
    discharge_delay = patient_metrics["discharge_delay_hours"]
    records = []

    for percentage in reduction_percentages:
        reduction_fraction = percentage / 100
        saved_hours = discharge_delay * reduction_fraction
        simulated_los = baseline_los - saved_hours
        records.append(
            {
                "scenario": (
                    "Baseline" if percentage == 0 else f"{percentage}% reduction"
                ),
                "discharge_delay_reduction_percentage": percentage,
                "patient_count": patient_count,
                "baseline_mean_los_hours": baseline_los.mean(),
                "simulated_mean_los_hours": simulated_los.mean(),
                "mean_los_improvement_hours": baseline_los.mean()
                - simulated_los.mean(),
                "baseline_median_los_hours": baseline_los.median(),
                "simulated_median_los_hours": simulated_los.median(),
                "median_los_improvement_hours": baseline_los.median()
                - simulated_los.median(),
                "baseline_mean_discharge_delay_hours": discharge_delay.mean(),
                "simulated_mean_discharge_delay_hours": (
                    discharge_delay * (1 - reduction_fraction)
                ).mean(),
                "total_bed_hours_saved": saved_hours.sum(),
            }
        )

    return pd.DataFrame(records)


def plot_simulation_impact(results, output_path):
    """Save a comparison chart for mean LoS and total bed-hours saved."""
    figure, los_axis = plt.subplots(figsize=(9, 5.5))
    labels = results["scenario"].tolist()
    positions = range(len(results))
    los_axis.bar(
        positions,
        results["simulated_mean_los_hours"],
        color="#4C78A8",
        label="Mean simulated LoS",
    )
    los_axis.set_xticks(list(positions), labels)
    los_axis.set_xlabel("Discharge delay reduction scenario")
    los_axis.set_ylabel("Mean length of stay (hours)", color="#4C78A8")
    los_axis.tick_params(axis="y", labelcolor="#4C78A8")
    los_axis.grid(axis="y", linestyle=":", alpha=0.5)

    capacity_axis = los_axis.twinx()
    capacity_axis.plot(
        list(positions),
        results["total_bed_hours_saved"],
        color="#F58518",
        marker="o",
        linewidth=2,
        label="Total bed-hours saved",
    )
    capacity_axis.set_ylabel("Total bed-hours saved", color="#F58518")
    capacity_axis.tick_params(axis="y", labelcolor="#F58518")

    handles, labels = los_axis.get_legend_handles_labels()
    capacity_handles, capacity_labels = capacity_axis.get_legend_handles_labels()
    los_axis.legend(
        handles + capacity_handles,
        labels + capacity_labels,
        loc="upper right",
    )
    los_axis.set_title("Projected Capacity Gain from Reducing Discharge Delays")
    figure.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(figure)


def main():
    parser = argparse.ArgumentParser(
        description="Simulate LoS and bed-hours saved by reducing discharge delays."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--visual-output", type=Path, default=DEFAULT_VISUAL_OUTPUT)
    args = parser.parse_args()

    events = load_event_log(str(args.input))
    patient_metrics = build_patient_metrics(events)
    results = simulate_reductions(patient_metrics)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(args.output, index=False)
    plot_simulation_impact(results, args.visual_output)

    print(f"Simulated discharge-delay reductions for {len(patient_metrics)} patients.")
    for _, row in results.iterrows():
        print(
            f"{row['scenario']}: mean LoS "
            f"{row['simulated_mean_los_hours']:.2f} hours "
            f"(improvement {row['mean_los_improvement_hours']:.2f}); "
            f"{row['total_bed_hours_saved']:.2f} bed-hours saved."
        )
    print(f"Wrote simulation results to {args.output}.")
    print(f"Wrote capacity impact chart to {args.visual_output}.")


if __name__ == "__main__":
    main()
