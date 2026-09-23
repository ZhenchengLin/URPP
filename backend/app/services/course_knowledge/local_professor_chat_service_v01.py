"""
URPP 14C-7D2: developer-only durable Local Professor Chat.

Connect the existing version-pinned Course Knowledge fetch,
Decision Engine, Structured Professor Adapter, per-turn
Conversation Context, and SQLite Chat Store.

One call generates one explanation and, after successful
validation, atomically saves one complete Student/Professor
exchange.

This service is for a single-user, serial local pilot.

It does not implement authentication, public student delivery,
assessment issuance, mastery updates, or exactly-once model
generation across process crashes.

A local_profile_id is a logical binding, NOT authentication.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.services.course_knowledge.course_pack_v01 import (
    CoursePackV01,
)

from app.services.course_knowledge.knowledge_fetch_v01 import (
    CourseKnowledgeFetchRequestV01,
    CourseKnowledgeFetcherV01,
    InMemoryCoursePackStoreV01,
    course_pack_digest_v01,
)

from app.services.course_knowledge.local_chat_context_v01 import (
    ConversationMessageV01,
    ConversationScopedGatewayV01,
)

from app.services.course_knowledge.local_chat_store_v01 import (
    LocalChatSnapshotV01,
    LocalChatStoreV01,
)

from app.services.course_knowledge.structured_professor_adapter_v01 import (
    StructuredProfessorAdapterV01,
)

from app.services.course_knowledge.teaching_harness_v01 import (
    CourseGroundedTeachingHarnessV01,
    CourseGroundedTeachingResultV01,
)

from app.services.decision.personalized_engine_v01 import (
    PersonalizedDecisionEngineV01,
)

from app.services.decision.student_request_v01 import (
    StudentLearningRequestKindV01,
    StudentLearningRequestV01,
)

from app.services.student_model.state_update_v02 import (
    estimate_objective_state,
)


@dataclass(frozen=True)
class LocalProfessorChatTurnV01:
    """
    One generated explanation and its committed Chat snapshot.

    The generated text has passed structural checks, but has
    not been independently verified for mathematical accuracy.

    This result is not student-delivery or mastery evidence.
    """

    teaching_result: CourseGroundedTeachingResultV01

    snapshot: LocalChatSnapshotV01

    @property
    def professor_text(self) -> str:
        return self.teaching_result.completed_turn.content


class LocalProfessorChatServiceV01:
    """
    Compose one local Professor with an exact Course Pack.

    The same Service can be reconstructed after reopening its
    SQLite database, provided the caller supplies the same
    Course Pack snapshot and local profile binding.
    """

    def __init__(
        self,
        *,
        chat_store: LocalChatStoreV01,
        pack: CoursePackV01,
        gateway: Any,
        local_profile_id: str,
        synthetic_student_id: str,
    ) -> None:

        if not isinstance(chat_store, LocalChatStoreV01):
            raise TypeError(
                "Expected LocalChatStoreV01."
            )

        if not isinstance(pack, CoursePackV01):
            raise TypeError(
                "Expected CoursePackV01."
            )

        # Validate the provider interface without invoking it.
        StructuredProfessorAdapterV01(
            gateway=gateway,
        )

        self._local_profile_id = self._identifier(
            local_profile_id,
            "local_profile_id",
        )

        self._synthetic_student_id = self._identifier(
            synthetic_student_id,
            "synthetic_student_id",
        )

        # Take a validated snapshot rather than retaining a
        # caller-owned mutable reference.
        self._pack = CoursePackV01.model_validate(
            pack.model_dump(mode="json")
        )

        self._pack_sha256 = course_pack_digest_v01(
            self._pack
        )

        self._fetcher = CourseKnowledgeFetcherV01(
            InMemoryCoursePackStoreV01(
                (self._pack,)
            )
        )

        self._chat_store = chat_store
        self._gateway = gateway

    @staticmethod
    def _identifier(value: str, name: str) -> str:
        if (
            type(value) is not str
            or not value.strip()
            or len(value) > 128
        ):
            raise ValueError(
                f"{name} must contain 1–128 nonblank characters."
            )

        return value

    def _fetch_knowledge(
        self,
        objective_id: str,
    ) -> None:
        """
        Revalidate the exact Course Pack and Objective
        before opening a Session or invoking the model.
        """

        objective_id = self._identifier(
            objective_id,
            "objective_id",
        )

        fetched = self._fetcher.fetch(
            CourseKnowledgeFetchRequestV01(
                course_id=self._pack.course_id,
                objective_id=objective_id,
                pack_id=self._pack.pack_id,
                pack_revision=self._pack.pack_revision,
                expected_pack_sha256=self._pack_sha256,
            )
        )

        sources = fetched.knowledge.sources

        if not 1 <= len(sources) <= 8:
            raise ValueError(
                "Local Professor supports 1–8 source excerpts."
            )

        if any(
            len(source.content) > 8000
            for source in sources
        ):
            raise ValueError(
                "Course source exceeds the local Professor limit."
            )

    def _binding(
        self,
        *,
        session_id: str,
        objective_id: str,
    ) -> dict:

        return {
            "session_id": self._identifier(
                session_id,
                "session_id",
            ),
            "local_profile_id": self._local_profile_id,
            "course_id": self._pack.course_id,
            "objective_id": self._identifier(
                objective_id,
                "objective_id",
            ),
            "pack_id": self._pack.pack_id,
            "pack_revision": self._pack.pack_revision,
            "pack_sha256": self._pack_sha256,
        }

    def start_session(
        self,
        *,
        objective_id: str,
    ) -> str:
        """
        Create a new version-bound, developer-only Session.

        The Objective and source permissions are checked
        before the new Session is created.
        """

        self._fetch_knowledge(objective_id)

        return self._chat_store.create_session(
            local_profile_id=self._local_profile_id,
            course_id=self._pack.course_id,
            objective_id=objective_id,
            pack_id=self._pack.pack_id,
            pack_revision=self._pack.pack_revision,
            pack_sha256=self._pack_sha256,
        )

    def resume_session(
        self,
        *,
        session_id: str,
        objective_id: str,
    ) -> LocalChatSnapshotV01:
        """
        Recover one exact Session and its complete history.

        The caller must supply the same local profile,
        Course, Objective and pinned Course Pack snapshot.
        This logical check is not user authentication.
        """

        self._fetch_knowledge(objective_id)

        return self._chat_store.load_session(
            **self._binding(
                session_id=session_id,
                objective_id=objective_id,
            )
        )

    def send_explanation(
        self,
        *,
        session_id: str,
        objective_id: str,
        student_text: str,
        expected_message_count: int,
    ) -> LocalProfessorChatTurnV01:
        """
        Generate one course-grounded explanation and save it.

        A stale expected_message_count is rejected BEFORE
        model generation and is checked again by SQLite
        before committing the completed exchange.

        This is not a generation-reservation protocol.
        Only one caller should operate on a Session at a time.
        """

        if (
            type(expected_message_count) is not int
            or expected_message_count < 0
            or expected_message_count % 2
        ):
            raise ValueError(
                "Expected message count must be a "
                "nonnegative even integer."
            )

        # Scope, exact version and stored sequence must be
        # checked before any model call.
        snapshot = self.resume_session(
            session_id=session_id,
            objective_id=objective_id,
        )

        if len(snapshot.messages) != expected_message_count:
            raise ValueError(
                "Chat Session advanced since the caller "
                "loaded its history."
            )

        # This validates the incoming message and selects
        # recent complete exchanges from SQLite.
        chat_context = self._chat_store.conversation_context(
            snapshot,
            current_student_message=student_text,
        )

        scoped_gateway = ConversationScopedGatewayV01(
            gateway=self._gateway,
            chat_context=chat_context,
        )

        professor = StructuredProfessorAdapterV01(
            gateway=scoped_gateway,
        )

        harness = CourseGroundedTeachingHarnessV01(
            decision_engine=PersonalizedDecisionEngineV01(),
            professor_agent=professor,
        )

        # No Chat message is treated as assessment evidence.
        # An empty evidence set produces a synthetic local
        # pilot State, not a claim about the real learner.
        requested_at = datetime.now(timezone.utc)

        state = estimate_objective_state(
            [],
            student_id=self._synthetic_student_id,
            course_id=self._pack.course_id,
            objective_id=objective_id,
            as_of=requested_at,
        )

        teaching_result = harness.run_professor_turn(
            state,
            pack=self._pack,
            course_id=self._pack.course_id,
            objective_id=objective_id,
            expected_pack_revision=self._pack.pack_revision,
            decision_id=(
                "local-chat-decision-"
                + str(expected_message_count // 2)
                + "-"
                + session_id
            ),
            requested_at=requested_at,
            student_request=StudentLearningRequestV01(
                objective_id=objective_id,
                request_kind=(
                    StudentLearningRequestKindV01
                    .REQUEST_EXPLANATION
                ),
                requested_at=requested_at,
            ),
        )

        if (
            teaching_result.execution_status != "generated"
            or teaching_result.completed_turn.agent_kind
            != "professor"
        ):
            raise RuntimeError(
                "Local Chat requires a generated Professor turn."
            )

        professor_text = (
            teaching_result.completed_turn.content
        )

        # SQLite's current message contract permits at most
        # 1,500 characters. Never silently truncate a
        # generated explanation to make it fit.
        ConversationMessageV01(
            role="professor",
            text=professor_text,
        )

        # The two messages are committed as one transaction.
        # A failed append must not leave a half-completed turn.
        committed = self._chat_store.append_exchange(
            **self._binding(
                session_id=session_id,
                objective_id=objective_id,
            ),
            expected_message_count=expected_message_count,
            student_text=chat_context.current_student_message,
            professor_text=professor_text,
            answer_status=professor.answer_status,
        )

        return LocalProfessorChatTurnV01(
            teaching_result=teaching_result,
            snapshot=committed,
        )
