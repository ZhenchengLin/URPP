"""
URPP Implementation 14B-3-2C-1.

Durable, non-assessment teaching feedback for an immutable
student learning response.

Execution order:
    load original response
    -> commit feedback reservation
    -> call feedback agent
    -> commit generated feedback

An existing completed feedback is recovered without calling
the Agent again. An incomplete reservation blocks automatic
regeneration because the original Agent outcome is unknown.

This module does not:
- modify the original student response or Teaching Trace;
- grade an answer or produce Mastery Evidence;
- update Student State;
- authenticate callers;
- create a database, Engine, or production schema;
- guarantee exactly-once execution of an external model.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Protocol

from sqlalchemy import (
    Column,
    ForeignKey,
    String,
    Table,
    select,
    update,
)
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import sessionmaker

from app.repositories.course_learning_response_v01 import (
    CourseLearningResponseRepositoryV01,
    StoredCourseLearningResponseV01,
    course_learning_responses_v01,
)


course_learning_feedback_v01 = Table(
    "course_learning_feedback_v01",
    course_learning_responses_v01.metadata,

    Column(
        "response_id",
        String(128),
        ForeignKey(
            "course_learning_responses_v01.response_id",
            ondelete="RESTRICT",
        ),
        primary_key=True,
    ),
    Column(
        "feedback_id",
        String(128),
        nullable=False,
        unique=True,
    ),
    Column(
        "trace_id",
        String(128),
        nullable=False,
    ),
    Column(
        "student_id",
        String(128),
        nullable=False,
    ),
    Column(
        "course_id",
        String(128),
        nullable=False,
    ),
    Column(
        "objective_id",
        String(128),
        nullable=False,
    ),
    Column(
        "activity_id",
        String(128),
        nullable=False,
    ),
    Column(
        "feedback_version",
        String(128),
        nullable=False,
    ),
    Column(
        "input_sha256",
        String(64),
        nullable=False,
    ),
    Column(
        "status",
        String(16),
        nullable=False,
    ),
    Column(
        "reserved_at_utc",
        String(48),
        nullable=False,
    ),
    Column(
        "generated_at_utc",
        String(48),
        nullable=True,
    ),
    Column(
        "feedback_text",
        String(4000),
        nullable=True,
    ),
    Column(
        "feedback_sha256",
        String(64),
        nullable=True,
    ),
)


class FeedbackRecoveryRequiredV01(RuntimeError):
    """
    A feedback request was reserved, but no completed feedback
    is available. Do not automatically call the Agent again.
    """


class LearningFeedbackAgentPortV01(Protocol):
    """
    Agent receives the stored original response.

    Its output is teaching feedback, not an assessment result.
    """

    def produce(
        self,
        *,
        response: StoredCourseLearningResponseV01,
    ) -> str:
        ...


@dataclass(frozen=True)
class StoredLearningFeedbackV01:
    feedback_id: str
    response_id: str
    trace_id: str

    student_id: str
    course_id: str
    objective_id: str
    activity_id: str

    feedback_version: str
    feedback_text: str

    reserved_at: datetime
    generated_at: datetime

    status: str = "generated_feedback"


class DurableLearningFeedbackV01:
    """
    Persist a reservation before invoking the feedback Agent.

    The repository's existing response and presentation checks
    remain the source of truth for submitted student input.
    """

    def __init__(
        self,
        *,
        session_factory: sessionmaker,
        feedback_agent: LearningFeedbackAgentPortV01,
    ) -> None:
        if not isinstance(session_factory, sessionmaker):
            raise TypeError(
                "session_factory must be a SQLAlchemy sessionmaker."
            )

        self._session_factory = session_factory
        self._feedback_agent = feedback_agent

        self._responses = CourseLearningResponseRepositoryV01(
            session_factory
        )

    @staticmethod
    def _identifier(value: str, name: str) -> str:
        if (
            not isinstance(value, str)
            or not value.strip()
            or len(value) > 128
        ):
            raise ValueError(
                f"{name} must be a non-empty string "
                "of at most 128 characters."
            )

        return value

    @staticmethod
    def _utc(value: datetime, name: str) -> datetime:
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValueError(
                f"{name} must be timezone-aware."
            )

        return value.astimezone(timezone.utc)

    @staticmethod
    def _digest(value: str) -> str:
        return sha256(
            value.encode("utf-8")
        ).hexdigest()

    @classmethod
    def _input_digest(
        cls,
        response: StoredCourseLearningResponseV01,
        feedback_version: str,
    ) -> str:
        """
        Bind a feedback request to the immutable input,
        activity prompt, scope, and feedback policy version.
        """

        payload = {
            "contract": "course-learning-feedback-v0.1",
            "response_id": response.response_id,
            "trace_id": response.trace_id,
            "presentation_event_id": (
                response.presentation_event_id
            ),
            "student_id": response.student_id,
            "course_id": response.course_id,
            "objective_id": response.objective_id,
            "activity_id": response.activity_id,
            "activity_prompt": response.activity_prompt,
            "response_text": response.response_text,
            "submitted_at_utc": cls._utc(
                response.submitted_at,
                "submitted_at",
            ).isoformat(),
            "feedback_version": feedback_version,
        }

        encoded = json.dumps(
            payload,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")

        return sha256(encoded).hexdigest()

    def _load_response(
        self,
        *,
        response_id: str,
        trace_id: str,
        student_id: str,
        course_id: str,
        objective_id: str,
    ) -> StoredCourseLearningResponseV01:
        """
        The existing Repository verifies the original response
        against its Teaching Trace and Presentation Event.
        """

        return self._responses.load(
            response_id=response_id,
            trace_id=trace_id,
            student_id=student_id,
            course_id=course_id,
            objective_id=objective_id,
        )

    def _decode(
        self,
        row,
        response: StoredCourseLearningResponseV01,
        *,
        feedback_id: str,
        feedback_version: str,
    ) -> StoredLearningFeedbackV01:
        expected = {
            "response_id": response.response_id,
            "feedback_id": feedback_id,
            "trace_id": response.trace_id,
            "student_id": response.student_id,
            "course_id": response.course_id,
            "objective_id": response.objective_id,
            "activity_id": response.activity_id,
            "feedback_version": feedback_version,
            "input_sha256": self._input_digest(
                response,
                feedback_version,
            ),
        }

        if any(
            row[key] != value
            for key, value in expected.items()
        ):
            raise ValueError(
                "Feedback record does not match the "
                "original response and reserved request."
            )

        status = row["status"]

        if status == "reserved":
            raise FeedbackRecoveryRequiredV01(
                "Feedback generation has an incomplete "
                "reservation. Do not regenerate automatically."
            )

        if status != "completed":
            raise ValueError(
                "Stored feedback has an invalid status."
            )

        feedback_text = row["feedback_text"]
        generated_text = row["generated_at_utc"]

        if (
            not isinstance(feedback_text, str)
            or not feedback_text.strip()
            or len(feedback_text) > 4000
            or not isinstance(generated_text, str)
        ):
            raise ValueError(
                "Completed feedback has an invalid payload."
            )

        if (
            row["feedback_sha256"]
            != self._digest(feedback_text)
        ):
            raise ValueError(
                "Stored feedback content digest mismatch."
            )

        reserved_at = self._utc(
            datetime.fromisoformat(
                row["reserved_at_utc"]
            ),
            "reserved_at",
        )

        generated_at = self._utc(
            datetime.fromisoformat(generated_text),
            "generated_at",
        )

        if generated_at < reserved_at:
            raise ValueError(
                "Feedback generation precedes reservation."
            )

        return StoredLearningFeedbackV01(
            feedback_id=row["feedback_id"],
            response_id=row["response_id"],
            trace_id=row["trace_id"],
            student_id=row["student_id"],
            course_id=row["course_id"],
            objective_id=row["objective_id"],
            activity_id=row["activity_id"],
            feedback_version=row["feedback_version"],
            feedback_text=feedback_text,
            reserved_at=reserved_at,
            generated_at=generated_at,
        )

    def _find_row(self, response_id: str):
        with self._session_factory() as session:
            return session.execute(
                select(course_learning_feedback_v01)
                .where(
                    course_learning_feedback_v01.c.response_id
                    == response_id
                )
            ).mappings().one_or_none()

    def load(
        self,
        *,
        feedback_id: str,
        response_id: str,
        trace_id: str,
        student_id: str,
        course_id: str,
        objective_id: str,
        feedback_version: str,
    ) -> StoredLearningFeedbackV01:
        """
        Recover completed feedback without invoking the Agent.

        An incomplete reservation raises
        FeedbackRecoveryRequiredV01.
        """

        for name, value in (
            ("feedback_id", feedback_id),
            ("response_id", response_id),
            ("trace_id", trace_id),
            ("student_id", student_id),
            ("course_id", course_id),
            ("objective_id", objective_id),
            ("feedback_version", feedback_version),
        ):
            self._identifier(value, name)

        response = self._load_response(
            response_id=response_id,
            trace_id=trace_id,
            student_id=student_id,
            course_id=course_id,
            objective_id=objective_id,
        )

        row = self._find_row(response_id)

        if row is None:
            raise LookupError(
                "Learning feedback was not found."
            )

        return self._decode(
            row,
            response,
            feedback_id=feedback_id,
            feedback_version=feedback_version,
        )

    def _complete(
        self,
        *,
        response_id: str,
        input_sha256: str,
        feedback_text: str,
        generated_at: datetime,
    ) -> None:
        """
        Store generated feedback before returning to the caller.

        A failed database commit leaves an unresolved reservation.
        A successful commit can be recovered on the next request.
        """

        with self._session_factory() as session:
            with session.begin():
                updated = session.execute(
                    update(course_learning_feedback_v01)
                    .where(
                        course_learning_feedback_v01.c.response_id
                        == response_id,
                        course_learning_feedback_v01.c.input_sha256
                        == input_sha256,
                        course_learning_feedback_v01.c.status
                        == "reserved",
                    )
                    .values(
                        status="completed",
                        feedback_text=feedback_text,
                        feedback_sha256=self._digest(
                            feedback_text
                        ),
                        generated_at_utc=(
                            generated_at.isoformat()
                        ),
                    )
                )

                if updated.rowcount != 1:
                    raise RuntimeError(
                        "Feedback reservation changed before "
                        "its generated content was saved."
                    )

    def run_or_resume(
        self,
        *,
        feedback_id: str,
        response_id: str,
        trace_id: str,
        student_id: str,
        course_id: str,
        objective_id: str,
        feedback_version: str,
        requested_at: datetime,
    ) -> StoredLearningFeedbackV01:
        """
        Reserve once, then generate or recover durable feedback.

        requested_at timestamps the reservation attempt.
        Repeated requests may have a later requested_at, but
        must retain the same IDs, input, and feedback version.
        """

        for name, value in (
            ("feedback_id", feedback_id),
            ("response_id", response_id),
            ("trace_id", trace_id),
            ("student_id", student_id),
            ("course_id", course_id),
            ("objective_id", objective_id),
            ("feedback_version", feedback_version),
        ):
            self._identifier(value, name)

        reserved_at = self._utc(
            requested_at,
            "requested_at",
        )

        response = self._load_response(
            response_id=response_id,
            trace_id=trace_id,
            student_id=student_id,
            course_id=course_id,
            objective_id=objective_id,
        )

        if reserved_at < response.submitted_at.astimezone(
            timezone.utc
        ):
            raise ValueError(
                "Feedback request precedes the student submission."
            )

        input_sha256 = self._input_digest(
            response,
            feedback_version,
        )

        expected = {
            "response_id": response_id,
            "feedback_id": feedback_id,
            "trace_id": trace_id,
            "student_id": student_id,
            "course_id": course_id,
            "objective_id": objective_id,
            "activity_id": response.activity_id,
            "feedback_version": feedback_version,
            "input_sha256": input_sha256,
        }

        # Commit the unique request reservation BEFORE calling
        # the feedback Agent. SQLite arbitrates duplicate keys.
        with self._session_factory() as session:
            with session.begin():
                insertion = session.execute(
                    sqlite_insert(
                        course_learning_feedback_v01
                    )
                    .values(
                        **expected,
                        status="reserved",
                        reserved_at_utc=reserved_at.isoformat(),
                    )
                    .on_conflict_do_nothing()
                )

                claimed = insertion.rowcount == 1

                row = session.execute(
                    select(course_learning_feedback_v01)
                    .where(
                        course_learning_feedback_v01.c.response_id
                        == response_id
                    )
                ).mappings().one_or_none()

                if row is None:
                    raise ValueError(
                        "Feedback ID is already reserved "
                        "for another student response."
                    )

                if any(
                    row[key] != value
                    for key, value in expected.items()
                ):
                    raise ValueError(
                        "Feedback retry does not match "
                        "the original reserved request."
                    )

        if not claimed:
            return self.load(
                feedback_id=feedback_id,
                response_id=response_id,
                trace_id=trace_id,
                student_id=student_id,
                course_id=course_id,
                objective_id=objective_id,
                feedback_version=feedback_version,
            )

        # Only the caller that inserted a new reservation
        # may invoke the Agent.
        feedback_text = self._feedback_agent.produce(
            response=response
        )

        if (
            not isinstance(feedback_text, str)
            or not feedback_text.strip()
            or len(feedback_text) > 4000
        ):
            raise ValueError(
                "Feedback Agent must return non-empty "
                "text of at most 4000 characters."
            )

        generated_at = datetime.now(timezone.utc)

        if generated_at < reserved_at:
            raise ValueError(
                "Feedback generation precedes reservation."
            )

        self._complete(
            response_id=response_id,
            input_sha256=input_sha256,
            feedback_text=feedback_text,
            generated_at=generated_at,
        )

        return self.load(
            feedback_id=feedback_id,
            response_id=response_id,
            trace_id=trace_id,
            student_id=student_id,
            course_id=course_id,
            objective_id=objective_id,
            feedback_version=feedback_version,
        )
