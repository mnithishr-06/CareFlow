"""Check patient traces against the canonical clinical pathway with pm4py."""

import argparse
from pathlib import Path

import pandas as pd

from data_loader import EXPECTED_MILESTONES, load_event_log


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = REPOSITORY_ROOT / "data" / "raw" / "clinical_events.csv"
DEFAULT_SCORES_OUTPUT = (
    REPOSITORY_ROOT / "data" / "processed" / "conformance_scores.csv"
)
DEFAULT_SUMMARY_OUTPUT = (
    REPOSITORY_ROOT / "data" / "processed" / "conformance_summary.txt"
)


def build_canonical_petri_net():
    """Create a sequential Petri net representing the canonical seven stages."""
    from pm4py.objects.petri_net.obj import PetriNet, Marking
    from pm4py.objects.petri_net.utils import petri_utils

    net = PetriNet("careflow_canonical_seven_stage_pathway")
    places = [
        PetriNet.Place(f"p{index}_{name}")
        for index, name in enumerate(
            ["start", *[f"after_{stage}" for stage in EXPECTED_MILESTONES[:-1]], "end"]
        )
    ]
    transitions = [
        PetriNet.Transition(f"t{index}_{milestone}", milestone)
        for index, milestone in enumerate(EXPECTED_MILESTONES)
    ]

    for place in places:
        net.places.add(place)
    for transition in transitions:
        net.transitions.add(transition)
    for index, transition in enumerate(transitions):
        petri_utils.add_arc_from_to(places[index], transition, net)
        petri_utils.add_arc_from_to(transition, places[index + 1], net)

    initial_marking = Marking({places[0]: 1})
    final_marking = Marking({places[-1]: 1})
    return net, initial_marking, final_marking


def calculate_conformance(events):
    """Return per-case token-replay diagnostics and an executive summary."""
    import pm4py

    event_log = events.rename(
        columns={
            "case_id": "case:concept:name",
            "event_name": "concept:name",
            "event_timestamp": "time:timestamp",
        }
    )[["case:concept:name", "concept:name", "time:timestamp"]].copy()
    event_log = pm4py.format_dataframe(
        event_log,
        case_id="case:concept:name",
        activity_key="concept:name",
        timestamp_key="time:timestamp",
    )
    if event_log.empty:
        raise ValueError("The event log contains no patient cases")

    net, initial_marking, final_marking = build_canonical_petri_net()
    diagnostics = pm4py.conformance_diagnostics_token_based_replay(
        event_log,
        net,
        initial_marking,
        final_marking,
    )
    case_ids = event_log["case:concept:name"].drop_duplicates().tolist()
    if len(diagnostics) != len(case_ids):
        raise RuntimeError(
            "Token replay returned a different number of diagnostics than patient cases"
        )

    score_rows = []
    for case_id, result in zip(case_ids, diagnostics):
        required = ("trace_is_fit", "trace_fitness")
        missing_fields = [field for field in required if field not in result]
        if missing_fields:
            raise RuntimeError(
                f"Token replay diagnostics for case {case_id} lack {missing_fields}"
            )
        score_rows.append(
            {
                "case_id": case_id,
                "trace_is_fit": bool(result["trace_is_fit"]),
                "trace_fitness": float(result["trace_fitness"]),
                "missing_tokens": int(result.get("missing_tokens", 0)),
                "remaining_tokens": int(result.get("remaining_tokens", 0)),
                "consumed_tokens": int(result.get("consumed_tokens", 0)),
                "produced_tokens": int(result.get("produced_tokens", 0)),
            }
        )

    scores = pd.DataFrame(score_rows)
    fit_count = int(scores["trace_is_fit"].sum())
    summary = {
        "patient_cases": len(scores),
        "fitting_cases": fit_count,
        "non_fitting_cases": len(scores) - fit_count,
        "trace_fit_percentage": 100 * fit_count / len(scores),
        "mean_trace_fitness": float(scores["trace_fitness"].mean()),
        "median_trace_fitness": float(scores["trace_fitness"].median()),
        "total_missing_tokens": int(scores["missing_tokens"].sum()),
        "total_remaining_tokens": int(scores["remaining_tokens"].sum()),
    }
    return scores, summary


def write_summary(summary, output_path):
    """Write concise executive metrics with a clear model-scope caveat."""
    lines = [
        "CareFlow Token-Based Replay Conformance Summary",
        "",
        "Reference model: canonical seven-stage clinical pathway",
        "Method: pm4py token-based replay",
        "",
        f"Patient cases evaluated: {summary['patient_cases']}",
        f"Fitting cases: {summary['fitting_cases']}",
        f"Non-fitting cases: {summary['non_fitting_cases']}",
        f"Trace fit percentage: {summary['trace_fit_percentage']:.2f}%",
        f"Mean trace fitness: {summary['mean_trace_fitness']:.4f}",
        f"Median trace fitness: {summary['median_trace_fitness']:.4f}",
        f"Total missing tokens: {summary['total_missing_tokens']}",
        f"Total remaining tokens: {summary['total_remaining_tokens']}",
        "",
        "Interpretation: results measure conformance to the configured canonical "
        "sequence, not to a separately approved clinical SOP. The source event log "
        "is synthetic.",
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate patient pathway conformance by pm4py token replay."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--scores-output", type=Path, default=DEFAULT_SCORES_OUTPUT)
    parser.add_argument("--summary-output", type=Path, default=DEFAULT_SUMMARY_OUTPUT)
    args = parser.parse_args()

    events = load_event_log(str(args.input))
    scores, summary = calculate_conformance(events)
    args.scores_output.parent.mkdir(parents=True, exist_ok=True)
    scores.to_csv(args.scores_output, index=False)
    write_summary(summary, args.summary_output)

    print(
        f"Evaluated {summary['patient_cases']} cases; "
        f"{summary['fitting_cases']} fit the canonical pathway "
        f"({summary['trace_fit_percentage']:.2f}%)."
    )
    print(f"Wrote case-level scores to {args.scores_output}.")
    print(f"Wrote executive summary to {args.summary_output}.")


if __name__ == "__main__":
    main()
