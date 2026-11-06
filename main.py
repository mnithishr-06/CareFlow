"""Run the complete CareFlow analytics pipeline from the repository root."""

import argparse
import logging
import sys
import time
from pathlib import Path

import pandas as pd


REPOSITORY_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from bottleneck_simulation import (  # noqa: E402
    DEFAULT_OUTPUT as SIMULATION_OUTPUT,
    DEFAULT_VISUAL_OUTPUT as SIMULATION_VISUAL_OUTPUT,
    build_patient_metrics,
    plot_simulation_impact,
    simulate_reductions,
)
from conformance_checking import (  # noqa: E402
    DEFAULT_SCORES_OUTPUT,
    DEFAULT_SUMMARY_OUTPUT,
    calculate_conformance,
    write_summary,
)
from data_loader import load_event_log  # noqa: E402
from eda_transitions import DEFAULT_OUTPUT as TRANSITION_OUTPUT  # noqa: E402
from eda_transitions import analyze_transitions  # noqa: E402
from generate_executive_report import (  # noqa: E402
    DEFAULT_OUTPUT as EXECUTIVE_REPORT_OUTPUT,
    DEFAULT_PROCESSED_DIR,
    build_report,
    load_processed_metrics,
)
from process_mining_discovery import (  # noqa: E402
    DEFAULT_MODEL_OUTPUT,
    DEFAULT_VISUAL_OUTPUT as PETRI_NET_VISUAL_OUTPUT,
    format_event_log,
    save_visualization,
)
from sla_compliance import (  # noqa: E402
    DEFAULT_SUMMARY_OUTPUT as SLA_SUMMARY_OUTPUT,
    DEFAULT_VIOLATIONS_OUTPUT,
    evaluate_sla,
)
from variant_analysis import (  # noqa: E402
    DEFAULT_REWORK_OUTPUT,
    DEFAULT_VARIANTS_OUTPUT,
    discover_variants,
    summarize_rework,
)


LOGGER = logging.getLogger("careflow")
DEFAULT_INPUT = REPOSITORY_ROOT / "data" / "raw" / "clinical_events.csv"


def _run_stage(name, operation):
    """Run one sequential pipeline stage and log its completion and duration."""
    LOGGER.info("STARTED: %s", name)
    started_at = time.perf_counter()
    try:
        result = operation()
    except Exception:
        LOGGER.exception("FAILED: %s", name)
        raise
    elapsed = time.perf_counter() - started_at
    LOGGER.info("COMPLETED: %s (%.2f seconds)", name, elapsed)
    return result


def _ensure_parent(path):
    path.parent.mkdir(parents=True, exist_ok=True)


def run_pipeline(input_path=DEFAULT_INPUT, skip_viz=False):
    """Run validation, analytics, process mining, simulation, and reporting."""
    input_path = Path(input_path)
    output_dir = REPOSITORY_ROOT / "data" / "processed"
    output_dir.mkdir(parents=True, exist_ok=True)

    events = _run_stage(
        "Data validation",
        lambda: load_event_log(str(input_path)),
    )
    LOGGER.info(
        "Validated %s events across %s patient cases.",
        len(events),
        events["case_id"].nunique(),
    )

    def run_transition_analytics():
        rows, median_los, bottleneck = analyze_transitions(events)
        output_path = Path(TRANSITION_OUTPUT)
        _ensure_parent(output_path)
        pd.DataFrame(rows).to_csv(output_path, index=False)
        LOGGER.info(
            "Median LoS: %.3f hours; longest mean wait: %s.",
            median_los,
            bottleneck,
        )

    _run_stage("Transition analytics", run_transition_analytics)

    def run_variant_discovery():
        variants, adherence_percentage, pathways = discover_variants(events)
        rework = summarize_rework(events, pathways)
        variants.to_csv(DEFAULT_VARIANTS_OUTPUT, index=False)
        rework.to_csv(DEFAULT_REWORK_OUTPUT, index=False)
        LOGGER.info(
            "Discovered %s pathway variants; happy-path adherence %.2f%%.",
            len(variants),
            adherence_percentage,
        )

    _run_stage("Pathway variant and rework discovery", run_variant_discovery)

    def run_sla_compliance():
        violations, summary = evaluate_sla(events)
        violations.to_csv(DEFAULT_VIOLATIONS_OUTPUT, index=False)
        summary.to_csv(SLA_SUMMARY_OUTPUT, index=False)
        LOGGER.info("Recorded %s SLA breach transitions.", len(violations))

    _run_stage("SLA compliance audit", run_sla_compliance)

    def run_process_discovery():
        import pm4py

        event_log = format_event_log(events)
        event_log = pm4py.format_dataframe(
            event_log,
            case_id="case:concept:name",
            activity_key="concept:name",
            timestamp_key="time:timestamp",
        )
        net, initial_marking, final_marking = pm4py.discover_petri_net_inductive(
            event_log
        )
        _ensure_parent(DEFAULT_MODEL_OUTPUT)
        pm4py.write_pnml(
            net,
            initial_marking,
            final_marking,
            str(DEFAULT_MODEL_OUTPUT),
        )
        if not skip_viz:
            renderer = save_visualization(
                net,
                initial_marking,
                final_marking,
                PETRI_NET_VISUAL_OUTPUT,
            )
            LOGGER.info("Petri net visualization generated with %s.", renderer)
        else:
            LOGGER.info("Petri net visualization skipped (--skip-viz).")

    _run_stage("PM4Py process discovery", run_process_discovery)

    def run_conformance_checking():
        scores, summary = calculate_conformance(events)
        _ensure_parent(DEFAULT_SCORES_OUTPUT)
        scores.to_csv(DEFAULT_SCORES_OUTPUT, index=False)
        write_summary(summary, DEFAULT_SUMMARY_OUTPUT)
        LOGGER.info(
            "%s/%s cases fit the canonical pathway (%.2f%%).",
            summary["fitting_cases"],
            summary["patient_cases"],
            summary["trace_fit_percentage"],
        )

    _run_stage("Conformance checking", run_conformance_checking)

    def run_simulation():
        patient_metrics = build_patient_metrics(events)
        results = simulate_reductions(patient_metrics)
        _ensure_parent(Path(SIMULATION_OUTPUT))
        results.to_csv(SIMULATION_OUTPUT, index=False)
        if not skip_viz:
            plot_simulation_impact(results, Path(SIMULATION_VISUAL_OUTPUT))
            LOGGER.info("Simulation impact chart generated.")
        else:
            LOGGER.info("Simulation impact chart skipped (--skip-viz).")

    _run_stage("What-if bottleneck simulation", run_simulation)

    def run_executive_report():
        report = build_report(load_processed_metrics(DEFAULT_PROCESSED_DIR))
        EXECUTIVE_REPORT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        EXECUTIVE_REPORT_OUTPUT.write_text(report, encoding="utf-8")
        LOGGER.info("Wrote executive briefing to %s.", EXECUTIVE_REPORT_OUTPUT)

    _run_stage("Executive report compilation", run_executive_report)
    LOGGER.info("CareFlow pipeline completed successfully.")


def main():
    parser = argparse.ArgumentParser(
        description="Run the full CareFlow clinical process-mining pipeline."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help="Path to the clinical event log CSV.",
    )
    parser.add_argument(
        "--skip-viz",
        action="store_true",
        help="Skip process-discovery and simulation chart generation.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    run_pipeline(args.input, skip_viz=args.skip_viz)


if __name__ == "__main__":
    main()
