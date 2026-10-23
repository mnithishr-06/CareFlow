# CareFlow: Clinical Pathway Process Mining

## Week 1 Progress Write-Up

### Executive summary

Week 1 established a reproducible synthetic event-log pipeline and produced initial pathway, waiting-time, bottleneck, rework, SLA, and cohort analyses for Project 3, **CareFlow: Clinical Pathway Process Mining**. The current dataset contains 500 patient cases and 3,500 timestamped events across seven clinical milestones.

The principal baseline finding is a median admission-to-discharge length of stay (LoS) of **27.13 hours**. The longest mean stage wait is **13.65 hours** from Inpatient Ward Transfer to Discharge. These results demonstrate the analytics workflow; they are not estimates of actual hospital performance because the input is synthetic.

### Business context and objective

Hospital pathway event logs can reveal where patients wait, whether care follows an intended sequence, and where repeated work occurs. CareFlow is intended to use those records to identify operational bottlenecks, measure stage-by-stage waiting time and LoS, and assess adherence to clinical standard operating procedures (SOPs).

The target pathway is:

1. Emergency Admission
2. Triage Assessment
3. Diagnostic Lab Orders
4. Physician Consultation
5. Treatment or Surgery
6. Inpatient Ward Transfer
7. Discharge

The Week 1 work establishes a data foundation and baseline analysis that can later be applied to appropriately governed, de-identified operational event logs.

### Data pipeline and analytical outputs

- `src/generate_synthetic.py` generates the reproducible 500-patient, seven-milestone event log at `data/raw/clinical_events.csv`. The log includes case and patient identifiers, event name and timestamp, department, provider, and a deterministic synthetic severity cohort.
- `src/data_loader.py` validates the event-log schema and milestone coverage, normalizes supported event/timestamp column aliases, parses timestamps, and sorts events by case and time.
- `src/eda_transitions.py` computes patient LoS, summary statistics for consecutive-stage waits, and the longest-mean-wait bottleneck in `data/processed/transition_metrics.csv`.
- `src/process_map.py` aggregates consecutive-stage transitions into `data/processed/process_graph_edges.csv` and produces `visuals/clinical_pathway_flow.png`, highlighting the bottleneck transition.
- `src/variant_analysis.py` discovers ordered patient pathway variants and repeated-activity rework in `data/processed/pathway_variants.csv` and `data/processed/rework_summary.csv`.
- `src/sla_compliance.py` evaluates configured transition SLAs and writes case-level breach records to `data/processed/sla_violations.csv`, with department summaries in `data/processed/department_breach_summary.csv`.
- `src/cohort_analysis.py` compares LoS, mean transition waiting time, and SLA breach rates by patient cohort, writing `data/processed/cohort_metrics.csv` and `visuals/cohort_los_comparison.png`.

The scripts use repository-relative defaults and support command-line paths for the inputs and outputs where applicable. The analysis scripts rely on pandas; visualizations use matplotlib.

### Week 1 findings

#### Length of stay and stage waiting times

LoS is measured from Emergency Admission to Discharge for each case. Across 500 synthetic patient cases, the median LoS is **27.125 hours** (reported as **27.13 hours**); the mean is 27.56 hours.

| Consecutive transition | Mean wait (hours) | Median wait (hours) |
|---|---:|---:|
| Emergency Admission → Triage Assessment | 0.55 | 0.55 |
| Triage Assessment → Diagnostic Lab Orders | 1.58 | 1.62 |
| Diagnostic Lab Orders → Physician Consultation | 3.17 | 3.13 |
| Physician Consultation → Treatment or Surgery | 2.16 | 2.15 |
| Treatment or Surgery → Inpatient Ward Transfer | 6.45 | 6.25 |
| Inpatient Ward Transfer → Discharge | **13.65** | 13.51 |

The largest mean wait is the Inpatient Ward Transfer → Discharge transition, making it the current synthetic-data bottleneck. The generated process map highlights this edge in red.

#### Pathway variants and rework

The event log contains **one unique pathway variant**: all 500 cases follow the seven milestones in the target order. The calculated standard happy-path adherence is therefore **100%**. No repeated activities were detected, so the rework summary reports no rework.

These results are expected from the generator's fixed pathway structure. They validate the variant and rework calculations, but do not establish real-world SOP adherence or prove that operational patients never experience detours or repeated work.

#### SLA breaches

The initial analysis configures two example thresholds:

- Triage Assessment → Physician Consultation: no more than **1 hour**.
- Inpatient Ward Transfer → Discharge: no more than **4 hours**.

The analysis evaluates these two transitions for each of 500 cases, for **1,000 SLA-targeted transitions**. It identifies **997 breaches**, or a **99.7% breach rate** (0.3% compliance). Department-level summaries attribute each evaluated transition to the department recorded on its destination event.

These thresholds are illustrative examples, not approved clinical standards. The high breach rate reflects the synthetic delay distributions and the chosen thresholds; clinical and operational stakeholders must validate targets before using this analysis for performance decisions.

#### Cohort comparison

The source log does not contain observed Emergency/Elective admission types. To enable a comparative example, the generator adds a deterministic **synthetic severity** label (High, Moderate, or Low) per patient. The analysis requires a patient-level cohort field and defaults to `severity`.

| Synthetic severity cohort | Patients | Median LoS (hours) | Mean transition wait (hours) | SLA breaches / evaluated | Breach rate |
|---|---:|---:|---:|---:|---:|
| High | 182 | 26.63 | 4.53 | 364 / 364 | 100.00% |
| Low | 146 | 26.95 | 4.64 | 292 / 292 | 100.00% |
| Moderate | 172 | 27.88 | 4.61 | 341 / 344 | 99.13% |

The cohort comparison demonstrates the reporting workflow only. Severity labels are synthetic and are not derived from clinical assessment; the generator does not vary patient pathways based on severity. These figures must not be interpreted as evidence that patient severity causes differences in LoS or SLA performance. Real Emergency/Elective or severity comparisons require reliable cohort attributes in the source data.

### Limitations and interpretation

- All patient records, event times, departments, providers, and severity labels are synthetic. No patient-identifying or real hospital data is used.
- The generated cases have one fixed, complete milestone sequence; the current 100% adherence and zero rework findings are a property of the generated data.
- Department assignments are synthetic and should not be used to identify actual department-level performance.
- The two SLA targets are examples. They require clinical governance and operational validation before adoption.
- Current summaries provide descriptive comparisons, not causal conclusions or statistical tests.
- The current data has no Emergency/Elective admission type, clinical severity assessment, or patient outcome field. Synthetic severity supports code-path validation only.

### Week 2 roadmap

1. **Process discovery:** Apply pm4py to the event log to discover a Directly-Follows Graph (DFG), compare observed paths with the intended pathway, and document activity frequencies and variant coverage.
2. **Conformance and rework:** Add tests using controlled synthetic detours and repeated activities, then evaluate conformance against an approved SOP once its formal event and exception rules are available.
3. **Cohort analysis:** Replace the demonstration severity labels with validated, de-identified admission-type or severity attributes. Confirm cohort definitions and compare LoS, stage waits, and SLA breaches with suitable uncertainty reporting.
4. **SLA governance:** Confirm transition start/end definitions, thresholds, clock conventions, exclusions, and department attribution with clinical and operational stakeholders. Report both breach counts and denominators.
5. **BI dashboards:** Prototype dashboards for median LoS, stage-level wait distributions, bottleneck trends, pathway variants, rework, SLA breach/compliance rates, and cohort comparisons. Include filters for date range, department, and approved cohort fields.
6. **Reproducibility and quality:** Add automated tests for schema validation, boundary conditions, out-of-order and incomplete cases, rework, and aggregate reconciliation; document environment setup and the steps to regenerate all outputs.

### Summary

Week 1 delivered a working synthetic data foundation and a set of reproducible analytics and visual outputs. The baseline identifies Discharge as the longest-wait transition and demonstrates how pathway, SLA, and cohort measures can be generated. Week 2 should focus on process discovery, validated clinical definitions and source attributes, automated checks, and a clearly labeled BI prototype.
