"""
URPP Design 01C — Versioned Assessment Repository tests.

Uses an isolated SQLite database. No production database
or credentials are required.
"""

from datetime import datetime, timezone

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


def make_item(expected=5.0):
    return AssessmentItemV02(
        assessment_item_id="item-001",
        course_id="course-001",
        objective_id="objective-addition",
        prompt="What is 2 + 3?",
        rubric=NumericRubricV02(
            expected_value=expected,
            absolute_tolerance=0.0,
            rubric_version="addition-rubric-v1",
        ),
        alignment_verified=True,
    )


def make_attempt(**changes):
    data = {
        "attempt_id": "attempt-001",
        "student_id": "student-001",
        "course_id": "course-001",
        "session_id": "session-001",
        "objective_id": "objective-addition",
        "assessment_item_id": "item-001",
        "source_message_id": "message-001",
        "response_group_id": "response-001",
        "response_text": "5",
        "assistance_level": 0,
        "prior_solution_exposure": False,
        "novelty": "novel",
        "submitted_at": NOW,
    }

    data.update(changes)

    return StudentAttemptV02(**data)


def test_numeric_item_round_trip(repository):
    original = make_item()

    repository.save_item(original, revision=1)

    loaded = repository.load_item(
        "item-001",
        revision=1,
    )

    assert loaded.model_dump() == original.model_dump()


def test_item_revision_cannot_be_overwritten(repository):
    repository.save_item(make_item(), revision=1)

    with pytest.raises(ValueError, match="cannot be overwritten"):
        repository.save_item(
            make_item(expected=7.0),
            revision=1,
        )

    original = repository.load_item(
        "item-001",
        revision=1,
    )

    assert original.rubric.expected_value == 5.0


def test_new_revision_preserves_old_rubric(repository):
    repository.save_item(make_item(expected=5.0), revision=1)
    repository.save_item(make_item(expected=7.0), revision=2)

    first = repository.load_item(
        "item-001",
        revision=1,
    )

    second = repository.load_item(
        "item-001",
        revision=2,
    )

    assert first.rubric.expected_value == 5.0
    assert second.rubric.expected_value == 7.0


def test_attempt_is_bound_to_item_revision(repository):
    repository.save_item(make_item(expected=5.0), revision=1)
    repository.save_item(make_item(expected=7.0), revision=2)

    repository.save_attempt(
        make_attempt(),
        item_revision=1,
    )

    loaded_attempt, revision = repository.load_attempt(
        "attempt-001"
    )

    original_item = repository.load_item(
        loaded_attempt.assessment_item_id,
        revision=revision,
    )

    assert loaded_attempt.response_text == "5"
    assert revision == 1
    assert original_item.rubric.expected_value == 5.0


def test_unknown_item_revision_is_rejected(repository):
    with pytest.raises(LookupError, match="not found"):
        repository.save_attempt(
            make_attempt(),
            item_revision=99,
        )


def test_mismatched_attempt_scope_is_rejected(repository):
    repository.save_item(make_item(), revision=1)

    with pytest.raises(ValueError, match="does not match"):
        repository.save_attempt(
            make_attempt(course_id="different-course"),
            item_revision=1,
        )


def test_attempt_identity_cannot_be_reused(repository):
    repository.save_item(make_item(), revision=1)

    repository.save_attempt(
        make_attempt(),
        item_revision=1,
    )

    with pytest.raises(ValueError, match="cannot be reused"):
        repository.save_attempt(
            make_attempt(response_text="7"),
            item_revision=1,
        )

    loaded_attempt, _ = repository.load_attempt(
        "attempt-001"
    )

    assert loaded_attempt.response_text == "5"


def test_open_response_item_round_trip(repository):
    item = OpenResponseAssessmentItemV02(
        assessment_item_id="open-item-001",
        course_id="course-001",
        objective_id="objective-001",
        prompt="Explain the concept.",
        rubric=OpenResponseRubricV02(
            rubric_version="explanation-rubric-v1",
            criteria=[
                OpenResponseCriterionV02(
                    criterion_id="definition",
                    description="Define the concept.",
                    full_credit_guidance="Provide a definition.",
                    weight=1.0,
                ),
            ],
        ),
    )

    repository.save_item(item, revision=1)

    loaded = repository.load_item(
        "open-item-001",
        revision=1,
    )

    assert loaded.model_dump() == item.model_dump()


@pytest.mark.parametrize("revision", [0, -1, True])
def test_invalid_revision_is_rejected(repository, revision):
    with pytest.raises(ValueError, match="positive integer"):
        repository.save_item(
            make_item(),
            revision=revision,
        )
