"""Create a clinical pathway edge list and process flow visualization."""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from data_loader import EXPECTED_MILESTONES, load_event_log


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = REPOSITORY_ROOT / "data" / "raw" / "clinical_events.csv"
DEFAULT_EDGES_OUTPUT = (
    REPOSITORY_ROOT / "data" / "processed" / "process_graph_edges.csv"
)
DEFAULT_VISUAL_OUTPUT = (
    REPOSITORY_ROOT / "visuals" / "clinical_pathway_flow.png"
)


def build_transition_edges(events):
    """Aggregate consecutive milestone transitions across patient cases."""
    transition_waits = {
        (source, target): []
        for source, target in zip(EXPECTED_MILESTONES, EXPECTED_MILESTONES[1:])
    }

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
        timestamps = case_events.loc[
            EXPECTED_MILESTONES, "event_timestamp"
        ].tolist()
        if any(earlier > later for earlier, later in zip(timestamps, timestamps[1:])):
            raise ValueError(f"Case {case_id} has milestones out of clinical pathway order")

        for index, (source, target) in enumerate(
            zip(EXPECTED_MILESTONES, EXPECTED_MILESTONES[1:])
        ):
            wait_hours = (timestamps[index + 1] - timestamps[index]).total_seconds() / 3600
            transition_waits[(source, target)].append(wait_hours)

    if not transition_waits or not next(iter(transition_waits.values()), []):
        raise ValueError("The event log contains no patient transitions to summarize")

    rows = [
        {
            "source": source,
            "target": target,
            "patient_count": len(wait_hours),
            "mean_waiting_hours": sum(wait_hours) / len(wait_hours),
        }
        for (source, target), wait_hours in transition_waits.items()
    ]
    return pd.DataFrame(rows)


def plot_process_map(edges, output_path):
    """Render the pathway as a left-to-right map and highlight its bottleneck."""
    bottleneck_index = edges["mean_waiting_hours"].idxmax()
    bottleneck = edges.loc[bottleneck_index]
    positions = {
        milestone: (index, 0)
        for index, milestone in enumerate(EXPECTED_MILESTONES)
    }

    figure, axis = plt.subplots(figsize=(18, 5.5))
    axis.set_xlim(-0.5, len(EXPECTED_MILESTONES) - 0.5)
    axis.set_ylim(-1.05, 1.1)
    axis.axis("off")
    axis.set_title("Clinical Pathway Process Map", fontsize=17, weight="bold", pad=20)

    for milestone, (x, y) in positions.items():
        axis.text(
            x,
            y,
            milestone.replace("_", "\n"),
            ha="center",
            va="center",
            fontsize=9,
            color="white",
            weight="bold",
            bbox={
                "boxstyle": "round,pad=0.55",
                "facecolor": "#b42318" if milestone in {bottleneck["source"], bottleneck["target"]} else "#2364aa",
                "edgecolor": "#b42318" if milestone in {bottleneck["source"], bottleneck["target"]} else "#174a7e",
                "linewidth": 2 if milestone in {bottleneck["source"], bottleneck["target"]} else 1,
            },
        )

    for row_index, edge in edges.iterrows():
        source_x = positions[edge["source"]][0]
        target_x = positions[edge["target"]][0]
        is_bottleneck = row_index == bottleneck_index
        color = "#d62728" if is_bottleneck else "#667085"
        axis.annotate(
            "",
            xy=(target_x - 0.46, 0),
            xytext=(source_x + 0.46, 0),
            arrowprops={
                "arrowstyle": "-|>",
                "color": color,
                "linewidth": 3 if is_bottleneck else 1.8,
                "connectionstyle": "arc3,rad=0",
            },
            zorder=0,
        )
        axis.text(
            (source_x + target_x) / 2,
            0.33,
            f"{edge['mean_waiting_hours']:.2f} h mean\n"
            f"{int(edge['patient_count'])} patients",
            ha="center",
            va="bottom",
            fontsize=8,
            color=color,
            weight="bold" if is_bottleneck else "normal",
        )

    axis.text(
        0.5,
        -0.39,
        f"Longest mean wait: {bottleneck['source']} -> {bottleneck['target']} "
        f"({bottleneck['mean_waiting_hours']:.2f} hours)",
        transform=axis.transAxes,
        ha="center",
        va="center",
        color="#b42318",
        fontsize=10,
        weight="bold",
    )
    figure.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(figure)


def main():
    parser = argparse.ArgumentParser(
        description="Generate clinical pathway transition edges and a process map."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--edges-output", type=Path, default=DEFAULT_EDGES_OUTPUT)
    parser.add_argument("--visual-output", type=Path, default=DEFAULT_VISUAL_OUTPUT)
    args = parser.parse_args()

    events = load_event_log(str(args.input))
    edges = build_transition_edges(events)
    args.edges_output.parent.mkdir(parents=True, exist_ok=True)
    edges.to_csv(args.edges_output, index=False)
    plot_process_map(edges, args.visual_output)

    bottleneck = edges.loc[edges["mean_waiting_hours"].idxmax()]
    print(f"Generated {len(edges)} transitions for {events['case_id'].nunique()} patient cases.")
    print(
        f"Bottleneck: {bottleneck['source']} -> {bottleneck['target']} "
        f"({bottleneck['mean_waiting_hours']:.2f} mean waiting hours)."
    )
    print(f"Wrote edge list to {args.edges_output}.")
    print(f"Wrote process map to {args.visual_output}.")


if __name__ == "__main__":
    main()
