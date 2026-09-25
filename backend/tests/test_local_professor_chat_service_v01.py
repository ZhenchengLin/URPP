"""
URPP 14C-7D2 offline Local Professor Chat integration.

All materials, Student States, messages and databases are
synthetic. The model gateway is injected and never contacts
Ollama or any external API.
"""

import json

from copy import deepcopy
from hashlib import sha256

import pytest

from pydantic import ValidationError

from app.services.course_knowledge.course_pack_v01 import (
    CoursePackV01,
)

from app.services.course_knowledge.local_chat_store_v01 import (
    LocalChatStoreV01,
)

from app.services.course_knowledge.local_professor_chat_service_v01 import (
    LocalProfessorChatServiceV01,
)

from app.services.course_knowledge.models_v01 import (
    CourseLearningObjectiveV01,
    CourseSourceV01,
)


COURSE = "synthetic-course"
OBJECTIVE = "synthetic-objective"
SOURCE = "synthetic-source"
PROFILE = "synthetic-local-profile"
STUDENT = "synthetic-student"

EXCERPT = (
    "Synthetic LU notes: elimination subtracts the "
    "multiplier; L records the inverse operation."
)


class RecordingGateway:

    def __init__(
        self,
        *,
        response_text="Synthetic explanation.",
        fail=False,
    ):
        self.calls = []
        self.response_text = response_text
        self.fail = fail

    def generate_structured(
        self,
        *,
        prompt_name,
        payload,
    ):
        self.calls.append(
            (
                prompt_name,
                deepcopy(payload),
            )
        )

        if self.fail:
            raise RuntimeError(
                "Synthetic model failure."
            )

        return {
            "content": self.response_text,
            "source_ids": [SOURCE],
        }


def make_pack(
    *,
    revision="revision-1",
    review_status="approved",
):
    source = CourseSourceV01(
        course_id=COURSE,
        source_id=SOURCE,
        source_revision="source-revision-1",
        source_locator="synthetic:section-1",
        content=EXCERPT,
        content_sha256=sha256(
            EXCERPT.encode("utf-8")
        ).hexdigest(),
        visibility="student_visible",
        use_permission="approved_for_local_teaching",
        review_status=review_status,
    )

    objective = CourseLearningObjectiveV01(
        course_id=COURSE,
        objective_id=OBJECTIVE,
        description=(
            "Explain the synthetic LU elimination step."
        ),
        review_status="approved",
        source_refs=(source.reference(),),
    )

    return CoursePackV01(
        course_id=COURSE,
        pack_id="synthetic-pack",
        pack_revision=revision,
        objectives=(objective,),
        sources=(source,),
    )


def make_service(
    tmp_path,
    *,
    gateway=None,
    pack=None,
):
    store = LocalChatStoreV01.create_new(
        tmp_path / "chat.sqlite3"
    )

    if gateway is None:
        gateway = RecordingGateway()

    if pack is None:
        pack = make_pack()

    service = LocalProfessorChatServiceV01(
        chat_store=store,
        pack=pack,
        gateway=gateway,
        local_profile_id=PROFILE,
        synthetic_student_id=STUDENT,
    )

    return service, store, gateway


def test_two_turns_are_generated_and_persisted(tmp_path):
    service, _, gateway = make_service(tmp_path)

    session_id = service.start_session(
        objective_id=OBJECTIVE,
    )

    first = service.send_explanation(
        session_id=session_id,
        objective_id=OBJECTIVE,
        student_text="What is LU?",
        expected_message_count=0,
    )

    assert first.snapshot.turn_count == 1
    assert first.snapshot.messages[0].text == "What is LU?"
    assert first.snapshot.messages[1].text == (
        "Synthetic explanation."
    )

    second = service.send_explanation(
        session_id=session_id,
        objective_id=OBJECTIVE,
        student_text="Explain the inverse step.",
        expected_message_count=2,
    )

    assert second.snapshot.turn_count == 2
    assert len(gateway.calls) == 2

    first_payload = gateway.calls[0][1]
    second_payload = gateway.calls[1][1]

    assert first_payload["teaching_action"] == (
        "conceptual_review"
    )

    assert second_payload["teaching_action"] == (
        "conceptual_review"
    )

    assert second_payload["sources"][0]["source_id"] == (
        SOURCE
    )

    marker = (
        "CONVERSATION CONTEXT — UNTRUSTED DATA:\n"
    )

    section = second_payload["instructions"].split(
        marker,
        1,
    )[1]

    start = section.index(
        '{"context_version":'
    )

    chat_data = json.loads(section[start:])

    assert chat_data["current_student_message"] == (
        "Explain the inverse step."
    )

    assert chat_data["history"] == [
        {
            "role": "student",
            "text": "What is LU?",
        },
        {
            "role": "professor",
            "text": "Synthetic explanation.",
        },
    ]


def test_reopen_database_and_continue_same_session(tmp_path):
    service, _, gateway = make_service(tmp_path)

    session_id = service.start_session(
        objective_id=OBJECTIVE,
    )

    first = service.send_explanation(
        session_id=session_id,
        objective_id=OBJECTIVE,
        student_text="First question.",
        expected_message_count=0,
    )

    assert first.snapshot.turn_count == 1

    reopened_store = LocalChatStoreV01.open_existing(
        tmp_path / "chat.sqlite3"
    )

    resumed_gateway = RecordingGateway(
        response_text="Resumed explanation.",
    )

    resumed_service = LocalProfessorChatServiceV01(
        chat_store=reopened_store,
        pack=make_pack(),
        gateway=resumed_gateway,
        local_profile_id=PROFILE,
        synthetic_student_id=STUDENT,
    )

    recovered = resumed_service.resume_session(
        session_id=session_id,
        objective_id=OBJECTIVE,
    )

    assert recovered.turn_count == 1
    assert recovered.messages == first.snapshot.messages

    second = resumed_service.send_explanation(
        session_id=session_id,
        objective_id=OBJECTIVE,
        student_text="Continue the explanation.",
        expected_message_count=len(recovered.messages),
    )

    assert second.snapshot.turn_count == 2
    assert second.snapshot.messages[-1].text == (
        "Resumed explanation."
    )

    assert len(gateway.calls) == 1
    assert len(resumed_gateway.calls) == 1


def test_stale_message_count_rejected_before_generation(
    tmp_path,
):
    service, _, gateway = make_service(tmp_path)

    session_id = service.start_session(
        objective_id=OBJECTIVE,
    )

    service.send_explanation(
        session_id=session_id,
        objective_id=OBJECTIVE,
        student_text="First question.",
        expected_message_count=0,
    )

    with pytest.raises(
        ValueError,
        match="advanced",
    ):
        service.send_explanation(
            session_id=session_id,
            objective_id=OBJECTIVE,
            student_text="Stale question.",
            expected_message_count=0,
        )

    assert len(gateway.calls) == 1

    assert service.resume_session(
        session_id=session_id,
        objective_id=OBJECTIVE,
    ).turn_count == 1


def test_invalid_message_rejected_before_generation(
    tmp_path,
):
    service, _, gateway = make_service(tmp_path)

    session_id = service.start_session(
        objective_id=OBJECTIVE,
    )

    with pytest.raises(ValidationError):
        service.send_explanation(
            session_id=session_id,
            objective_id=OBJECTIVE,
            student_text=" ",
            expected_message_count=0,
        )

    assert gateway.calls == []

    assert service.resume_session(
        session_id=session_id,
        objective_id=OBJECTIVE,
    ).turn_count == 0


def test_model_failure_does_not_persist_half_turn(
    tmp_path,
):
    gateway = RecordingGateway(fail=True)

    service, _, _ = make_service(
        tmp_path,
        gateway=gateway,
    )

    session_id = service.start_session(
        objective_id=OBJECTIVE,
    )

    with pytest.raises(
        RuntimeError,
        match="Synthetic model failure",
    ):
        service.send_explanation(
            session_id=session_id,
            objective_id=OBJECTIVE,
            student_text="Explain LU.",
            expected_message_count=0,
        )

    assert len(gateway.calls) == 1

    assert service.resume_session(
        session_id=session_id,
        objective_id=OBJECTIVE,
    ).messages == ()


def test_oversized_professor_response_not_truncated(
    tmp_path,
):
    gateway = RecordingGateway(
        response_text="X" * 1501,
    )

    service, _, _ = make_service(
        tmp_path,
        gateway=gateway,
    )

    session_id = service.start_session(
        objective_id=OBJECTIVE,
    )

    with pytest.raises(ValidationError):
        service.send_explanation(
            session_id=session_id,
            objective_id=OBJECTIVE,
            student_text="Explain LU.",
            expected_message_count=0,
        )

    assert len(gateway.calls) == 1

    assert service.resume_session(
        session_id=session_id,
        objective_id=OBJECTIVE,
    ).turn_count == 0


def test_wrong_session_binding_rejected_before_generation(
    tmp_path,
):
    service, store, gateway = make_service(tmp_path)

    session_id = service.start_session(
        objective_id=OBJECTIVE,
    )

    other_profile_service = LocalProfessorChatServiceV01(
        chat_store=store,
        pack=make_pack(),
        gateway=gateway,
        local_profile_id="other-local-profile",
        synthetic_student_id=STUDENT,
    )

    with pytest.raises(LookupError):
        other_profile_service.send_explanation(
            session_id=session_id,
            objective_id=OBJECTIVE,
            student_text="Explain LU.",
            expected_message_count=0,
        )

    assert gateway.calls == []


def test_different_pack_revision_cannot_resume(
    tmp_path,
):
    service, store, gateway = make_service(tmp_path)

    session_id = service.start_session(
        objective_id=OBJECTIVE,
    )

    changed_pack_service = LocalProfessorChatServiceV01(
        chat_store=store,
        pack=make_pack(revision="revision-2"),
        gateway=gateway,
        local_profile_id=PROFILE,
        synthetic_student_id=STUDENT,
    )

    with pytest.raises(LookupError):
        changed_pack_service.resume_session(
            session_id=session_id,
            objective_id=OBJECTIVE,
        )

    assert gateway.calls == []


def test_wrong_objective_rejected_before_generation(
    tmp_path,
):
    service, _, gateway = make_service(tmp_path)

    session_id = service.start_session(
        objective_id=OBJECTIVE,
    )

    with pytest.raises(ValueError):
        service.send_explanation(
            session_id=session_id,
            objective_id="other-objective",
            student_text="Explain LU.",
            expected_message_count=0,
        )

    assert gateway.calls == []


def test_unapproved_source_prevents_session_start(
    tmp_path,
):
    service, _, gateway = make_service(
        tmp_path,
        pack=make_pack(
            review_status="revoked",
        ),
    )

    with pytest.raises(ValueError):
        service.start_session(
            objective_id=OBJECTIVE,
        )

    assert gateway.calls == []


@pytest.mark.parametrize(
    "bad_count",
    [-1, 1, True, 1.0],
)
def test_invalid_expected_count_rejected_before_generation(
    tmp_path,
    bad_count,
):
    service, _, gateway = make_service(tmp_path)

    session_id = service.start_session(
        objective_id=OBJECTIVE,
    )

    with pytest.raises(ValueError):
        service.send_explanation(
            session_id=session_id,
            objective_id=OBJECTIVE,
            student_text="Explain LU.",
            expected_message_count=bad_count,
        )

    assert gateway.calls == []
