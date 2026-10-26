"""Interactive Streamlit dashboard for CareFlow process analytics."""

from pathlib import Path

import pandas as pd
import streamlit as st


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DATA = REPOSITORY_ROOT / "data" / "processed"
RAW_EVENT_LOG = REPOSITORY_ROOT / "data" / "raw" / "clinical_events.csv"
SLA_TRANSITIONS_PER_PATIENT = 2
MILESTONES = [
    "Emergency_Admission",
    "Triage_Assessment",
    "Diagnostic_Lab_Orders",
    "Physician_Consultation",
    "Treatment_or_Surgery",
    "Inpatient_Ward_Transfer",
    "Discharge",
]


@st.cache_data
def load_analytics():
    """Load processed analytics and raw events used for dashboard filters."""
    files = {
        "events": RAW_EVENT_LOG,
        "transitions": PROCESSED_DATA / "transition_metrics.csv",
        "sla_violations": PROCESSED_DATA / "sla_violations.csv",
        "cohorts": PROCESSED_DATA / "cohort_metrics.csv",
        "conformance": PROCESSED_DATA / "conformance_scores.csv",
    }
    missing = [str(path) for path in files.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "Required dashboard data files are missing: " + ", ".join(missing)
        )

    events = pd.read_csv(files["events"])
    required_event_columns = {
        "case_id",
        "severity",
        "event_name",
        "event_timestamp",
        "department",
    }
    missing_columns = required_event_columns.difference(events.columns)
    if missing_columns:
        raise ValueError(f"Event log is missing columns: {sorted(missing_columns)}")
    events["event_timestamp"] = pd.to_datetime(
        events["event_timestamp"], errors="raise"
    )
    events = events.sort_values(
        ["case_id", "event_timestamp"], kind="mergesort"
    ).reset_index(drop=True)

    transitions = pd.read_csv(files["transitions"])
    sla_violations = pd.read_csv(files["sla_violations"])
    cohorts = pd.read_csv(files["cohorts"])
    conformance = pd.read_csv(files["conformance"])
    if "trace_fitness" not in conformance or "case_id" not in conformance:
        raise ValueError("Conformance scores require case_id and trace_fitness columns")
    return {
        "events": events,
        "transitions": transitions,
        "sla_violations": sla_violations,
        "cohorts": cohorts,
        "conformance": conformance,
    }


def build_case_metrics(events):
    """Compute case-level LoS, transition waits, and SLA breach counts."""
    records = []
    sla_targets = {
        ("Triage_Assessment", "Physician_Consultation"): 1.0,
        ("Inpatient_Ward_Transfer", "Discharge"): 4.0,
    }
    for case_id, case_events in events.groupby("case_id", sort=False):
        if case_events["severity"].nunique() != 1:
            raise ValueError(f"Case {case_id} has inconsistent severity cohort labels")
        if case_events["event_name"].duplicated().any():
            raise ValueError(f"Case {case_id} has repeated canonical milestones")
        case_events = case_events.set_index("event_name")
        missing = [stage for stage in MILESTONES if stage not in case_events.index]
        if missing:
            raise ValueError(f"Case {case_id} is missing milestones: {missing}")
        ordered = case_events.loc[MILESTONES]
        timestamps = ordered["event_timestamp"].tolist()
        if any(earlier > later for earlier, later in zip(timestamps, timestamps[1:])):
            raise ValueError(f"Case {case_id} has milestones out of timestamp order")

        waits = [
            (later - earlier).total_seconds() / 3600
            for earlier, later in zip(timestamps, timestamps[1:])
        ]
        breach_count = 0
        for (source, target), threshold in sla_targets.items():
            hours = (
                case_events.loc[target, "event_timestamp"]
                - case_events.loc[source, "event_timestamp"]
            ).total_seconds() / 3600
            breach_count += int(hours > threshold)

        records.append(
            {
                "case_id": case_id,
                "cohort": str(ordered["severity"].iloc[0]),
                "admission_date": timestamps[0].date(),
                "length_of_stay_hours": (
                    timestamps[-1] - timestamps[0]
                ).total_seconds()
                / 3600,
                "mean_transition_wait_hours": sum(waits) / len(waits),
                "sla_transitions_evaluated": len(sla_targets),
                "sla_breaches": breach_count,
            }
        )
    if not records:
        raise ValueError("No patient cases are available after filtering")
    return pd.DataFrame(records)


def render_dashboard(data):
    """Render KPI cards and filtered analytic views."""
    st.title("CareFlow | Clinical Pathway Analytics")
    st.caption(
        "Synthetic-data dashboard for pathway operations. Findings are illustrative "
        "and are not clinical performance estimates."
    )

    events = data["events"]
    case_metrics = build_case_metrics(events)
    departments = sorted(events["department"].dropna().unique().tolist())
    cohorts = sorted(case_metrics["cohort"].unique().tolist())
    minimum_date = case_metrics["admission_date"].min()
    maximum_date = case_metrics["admission_date"].max()

    st.sidebar.header("Filters")
    selected_date_range = st.sidebar.date_input(
        "Admission date range",
        value=(minimum_date, maximum_date),
        min_value=minimum_date,
        max_value=maximum_date,
    )
    if isinstance(selected_date_range, tuple) and len(selected_date_range) == 2:
        date_start, date_end = selected_date_range
    else:
        date_start = date_end = selected_date_range
    selected_departments = st.sidebar.multiselect(
        "Departments present in case", departments, default=departments
    )
    selected_cohorts = st.sidebar.multiselect(
        "Severity cohort", cohorts, default=cohorts
    )

    case_ids_by_department = set(
        events.loc[events["department"].isin(selected_departments), "case_id"]
    )
    filtered_cases = case_metrics.loc[
        case_metrics["admission_date"].between(date_start, date_end)
        & case_metrics["cohort"].isin(selected_cohorts)
        & case_metrics["case_id"].isin(case_ids_by_department)
    ].copy()
    if filtered_cases.empty:
        st.warning("No patient cases match the selected filters.")
        st.stop()

    selected_ids = set(filtered_cases["case_id"])
    filtered_events = events.loc[events["case_id"].isin(selected_ids)].copy()
    filtered_violations = data["sla_violations"].loc[
        data["sla_violations"]["case_id"].isin(selected_ids)
        & data["sla_violations"]["department"].isin(selected_departments)
    ].copy()
    filtered_conformance = data["conformance"].loc[
        data["conformance"]["case_id"].isin(selected_ids)
    ].copy()

    case_count = len(filtered_cases)
    breach_count = int(filtered_cases["sla_breaches"].sum())
    sla_check_count = int(filtered_cases["sla_transitions_evaluated"].sum())
    breach_rate = 100 * breach_count / sla_check_count if sla_check_count else 0.0
    mean_fitness = (
        float(filtered_conformance["trace_fitness"].mean())
        if not filtered_conformance.empty
        else 0.0
    )

    kpi_columns = st.columns(5)
    kpi_columns[0].metric("Patients", f"{case_count:,}")
    kpi_columns[1].metric(
        "Median LoS", f"{filtered_cases['length_of_stay_hours'].median():.2f} hrs"
    )
    kpi_columns[2].metric(
        "Mean transition wait",
        f"{filtered_cases['mean_transition_wait_hours'].mean():.2f} hrs",
    )
    kpi_columns[3].metric("SLA breach rate", f"{breach_rate:.1f}%")
    kpi_columns[4].metric("Mean trace fitness", f"{mean_fitness:.3f}")

    st.subheader("Transition waits")
    transition_rows = []
    for case_id, case_events in filtered_events.groupby("case_id", sort=False):
        ordered = case_events.set_index("event_name").loc[MILESTONES]
        timestamps = ordered["event_timestamp"].tolist()
        for index, (source, target) in enumerate(zip(MILESTONES, MILESTONES[1:])):
            transition_rows.append(
                {
                    "case_id": case_id,
                    "transition": f"{source.replace('_', ' ')} → {target.replace('_', ' ')}",
                    "mean_wait_hours": (
                        timestamps[index + 1] - timestamps[index]
                    ).total_seconds()
                    / 3600,
                }
            )
    transition_detail = pd.DataFrame(transition_rows)
    transition_summary = (
        transition_detail.groupby("transition", sort=False)["mean_wait_hours"]
        .mean()
        .rename("Mean wait (hours)")
        .to_frame()
    )
    st.bar_chart(transition_summary)
    with st.expander("All-case processed transition baseline"):
        st.caption(
            "This pre-aggregated reference is not recalculated by the dashboard filters."
        )
        st.dataframe(data["transitions"], width="stretch", hide_index=True)

    left, right = st.columns(2)
    with left:
        st.subheader("SLA breaches")
        st.metric("Breach records in filtered cases", f"{len(filtered_violations):,}")
        if filtered_violations.empty:
            st.info("No breach records match these filters.")
        else:
            department_breaches = (
                filtered_violations.groupby("department")
                .size()
                .rename("Breaches")
                .to_frame()
            )
            st.bar_chart(department_breaches)
            st.dataframe(
                filtered_violations[
                    [
                        "case_id",
                        "source",
                        "target",
                        "department",
                        "actual_waiting_hours",
                        "sla_target_hours",
                        "breach_hours",
                    ]
                ],
                width="stretch",
                hide_index=True,
            )

    with right:
        st.subheader("Cohort comparison")
        cohort_summary = (
            filtered_cases.groupby("cohort", sort=True)
            .agg(
                patient_count=("case_id", "nunique"),
                median_los_hours=("length_of_stay_hours", "median"),
                mean_transition_wait_hours=("mean_transition_wait_hours", "mean"),
                sla_transitions_evaluated=("sla_transitions_evaluated", "sum"),
                sla_breaches=("sla_breaches", "sum"),
            )
            .reset_index()
        )
        cohort_summary["sla_breach_rate_percentage"] = (
            100
            * cohort_summary["sla_breaches"]
            / cohort_summary["sla_transitions_evaluated"]
        )
        st.dataframe(cohort_summary, width="stretch", hide_index=True)
        with st.expander("All-case processed cohort baseline"):
            st.dataframe(data["cohorts"], width="stretch", hide_index=True)

    st.subheader("Conformance")
    fitness_bins = pd.cut(
        filtered_conformance["trace_fitness"],
        bins=10,
        include_lowest=True,
    ).value_counts(sort=False)
    fitness_bins.index = [str(interval) for interval in fitness_bins.index]
    fitness_bins = fitness_bins.rename_axis("Fitness range").rename("Cases").to_frame()
    st.bar_chart(fitness_bins)
    st.caption(
        "Token replay is measured against the configured canonical sequence, not an "
        "approved clinical SOP. The source event log and cohort labels are synthetic."
    )


def main():
    st.set_page_config(page_title="CareFlow Analytics", layout="wide")
    try:
        data = load_analytics()
    except (FileNotFoundError, ValueError, pd.errors.ParserError) as error:
        st.error(f"Unable to load CareFlow analytics: {error}")
        st.stop()
    render_dashboard(data)


if __name__ == "__main__":
    main()
