# URPP design records

Each stage of URPP was written up as a design record before or alongside its code. Start with the overview, then read by topic.

**Start here:** [Implementations 0–14: review and analysis](URPP_00-14_review_and_analysis_v01.md)

## Foundations

| Record | Topic |
|---|---|
| [00](00_product_spec.md) | Product specification and the twelve things V0 must demonstrate |
| [01](01_architecture.md) | V0 architecture |
| [02](02_learning_objective_evidence_student_state.md) | Learning objectives, evidence events, and student state |
| [03](03_state_update_engine.md) · [03b](03b_state_update_engine_v0.2.md) | Student state update engine (V0.1 design → V0.2) |
| [03c](03c_assessment_records_and_authorization.md) | Assessment records and authorization |
| [03d](03d_logical_decision_engine.md) | Logical decision engine |
| [04](04_course_model.md) · [05](05_pedagogy_policy.md) · [06](06_session_state_machine.md) | Course model, pedagogy policy, session state machine (planned) |
| [07](07_evaluation_plan.md) | Evaluation plan: generic LLM vs. course RAG vs. URPP |
| [08](08_privacy_safety.md) | Privacy and student-model safety |
| [09](09_demo_scenario.md) | Demo scenario |

## Personalized teaching (Implementation 13B–13C)

| Record | Topic |
|---|---|
| [07](07_personalized_decision_policy_v0.1.md) · [08](08_personalized_decision_selection_v0.1.md) | Student requests and action selection |
| [09](09_personalized_teaching_turn_v0.1.md) | One decision, one agent call |
| [10](10_personalized_numeric_session_adapter_v0.1.md) · [11](11_personalized_numeric_sqlite_integration_v0.1.md) | Connecting personalized turns to recoverable SQLite sessions |

## Transfer assessment and review (Implementation 13D)

| Record | Topic |
|---|---|
| [12](12_assessment_action_eligibility_v0.1.md) | An ordinary item cannot be relabeled "transfer" by a request |
| [13](13_transfer_design_review_contract_v0.1.md) – [18](18_transfer_review_application_v0.1.md) | Review drafts, fail-closed delivery, reviewer authorization, decision history |

## Evidence-driven loop and provenance (Implementation 13E)

| Record | Topic |
|---|---|
| [19](19_evidence_driven_decision_v0.1.md) – [21](21_evidence_provenance_adaptive_loop_v0.1.md) | Choosing the next action from stored evidence |
| [22](22_assessment_assistance_log_v0.1.md) · [23](23_assessment_assistance_presentation_v0.1.md) | Logging hints and solutions without overclaiming |
| [24](24_local_numeric_teaching_cli_v0.1.md) | Local numeric teaching CLI |
| [25](25_numeric_attempt_provenance_snapshot_v0.1.md) · [26](26_numeric_provenance_review_candidate_v0.1.md) | Read-only provenance snapshots and review candidates |
| [27](27_architecture_v2_research_decision_and_roadmap_v0.2.md) | Architecture V2: research decisions and roadmap |

## The Professor (Implementation 14)

| Record | Topic |
|---|---|
| [28](28_nanojev_mps_shadow_evaluation_v0.1.md) – [30](30_nanojev_shadow_eval_v0.2_findings.md) | Shadow evaluation of a small decision model (developer-only) |
| [31](31_lu_focus_resolution_boundary_v0.1.md) · [32](32_lu_caller_session_access_boundary_v0.1.md) | LU teaching pilot boundaries |
| [Benchmark strategy](URPP_SOURCE_GROUNDED_ACCURACY_BENCHMARK_STRATEGY_v01.md) | Source-grounded accuracy benchmark |
| [Math-fidelity protocol](URPP_14D-4B4D2_math_fidelity_protocol_v01.md) · [Verified equations](URPP_14D-4B4D2A_source_verified_equations_v01.md) | 14D: protocol and source-verified equation records |
| [Completion record](URPP_14_completion_record_v01.md) · [14F revision](URPP_14F_revision_record_v01.md) | 14E benchmark results and the verified-equation route |

## Course workspace (Tier 1 user stories)

| Record | Topic |
|---|---|
| [33](33_course_workspace_tier1_v0.1.md) | Course path, lessons, check questions, adaptive next step on the website; verification and lessons from the real run |

## Next

| Record | Topic |
|---|---|
| [Implementation 15 taskbook](URPP_15_course_timeline_syllabus_taskbook_v01.md) | Course timeline and syllabus intelligence |
