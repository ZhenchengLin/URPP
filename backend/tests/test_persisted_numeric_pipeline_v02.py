"""
URPP Design 01C — Persisted Numeric Assessment Pipeline tests.

The SQLite database is isolated for each test.
"""

from datetime import datetime, timedelta, timezone

import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.repositories.assessment_records_v02 import (
    AssessmentRecordRepositoryV02,
    Base,
)

from app.services.assessment.models_v02 import (
    AssessmentItemV02,
    NumericRubricV02,
    StudentAttemptV02,
)

from app.services.assessment.open_response_models_v02 import (
    OpenResponseAssessmentItemV02,
    OpenResponseCriterionV02,
    OpenResponseRubricV02,
)

from app.services.assessment.persisted_numeric_pipeline_v02 import (
    PersistedNumericAssessmentServiceV02,
)


NOW = datetime(2026, 9, 19, tzinfo=timezone.utc)


@pytest.fixture
def repository():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:"
    )

    Base.metadata.create_all(engine)

    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    repo = AssessmentRecordRepositoryV02(factory)

    yield repo

    engine.dispose()


def make_item(
    *,
    item_id="item-001",
    expected=5.0,
):
    return AssessmentItemV02(
        assessment_item_id=item_id,
        course_id="course-001",
        objective_id="objective-addition",
        prompt="Enter the numeric answer.",
        rubric=NumericRubricV02(
            expected_value=expected,
            absolute_tolerance=0.0,
            rubric_version="numeric-rubric-v1",
        ),
        alignment_verified=True,
    )


def make_attempt(
    *,
    attempt_id="attempt-001",
    item_id="item-001",
    response="5",
    student_id="student-001",
):
    return StudentAttemptV02(
        attempt_id=attempt_id,
        student_id=student_id,
        course_id="course-001",
        session_id="session-001",
        objective_id="objective-addition",
        assessment_item_id=item_id,
        source_message_id=f"message-{attempt_id}",
        response_group_id=f"response-{attempt_id}",
        response_text=response,
        assistance_level=0,
        prior_solution_exposure=False,
        novelty="novel",
        submitted_at=NOW,
    )


def estimate(repository, attempt_ids, **overrides):
    parameters = {
        "student_id": "student-001",
        "course_id": "course-001",
        "objective_id": "objective-addition",
        "as_of": NOW + timedelta(seconds=1),
    }

    parameters.update(overrides)

    return PersistedNumericAssessmentServiceV02(
        repository
    ).estimate_from_attempt_ids(
        attempt_ids,
        **parameters,
    )


def test_stored_numeric_attempt_reaches_state_engine(repository):
    repository.save_item(make_item(), revision=1)

    repository.save_attempt(
        make_attempt(),
        item_revision=1,
    )

    result = estimate(
        repository,
        ["attempt-001"],
    )

    assert result.performance_estimate == 1.0
    assert result.distinct_assessment_count == 1
    assert result.state.value == "unknown"


def test_historical_attempt_uses_original_rubric(repository):
    repository.save_item(
        make_item(expected=5.0),
        revision=1,
    )

    repository.save_attempt(
        make_attempt(response="5"),
        item_revision=1,
    )

    repository.save_item(
        make_item(expected=7.0),
        revision=2,
    )

    result = estimate(
        repository,
        ["attempt-001"],
    )

    assert result.performance_estimate == 1.0


def test_new_attempt_uses_new_rubric_revision(repository):
    repository.save_item(
        make_item(expected=5.0),
        revision=1,
    )

    repository.save_item(
        make_item(expected=7.0),
        revision=2,
    )

    repository.save_attempt(
        make_attempt(response="5"),
        item_revision=2,
    )

    result = estimate(
        repository,
        ["attempt-001"],
    )

    assert result.performance_estimate == 0.0


def test_two_stored_independent_successes_can_establish_competence(
    repository,
):
    repository.save_item(
        make_item(
            item_id="item-001",
            expected=5.0,
        ),
        revision=1,
    )

    repository.save_item(
        make_item(
            item_id="item-002",
            expected=7.0,
        ),
        revision=1,
    )

    repository.save_attempt(
        make_attempt(
            attempt_id="attempt-001",
            item_id="item-001",
            response="5",
        ),
        item_revision=1,
    )

    repository.save_attempt(
        make_attempt(
            attempt_id="attempt-002",
            item_id="item-002",
            response="7",
        ),
        item_revision=1,
    )

    result = estimate(
        repository,
        ["attempt-001", "attempt-002"],
    )

    assert result.distinct_assessment_count == 2
    assert result.independent_success_count == 2
    assert result.state.value == "competent"


def test_unknown_attempt_is_rejected(repository):
    with pytest.raises(LookupError, match="not found"):
        estimate(
            repository,
            ["missing-attempt"],
        )


def test_empty_attempt_list_is_rejected(repository):
    with pytest.raises(ValueError, match="At least one"):
        estimate(repository, [])


def test_duplicate_attempt_ids_are_rejected(repository):
    repository.save_item(make_item(), revision=1)

    repository.save_attempt(
        make_attempt(),
        item_revision=1,
    )

    with pytest.raises(ValueError, match="Duplicate"):
        estimate(
            repository,
            ["attempt-001", "attempt-001"],
        )


def test_attempt_cannot_be_used_for_another_student(repository):
    repository.save_item(make_item(), revision=1)

    repository.save_attempt(
        make_attempt(student_id="student-001"),
        item_revision=1,
    )

    with pytest.raises(ValueError, match="does not match"):
        estimate(
            repository,
            ["attempt-001"],
            student_id="student-002",
        )


def test_open_response_item_is_not_silently_scored(repository):
    item = OpenResponseAssessmentItemV02(
        assessment_item_id="open-001",
        course_id="course-001",
        objective_id="objective-addition",
        prompt="Explain the concept.",
        rubric=OpenResponseRubricV02(
            rubric_version="open-rubric-v1",
            criteria=[
                OpenResponseCriterionV02(
                    criterion_id="explanation",
                    description="Explain the concept.",
                    full_credit_guidance="Give a correct explanation.",
                    weight=1.0,
                )
            ],
        ),
    )

    repository.save_item(
        item,
        revision=1,
    )

    repository.save_attempt(
        make_attempt(
            item_id="open-001",
            response="An explanation.",
        ),
        item_revision=1,
    )

    with pytest.raises(TypeError, match="numeric"):
        estimate(
            repository,
            ["attempt-001"],
        )


def test_single_string_is_not_treated_as_attempt_id_list(repository):
    with pytest.raises(TypeError, match="sequence"):
        estimate(
            repository,
            "attempt-001",
        )
