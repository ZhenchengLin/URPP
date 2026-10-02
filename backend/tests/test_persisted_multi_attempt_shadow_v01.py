"""
13E-4C-3C-2: two persisted Attempts -> one Shadow Evaluation.

Both Attempts belong to the same Student, Course, Objective
and Session. Their Assistance Events must remain scoped to
their respective Assignments.
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
)
from app.services.decision.shadow_turn_evaluation_v01 import (
    evaluate_shadow_turn_v01,
)
from app.services.decision.student_request_v01 import (
    PersonalizedDecisionContextV01,
)
from app.services.decision.teaching_observation_context_v01 import (
    TeachingObservationContextV01,
)

from test_assessment_assistance_log_v01 import (
    NOW,
    AssessmentItemV02,
    NumericRubricV02,
    environment,
    make_provenance_snapshot_service,
    open_stack,
    record_hint,
)


def test_two_persisted_attempts_keep_assistance_scoped(
    environment,
):
    path, first_engine, first_log, first_service, first_delivery = (
        environment
    )

    # Assignment 1: the application reports one Hint.
    first_hint = record_hint(
        first_log,
        first_delivery,
    )

    first_completed = first_service.submit_numeric_answer(
        assignment_id=first_delivery.assignment_id,
        response_text="5",
        as_of=NOW + timedelta(seconds=5),
    )

    assert first_completed.pending is None
    assert first_completed.state.included_evidence_ids == []

    # Reopen the persisted Session before the next Assignment.
    first_engine.dispose()

    second_engine, assessments, second_log, _unused_service = (
        open_stack(
            path,
            initialize=False,
        )
    )

    try:
        # Create a new adapter for the second turn's explicit
        # diagnostic request. Keep the same persisted Session.
        from app.services.decision.student_request_v01 import (
            StudentLearningRequestKindV01,
            StudentLearningRequestV01,
        )
        from test_assessment_assistance_log_v01 import (
            NumericAssignmentRepositoryV01,
            NumericSessionRecordRepositoryV01,
            RecordingAgent,
            create_evidence_driven_personalized_turn_v01,
            create_personalized_recoverable_numeric_session_v01,
        )

        second_request_at = NOW + timedelta(seconds=6)

        second_request = StudentLearningRequestV01(
            objective_id="objective-001",
            request_kind=(
                StudentLearningRequestKindV01.REQUEST_DIAGNOSTIC
            ),
            requested_at=second_request_at,
        )

        second_service = (
            create_personalized_recoverable_numeric_session_v01(
                assessment_repository=assessments,
                assignment_repository=NumericAssignmentRepositoryV01(
                    assessments,
                    clock=lambda: NOW + timedelta(seconds=7),
                ),
                session_repository=NumericSessionRecordRepositoryV01(
                    assessments
                ),
                personalized_turn_orchestrator=(
                    create_evidence_driven_personalized_turn_v01(
                        professor_agent=RecordingAgent(),
                        assessment_agent=RecordingAgent(),
                    )
                ),
                student_id="student-001",
                course_id="course-001",
                objective_id="objective-001",
                session_id="session-001",
                student_request=second_request,
            )
        )

        assessments.save_item(
            AssessmentItemV02(
                assessment_item_id="item-002",
                course_id="course-001",
                objective_id="objective-001",
                prompt="What is 3 + 4?",
                rubric=NumericRubricV02(
                    expected_value=7.0,
                    absolute_tolerance=0.0,
                    rubric_version="numeric-rubric-v1",
                ),
                alignment_verified=True,
            ),
            revision=1,
        )

        resumed = second_service.resume(
            as_of=NOW + timedelta(seconds=6),
        )

        assert resumed.pending is None

        second_delivery = second_service.deliver_numeric_assessment(
            assessment_item_id="item-002",
            item_revision=1,
            decision_id="decision-002",
            requested_at=NOW + timedelta(seconds=6),
        )

        assert (
            second_delivery.assignment_id
            != first_delivery.assignment_id
        )

        # Assignment 2 has no application-reported assistance.
        second_completed = second_service.submit_numeric_answer(
            assignment_id=second_delivery.assignment_id,
            response_text="7",
            as_of=NOW + timedelta(seconds=8),
        )

        assert second_completed.pending is None
        assert second_completed.completed_assignment_ids == (
            first_delivery.assignment_id,
            second_delivery.assignment_id,
        )

        # Application-help history alone must not add
        # independently verified Mastery Evidence.
        assert second_completed.state.independent_success_count == 0

    finally:
        second_engine.dispose()

    # Reopen SQLite again: both source Attempts must now
    # come from persisted records, not in-memory objects.
    third_engine, _, third_log, third_service = open_stack(
        path,
        initialize=False,
    )

    try:
        snapshots = make_provenance_snapshot_service(
            third_engine,
            third_log,
        )

        first_snapshot = snapshots.build_snapshot(
            assignment_id=first_delivery.assignment_id,
            student_id="student-001",
            session_id="session-001",
        )

        second_snapshot = snapshots.build_snapshot(
            assignment_id=second_delivery.assignment_id,
            student_id="student-001",
            session_id="session-001",
        )

        # Help from Assignment 1 cannot leak into Assignment 2.
        assert first_snapshot.assistance_events == (first_hint,)
        assert second_snapshot.assistance_events == ()

        first_observation = derive_learning_observation_v01(
            first_snapshot,
        )

        second_observation = derive_learning_observation_v01(
            second_snapshot,
        )

        assert first_observation.reported_hint_count == 1
        assert first_observation.app_assistance_context == (
            "app_hint_reported"
        )

        assert second_observation.reported_hint_count == 0
        assert second_observation.app_assistance_context == (
            "no_app_report"
        )

        restored = third_service.resume(
            as_of=NOW + timedelta(seconds=9),
        )

        state = restored.state

        assert restored.pending is None
        assert state.included_evidence_ids == []
        assert state.independent_success_count == 0

        observation_context = TeachingObservationContextV01(
            student_id=state.student_id,
            course_id=state.course_id,
            objective_id=state.objective_id,
            observations=(
                first_observation,
                second_observation,
            ),
        )

        assert observation_context.observed_attempt_count == 2
        assert observation_context.app_hint_attempt_count == 1
        assert observation_context.app_solution_attempt_count == 0
        assert observation_context.no_app_report_attempt_count == 1

        decision_context = PersonalizedDecisionContextV01(
            decision_context=DecisionContextV01(
                decision_id="multi-attempt-shadow-decision-001",
                objective_state=state,
                requested_at=state.as_of,
            ),
            student_request=None,
        )

        original_state = state.model_dump(mode="json")

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

        report = evaluation.observation_report

        assert report.observed_attempt_count == 2
        assert report.app_hint_attempt_count == 1
        assert report.no_app_report_attempt_count == 1

        assert report.source_attempt_ids == (
            first_snapshot.attempt_id,
            second_snapshot.attempt_id,
        )

        assert report.existing_action == (
            expected_decision.decision.selected_action
        )

        if report.candidate_action is not None:
            assert report.candidate_action in (
                expected_decision.decision.allowed_actions
            )

        # Tuple order is caller-supplied; it is not a
        # verified chronological history.
        assert report.history_order_verified is False

        assert report.action_execution_authorized is False
        assert report.verified_independence is False
        assert report.mastery_eligible is False

        assert state.model_dump(mode="json") == original_state

    finally:
        third_engine.dispose()
