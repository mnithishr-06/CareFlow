# CareFlow: Clinical Pathway Process Mining

## Week 2 Executive Review

### Executive overview

Week 2 extended CareFlow from baseline process analytics into formal process discovery, conformance evaluation, cohort comparisons, and an interactive dashboard prototype. The work delivers a PM4Py Inductive Miner pipeline, a canonical-path token replay check, and a Streamlit dashboard that combines transition, SLA, cohort, and conformance outputs.

All reported results are based on a synthetic dataset of 500 patient cases and 3,500 events. They validate the analysis pipeline and dashboard behavior, not actual hospital operations or clinical outcomes.

### Process discovery with PM4Py

`src/process_mining_discovery.py` converts the source event fields into PM4Py's standard event-log columns:

- `case:concept:name`
- `concept:name`
- `time:timestamp`

It applies PM4Py's Inductive Miner to the patient traces and exports the discovered Petri net to `models/clinical_petri_net.pnml`. The checked-in model contains 8 places, 7 transitions, and 14 arcs. A visualization is saved to `visuals/petri_net_discovered.png`.

The execution environment did not have Graphviz's `dot` executable. The script reported this and used its matplotlib fallback to produce the visualization instead. The PNML model was read back successfully after export.

The event generator currently creates a single complete seven-stage sequence for every patient. Consequently, the discovered model represents that standard synthetic route; it does not yet demonstrate real-world detours, concurrency, optional care, or rework behavior.

### Conformance checking

`src/conformance_checking.py` builds a canonical sequential Petri net for the seven target milestones and performs PM4Py token-based replay for every case. It writes per-case fitness and token diagnostics to `data/processed/conformance_scores.csv` and an executive summary to `data/processed/conformance_summary.txt`.

Current results:

| Measure | Result |
|---|---:|
| Patient cases evaluated | 500 |
| Fitting cases | 500 |
| Non-fitting cases | 0 |
| Trace fit percentage | 100.00% |
| Mean trace fitness | 1.0000 |
| Median trace fitness | 1.0000 |

The replay confirms that generated cases match the configured canonical sequence. It does not establish conformance with an independently approved clinical SOP, because no formally governed protocol model or exception rules are included. The 100% fit is expected from the generator's fixed pathway and should not be interpreted as a real-world adherence rate.

### Dashboard capabilities

`src/dashboard_app.py` provides an interactive Streamlit dashboard that brings together:

- **Filters:** admission date range, departments present in a case, and synthetic severity cohort.
- **KPI cards:** filtered patient count, median LoS, mean transition wait, SLA breach rate, and mean token-replay fitness.
- **Transition analysis:** selected-case average waits across the six consecutive milestones, with the precomputed all-case transition baseline available for reference.
- **SLA review:** filtered breach counts by destination department and case-level details including actual wait, target, and excess breach hours.
- **Cohort comparison:** filtered patient counts, median LoS, mean transition wait, SLA check totals, and breach rate by cohort, alongside the all-case cohort baseline.
- **Conformance view:** filtered trace-fitness distribution.

Start the application from the repository root after installing Streamlit and the project's Python analytics dependencies:

```powershell
py -3 -m pip install streamlit pandas numpy pm4py matplotlib networkx
py -3 -m streamlit run src/dashboard_app.py
```

The dashboard labels the data as synthetic and distinguishes filtered case metrics from pre-aggregated all-case baselines. The precomputed transition and cohort tables do not change with dashboard filters; filtered views are recomputed from case-level event and conformance data.

### Clinical operations review and recommendations

Earlier baseline analysis identified a median LoS of **27.13 hours** and a longest mean wait of **13.65 hours** from Inpatient Ward Transfer to Discharge. Under the illustrative SLA thresholds currently configured (Triage Assessment to Physician Consultation within 1 hour; Inpatient Ward Transfer to Discharge within 4 hours), 997 of 1,000 evaluated transitions breached a target. These results reflect generated delays and example thresholds only.

Recommended next steps for a real operational pilot:

1. **Validate clinical definitions first.** Ask clinical and operational owners to approve milestone definitions, event timestamps, SLA clocks, exclusions, escalation rules, and the canonical pathway's allowed exceptions.
2. **Review discharge coordination as a hypothesis.** The synthetic results point to the Inpatient Ward Transfer to Discharge interval as the largest wait. On governed operational data, examine discharge readiness, medication reconciliation, transport, documentation, and downstream bed/placement constraints before selecting interventions.
3. **Do not rank real departments using synthetic assignments.** Current department labels are generated and destination-event attribution is a prototype convention. Confirm accountable ownership for each transition and use validated source-system department data.
4. **Validate cohorts before comparing them.** The current severity labels are deterministic synthetic values, not clinical assessments. Replace them with approved, de-identified admission-type or severity fields, then report denominators and uncertainty for cohort differences.
5. **Test discovery and conformance with meaningful variation.** Add controlled test traces for approved detours, repeated activities, missing milestones, and reordered events. Compare discovery and token-replay results against a formally approved protocol model.
6. **Pilot dashboards with governance and privacy controls.** Use role-appropriate access, minimum necessary fields, de-identification, auditability, refresh monitoring, and clear synthetic-versus-operational labeling before connecting real data.

These are validation and investigation priorities, not clinical recommendations to change care based on synthetic results.

### Limitations and interpretation

- The event log, provider IDs, department assignments, and severity cohorts are synthetic; no real patient records are represented.
- The generated cases follow one complete canonical route. Current pathway adherence and conformance scores are therefore properties of the test data.
- SLA thresholds are examples and have not been approved as clinical targets.
- The available cohort attribute is generated severity, not observed Emergency/Elective admission type or validated clinical acuity.
- Dashboard charts are descriptive. They do not establish causation or clinical significance.
- The prototype reads local CSV outputs and has no production refresh, authentication, authorization, or deployment configuration.

### Week 3 priorities

- Obtain approved, de-identified operational event data and a formally reviewed pathway/SOP reference.
- Agree on definitions, timestamp semantics, cohort fields, SLA thresholds, department ownership, and exception handling.
- Test data quality, conformance behavior, and metric reconciliation using controlled variants and reviewed edge cases.
- Revalidate the discharge bottleneck and SLA findings using operational denominators and appropriate cohort comparisons.
- Review dashboard privacy, access controls, refresh cadence, ownership, and deployment requirements before a broader BI rollout.

### Conclusion

Week 2 delivered formal model discovery, token-based replay, and an interactive analytics prototype on top of the Week 1 pipeline. The outputs provide a reproducible technical baseline and indicate which operational questions to investigate next. Any clinical or resource-allocation decision must wait for validated real-world data, governed definitions, and clinical review.
