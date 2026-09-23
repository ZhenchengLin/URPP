"""
URPP 14C-5D-13J-7 offline tests.

Synthetic credentials and Session records only.

No real students, network, database writes, model inference,
public authentication API, or teaching execution.
"""

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from app.core.dev_caller_credential_v01 import (
    DevCredentialRejectedV01,
    DevCallerObservationV01,
)

from app.core.dev_lu_session_binding_v01 import (
    DevLUSessionBindingV01,
)

from app.repositories.numeric_session_records_v01 import (
    StoredNumericSessionV01,
)

from app.services.course_knowledge import (
    controlled_lu_teaching_v01,
)

from app.services.course_knowledge.lu_focus_resolution_v01 import (
    LUFocusRequestV01,
)


TOKEN = "A" * 43
STUDENT = "synthetic-student-001"

SESSION = {
    "session_id": "synthetic-session-001",
    "student_id": STUDENT,
    "course_id": "synthetic-course-001",
    "objective_id": "synthetic-objective-001",
}


class FakeSessionRepository:

    def __init__(self, *, record=None):
        self.calls = []

        self.record = record or StoredNumericSessionV01(
            **SESSION,
            started_at=datetime(
                2026, 1, 1, tzinfo=timezone.utc
            ),
        )

    def load(self, **kwargs):
        self.calls.append(kwargs)

        if (
            kwargs["session_id"] != self.record.session_id
            or kwargs["student_id"] != self.record.student_id
            or kwargs["course_id"] != self.record.course_id
            or kwargs["objective_id"] != self.record.objective_id
        ):
            raise ValueError(
                "Stored Session scope mismatch."
            )

        return self.record


def make_binding(repository):
    return DevLUSessionBindingV01(
        configured_token=TOKEN,
        synthetic_student_id=STUDENT,
        session_repository=repository,
    )


def inspect(
    binding,
    *,
    header=None,
    focus_ids=("sign_relation",),
    **overrides,
):
    scope = {
        key: value
        for key, value in SESSION.items()
        if key != "student_id"
    }

    scope.update(overrides)

    return binding.inspect(
        authorization_header=header,
        focus_request=LUFocusRequestV01(
            requested_focus_ids=focus_ids,
        ),
        **scope,
    )


@pytest.mark.parametrize(
    "focus_id",
    ["sign_relation", "calculation"],
)
def test_valid_credential_binds_configured_student_to_session(
    focus_id,
):
    repository = FakeSessionRepository()
    binding = make_binding(repository)

    result = inspect(
        binding,
        header="Bearer " + TOKEN,
        focus_ids=(focus_id,),
    )

    assert len(repository.calls) == 1

    assert repository.calls[0]["student_id"] == STUDENT

    assert result.synthetic_student_id == STUDENT

    assert result.preflight.session_scope_matched is True

    assert result.preflight.classification.status == (
        "needs_source_verification"
    )

    assert result.preflight.classification.candidate_focus_id == (
        focus_id
    )

    assert result.status == "developer_audit_only"
    assert result.session_access_authorized is False
    assert result.lu_routing_authorized is False
    assert result.student_delivery_authorized is False


@pytest.mark.parametrize(
    "header",
    [
        None,
        "",
        "Bearer ",
        "Bearer " + ("B" * 43),
        "Basic " + TOKEN,
        "bearer " + TOKEN,
        "Bearer " + TOKEN + " ",
    ],
)
def test_invalid_credential_rejected_before_session_lookup(
    header,
):
    repository = FakeSessionRepository()
    binding = make_binding(repository)

    with pytest.raises(DevCredentialRejectedV01):
        inspect(
            binding,
            header=header,
        )

    assert repository.calls == []


@pytest.mark.parametrize(
    "focus_ids",
    [
        (),
        ("",),
        ("sign_relation", "calculation"),
        ("unknown",),
    ],
)
def test_unresolved_focus_does_not_read_session(
    focus_ids,
):
    repository = FakeSessionRepository()
    binding = make_binding(repository)

    result = inspect(
        binding,
        header="Bearer " + TOKEN,
        focus_ids=focus_ids,
    )

    assert repository.calls == []
    assert result.preflight.session_scope_matched is False

    assert result.session_access_authorized is False
    assert result.lu_routing_authorized is False
    assert result.student_delivery_authorized is False


def test_other_student_session_is_rejected():
    other_session = StoredNumericSessionV01(
        **{
            **SESSION,
            "student_id": "another-student",
        },
        started_at=datetime(
            2026, 1, 1, tzinfo=timezone.utc
        ),
    )

    repository = FakeSessionRepository(record=other_session)
    binding = make_binding(repository)

    with pytest.raises(ValueError):
        inspect(
            binding,
            header="Bearer " + TOKEN,
        )

    assert len(repository.calls) == 1
    assert repository.calls[0]["student_id"] == STUDENT


@pytest.mark.parametrize(
    "field",
    ["session_id", "course_id", "objective_id"],
)
def test_wrong_session_scope_fails_closed(field):
    repository = FakeSessionRepository()
    binding = make_binding(repository)

    with pytest.raises(ValueError):
        inspect(
            binding,
            header="Bearer " + TOKEN,
            **{field: "incorrect-value"},
        )

    assert len(repository.calls) == 1


def test_missing_session_fails_closed():
    class MissingSessionRepository:

        def load(self, **kwargs):
            raise LookupError(
                "Session does not exist."
            )

    binding = make_binding(MissingSessionRepository())

    with pytest.raises(LookupError):
        inspect(
            binding,
            header="Bearer " + TOKEN,
        )


def test_client_cannot_supply_student_id():
    repository = FakeSessionRepository()
    binding = make_binding(repository)

    with pytest.raises(TypeError):
        inspect(
            binding,
            header="Bearer " + TOKEN,
            student_id="another-student",
        )

    assert repository.calls == []


def test_forged_observation_is_not_an_accepted_input():
    repository = FakeSessionRepository()
    binding = make_binding(repository)

    forged = DevCallerObservationV01(
        synthetic_student_id=STUDENT,
    )

    with pytest.raises(TypeError):
        inspect(
            binding,
            header="Bearer " + TOKEN,
            principal=forged,
        )

    assert repository.calls == []


def test_forged_authorization_fields_cannot_grant_access():
    repository = FakeSessionRepository()
    binding = make_binding(repository)

    result = inspect(
        binding,
        header="Bearer " + TOKEN,
    )

    forged = replace(
        result,
        session_access_authorized=True,
        lu_routing_authorized=True,
    )

    assert forged.session_access_authorized is True
    assert forged.lu_routing_authorized is True

    # A forged dataclass can be constructed by arbitrary
    # Python code. It is not an access or routing credential.
    assert result.session_access_authorized is False
    assert result.lu_routing_authorized is False


def test_no_lu_teaching_execution(monkeypatch):
    repository = FakeSessionRepository()
    binding = make_binding(repository)

    def forbidden(*args, **kwargs):
        raise AssertionError(
            "Developer Session Binding must not execute teaching."
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
        binding,
        header="Bearer " + TOKEN,
    )

    assert result.lu_routing_authorized is False
    assert result.student_delivery_authorized is False
