"""
13E-4C-3C-1: Persisted Observation -> Shadow Turn Evaluation.

Uses the established temporary SQLite test environment.
No production database or teaching agent is used.
"""

from datetime import timedelta

from app.services.assessment.learning_observation_shadow_v01 import (
    derive_learning_observation_v01,
)
from app.services.decision.evidence_driven_engine_v01 import (
    EvidenceDrivenDecisionEngineV01,
)
from app.services.decision.models_v01 import (
    DecisionContextV01,
    TeachingActionV01,
)
from app.services.decision.shadow_turn_evaluation_v01 import (
    evaluate_shadow_turn_v01,
)
from app.services.decision.student_request_v01 import (
    PersonalizedDecisionContextV01,
    StudentLearningRequestKindV01,
    StudentLearningRequestV01,
)
from app.services.decision.teaching_observation_context_v01 import (
    TeachingObservationContextV01,
)

from test_assessment_assistance_log_v01 import (
    NOW,
    environment,
    make_provenance_snapshot_service,
    open_stack,
    record_hint,
)


def evaluate_persisted_attempt(
    environment,
    *,
    report_hint,
    request_kind=None,
):
    """
    Persist an Attempt, reopen SQLite, then evaluate
    an Observation derived exclusively from reloaded data.

    The existing Decision Engine remains authoritative.
    """

    path, engine, assistance, service, delivery = environment

    recorded_hint = None

    if report_hint:
        recorded_hint = record_hint(
            assistance,
            delivery,
        )

    completed = service.submit_numeric_answer(
        assignment_id=delivery.assignment_id,
        response_text="5",
        as_of=NOW + timedelta(seconds=5),
    )

    assert completed.pending is None

    # Preserve the original conservative evidence result.
    assert completed.state.included_evidence_ids == []

    engine.dispose()

    reopened_engine, _, reopened_log, reopened_service = (
        open_stack(
            path,
            initialize=False,
        )
    )

    try:
        snapshot = make_provenance_snapshot_service(
            reopened_engine,
            reopened_log,
        ).build_snapshot(
            assignment_id=delivery.assignment_id,
            student_id="student-001",
            session_id="session-001",
        )

        observation = derive_learning_observation_v01(
            snapshot,
        )

        restored = reopened_service.resume(
            as_of=NOW + timedelta(seconds=5),
        )

        state = restored.state

        assert restored.pending is None
        assert state.included_evidence_ids == []
        assert state.state.value == "unknown"

        assert observation.attempt_id == snapshot.attempt_id
        assert observation.assignment_id == delivery.assignment_id

        observation_context = TeachingObservationContextV01(
            student_id=state.student_id,
            course_id=state.course_id,
            objective_id=state.objective_id,
            observations=(observation,),
        )

        student_request = None

        if request_kind is not None:
            student_request = StudentLearningRequestV01(
                objective_id=state.objective_id,
                request_kind=request_kind,
                requested_at=state.as_of,
            )

        decision_context = PersonalizedDecisionContextV01(
            decision_context=DecisionContextV01(
                decision_id="persisted-shadow-decision-001",
                objective_state=state,
                requested_at=state.as_of,
            ),
            student_request=student_request,
        )

        original_state = state.model_dump(mode="json")

        # Run the authoritative engine independently to obtain
        # the expected decision for the same inputs.
        expected_decision = (
            EvidenceDrivenDecisionEngineV01().decide(
                decision_context
            )
        )

        evaluation = evaluate_shadow_turn_v01(
            decision_context=decision_context,
            observation_context=observation_context,
            decision_engine=EvidenceDrivenDecisionEngineV01(),
        )

        assert evaluation.actual_decision == expected_decision

        assert evaluation.observation_report.existing_action == (
            expected_decision.decision.selected_action
        )

        assert evaluation.observation_report.decision_id == (
            expected_decision.decision.decision_id
        )

        assert state.model_dump(mode="json") == original_state

        assert observation_context.source_attempt_ids == (
            snapshot.attempt_id,
        )

        assert evaluation.observation_report.source_attempt_ids == (
            snapshot.attempt_id,
        )

        assert (
            evaluation.observation_report.action_execution_authorized
            is False
        )

        assert (
            evaluation.observation_report.verified_independence
            is False
        )

        assert (
            evaluation.observation_report.mastery_eligible
            is False
        )

        assert (
            evaluation.observation_report.history_order_verified
            is False
        )

        return snapshot, recorded_hint, evaluation

    finally:
        reopened_engine.dispose()


def test_persisted_hint_reaches_shadow_evaluation(environment):
    snapshot, hint, evaluation = evaluate_persisted_attempt(
        environment,
        report_hint=True,
    )

    assert hint is not None
    assert snapshot.assistance_events == (hint,)

    report = evaluation.observation_report

    assert report.observed_attempt_count == 1
    assert report.app_hint_attempt_count == 1
    assert report.app_solution_attempt_count == 0
    assert report.no_app_report_attempt_count == 0

    if report.candidate_action is not None:
        assert report.candidate_action in (
            evaluation.actual_decision.decision.allowed_actions
        )


def test_persisted_no_app_report_does_not_prove_independence(
    environment,
):
    snapshot, hint, evaluation = evaluate_persisted_attempt(
        environment,
        report_hint=False,
    )

    assert hint is None
    assert snapshot.assistance_events == ()

    report = evaluation.observation_report

    assert report.observed_attempt_count == 1
    assert report.no_app_report_attempt_count == 1
    assert report.candidate_action is None
    assert report.verified_independence is False
    assert report.mastery_eligible is False


def test_explicit_request_survives_persisted_shadow_path(
    environment,
):
    _, hint, evaluation = evaluate_persisted_attempt(
        environment,
        report_hint=True,
        request_kind=(
            StudentLearningRequestKindV01.REQUEST_EXPLANATION
        ),
    )

    assert hint is not None

    assert evaluation.actual_decision.decision.selected_action == (
        TeachingActionV01.CONCEPTUAL_REVIEW
    )

    report = evaluation.observation_report

    assert report.app_hint_attempt_count == 1
    assert report.candidate_action is None
    assert report.status == "explicit_request_preserved"
    assert report.action_execution_authorized is False
