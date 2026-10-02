"""
URPP 14C-5D-13H: Session-Scoped Focus Preflight tests.

Synthetic repository and session records only.

No database, network, model, student record,
teaching execution, or student-facing delivery.
"""

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from app.repositories.numeric_session_records_v01 import (
    StoredNumericSessionV01,
)

from app.services.course_knowledge import (
    controlled_lu_teaching_v01,
)

from app.services.course_knowledge.lu_focus_resolution_v01 import (
    LUFocusRequestV01,
)

from app.services.course_knowledge.lu_focus_session_preflight_v01 import (
    inspect_lu_focus_session_v01,
)


SESSION = {
    "session_id": "synthetic-session-01",
    "student_id": "synthetic-student-01",
    "course_id": "synthetic-course-01",
    "objective_id": "synthetic-objective-01",
}


class FakeSessionRepository:
    def __init__(self, record=None):
        self.calls = 0

        self.record = record or StoredNumericSessionV01(
            **SESSION,
            started_at=datetime(
                2026, 1, 1, tzinfo=timezone.utc
            ),
        )

    def load(self, **kwargs):
        self.calls += 1

        if any(
            getattr(self.record, key) != value
            for key, value in kwargs.items()
        ):
            raise ValueError(
                "Stored Session scope mismatch."
            )

        return self.record


def inspect(focus_ids, repository, **overrides):
    scope = dict(SESSION)
    scope.update(overrides)

    return inspect_lu_focus_session_v01(
        request=LUFocusRequestV01(
            requested_focus_ids=focus_ids,
        ),
        session_repository=repository,
        **scope,
    )


@pytest.mark.parametrize(
    "focus_id",
    ["sign_relation", "calculation"],
)
def test_supported_focus_checks_stored_session_scope(
    focus_id,
):
    repository = FakeSessionRepository()

    result = inspect(
        (focus_id,),
        repository,
    )

    assert repository.calls == 1
    assert result.session_scope_matched is True

    assert result.classification.status == (
        "needs_source_verification"
    )

    assert result.classification.candidate_focus_id == focus_id

    assert result.caller_authenticated is False
    assert result.routing_authorized is False
    assert result.student_delivery_authorized is False

    assert result.status == "developer_audit_only"


@pytest.mark.parametrize(
    "focus_ids",
    [
        (),
        ("",),
        ("sign_relation", "calculation"),
        ("sign_relation", "sign_relation"),
        ("unknown",),
    ],
)
def test_unresolved_focus_never_reads_session(focus_ids):
    repository = FakeSessionRepository()

    result = inspect(
        focus_ids,
        repository,
    )

    assert repository.calls == 0
    assert result.session_scope_matched is False

    assert result.routing_authorized is False
    assert result.student_delivery_authorized is False


@pytest.mark.parametrize(
    "scope_field",
    [
        "session_id",
        "student_id",
        "course_id",
        "objective_id",
    ],
)
def test_scope_mismatch_fails_closed(scope_field):
    repository = FakeSessionRepository()

    with pytest.raises(ValueError):
        inspect(
            ("sign_relation",),
            repository,
            **{scope_field: "incorrect-value"},
        )

    assert repository.calls == 1


def test_missing_stored_session_fails_closed():
    class MissingSessionRepository:
        def load(self, **kwargs):
            raise LookupError(
                "Session was not found."
            )

    with pytest.raises(LookupError):
        inspect(
            ("calculation",),
            MissingSessionRepository(),
        )


@pytest.mark.parametrize(
    "invalid",
    [
        None,
        "",
        " ",
        "x" * 129,
        123,
        True,
    ],
)
def test_invalid_scope_identifier_rejected_before_read(invalid):
    repository = FakeSessionRepository()

    with pytest.raises(ValueError):
        inspect(
            ("sign_relation",),
            repository,
            session_id=invalid,
        )

    assert repository.calls == 0


def test_invalid_repository_rejected():
    with pytest.raises(TypeError):
        inspect(
            ("sign_relation",),
            object(),
        )


def test_unexpected_repository_record_rejected():
    class InvalidRepository:
        def load(self, **kwargs):
            return dict(SESSION)

    with pytest.raises(TypeError):
        inspect(
            ("sign_relation",),
            InvalidRepository(),
        )


def test_repository_returned_scope_is_rechecked():
    record = StoredNumericSessionV01(
        **{
            **SESSION,
            "student_id": "another-student",
        },
        started_at=datetime(
            2026, 1, 1, tzinfo=timezone.utc
        ),
    )

    class IncorrectRepository:
        def load(self, **kwargs):
            return record

    with pytest.raises(ValueError):
        inspect(
            ("sign_relation",),
            IncorrectRepository(),
        )


def test_scope_match_does_not_authorize_routing():
    result = inspect(
        ("sign_relation",),
        FakeSessionRepository(),
    )

    assert result.session_scope_matched is True
    assert result.caller_authenticated is False
    assert result.routing_authorized is False

    # An arbitrary caller may construct another dataclass.
    # Neither this result nor a modified copy is an
    # authorization credential.

    forged = replace(
        result,
        routing_authorized=True,
    )

    assert forged.routing_authorized is True

    assert result.routing_authorized is False


def test_preflight_does_not_execute_lu_teaching(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError(
            "Preflight must not execute teaching."
        )

    monkeypatch.setattr(
        controlled_lu_teaching_v01,
        "select_pilot_plan_v01",
        forbidden,
    )

    monkeypatch.setattr(
        controlled_lu_teaching_v01,
        "render_verified_lu_pilot_v01",
        forbidden,
    )

    result = inspect(
        ("sign_relation",),
        FakeSessionRepository(),
    )

    assert result.routing_authorized is False
    assert result.student_delivery_authorized is False
