"""
URPP Implementation 14B-2B-1.

Reserve an idempotency key before executing one course-grounded
Professor turn. Recover the stored generated Trace on a retry.

A reserved turn without a durable generated Trace is NOT
automatically re-executed: the Professor may already have run.

This module does not implement:
- production schema migration or application authentication;
- presentation/delivery acknowledgement;
- exactly-once external LLM execution;
- assessment issuance or mastery-evidence creation.
"""

from datetime import datetime, timezone
from hashlib import sha256
import json

from sqlalchemy import (
    Column,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    insert,
    select,
    update,
)
from sqlalchemy.orm import sessionmaker

from app.domain.learning.state_v02 import ObjectiveStateV02

from app.repositories.course_teaching_trace_v01 import (
    CourseTeachingTraceRepositoryV01,
    StoredCourseTeachingTraceV01,
)

from app.services.course_knowledge.course_pack_v01 import (
    CoursePackV01,
    resolve_course_knowledge_v01,
)

from app.services.course_knowledge.teaching_harness_v01 import (
    CourseGroundedProfessorPortV01,
    CourseGroundedTeachingHarnessV01,
)

from app.services.decision.personalized_turn_orchestrator_v01 import (
    PersonalizedDecisionPortV01,
)

from app.services.decision.student_request_v01 import (
    StudentLearningRequestV01,
)


_intent_metadata_v01 = MetaData()

course_teaching_turn_intents_v01 = Table(
    "course_teaching_turn_intents_v01",
    _intent_metadata_v01,
    Column("trace_id", String(128), primary_key=True),
    Column("student_id", String(128), nullable=False),
    Column("course_id", String(128), nullable=False),
    Column("objective_id", String(128), nullable=False),
    Column("decision_id", String(128), nullable=False),
    Column("pack_id", String(128), nullable=False),
    Column("pack_revision", String(128), nullable=False),
    Column("request_fingerprint", String(64), nullable=False),
    Column("status", String(16), nullable=False),
    UniqueConstraint(
        "student_id",
        "course_id",
        "objective_id",
        "decision_id",
        name="course_turn_intent_decision_unique_v01",
    ),
)


class TeachingTurnRecoveryRequiredV01(RuntimeError):
    """
    A turn was reserved but has no recoverable generated Trace.

    The caller must not silently generate it again with the
    same request key. Manual reconciliation is a later feature.
    """


class DurableCourseTeachingTurnV01:
    """
    Internal, SQLite-backed wrapper around the existing Harness.

    It reserves a request before the Decision Engine or Professor
    is called. A repeated matching request recovers its stored
    result, or fails closed if generation outcome is unknown.
    """

    def __init__(
        self,
        *,
        session_factory: sessionmaker,
        decision_engine: PersonalizedDecisionPortV01,
        professor_agent: CourseGroundedProfessorPortV01,
    ) -> None:
        if not isinstance(session_factory, sessionmaker):
            raise TypeError(
                "session_factory must be a SQLAlchemy sessionmaker."
            )

        self._session_factory = session_factory
        self._traces = CourseTeachingTraceRepositoryV01(
            session_factory
        )
        self._harness = CourseGroundedTeachingHarnessV01(
            decision_engine=decision_engine,
            professor_agent=professor_agent,
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
    def _utc(value: datetime) -> str:
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValueError("Turn timestamps must be timezone-aware.")

        return value.astimezone(timezone.utc).isoformat()

    @classmethod
    def _fingerprint(
        cls,
        *,
        trace_id: str,
        student_id: str,
        course_id: str,
        objective_id: str,
        decision_id: str,
        requested_at: datetime,
        objective_state: ObjectiveStateV02,
        pack: CoursePackV01,
        student_request: StudentLearningRequestV01 | None,
    ) -> str:
        """
        Bind retries to the original request's serialized inputs.

        A fingerprint is for request consistency, not identity,
        authorization, or an assessment-evidence signature.
        """

        payload = {
            "contract": "durable-course-turn-request-v0.1",
            "trace_id": trace_id,
            "student_id": student_id,
            "course_id": course_id,
            "objective_id": objective_id,
            "decision_id": decision_id,
            "requested_at_utc": cls._utc(requested_at),
            "objective_state": objective_state.model_dump(mode="json"),
            "course_pack": pack.model_dump(mode="json"),
            "student_request": (
                None
                if student_request is None
                else student_request.model_dump(mode="json")
            ),
        }

        encoded = json.dumps(
            payload,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")

        return sha256(encoded).hexdigest()

    def _finish_reservation(self, trace_id: str) -> None:
        """Mark an existing reservation completed after Trace recovery."""

        with self._session_factory() as session:
            with session.begin():
                row = session.execute(
                    select(
                        course_teaching_turn_intents_v01.c.status
                    ).where(
                        course_teaching_turn_intents_v01.c.trace_id
                        == trace_id
                    )
                ).scalar_one()

                if row == "completed":
                    return

                if row != "reserved":
                    raise RuntimeError(
                        "Teaching turn reservation has an invalid status."
                    )

                session.execute(
                    update(course_teaching_turn_intents_v01)
                    .where(
                        course_teaching_turn_intents_v01.c.trace_id
                        == trace_id
                    )
                    .values(status="completed")
                )

    def run_or_resume(
        self,
        objective_state: ObjectiveStateV02,
        *,
        pack: CoursePackV01,
        trace_id: str,
        student_id: str,
        course_id: str,
        objective_id: str,
        expected_pack_revision: str,
        decision_id: str,
        requested_at: datetime,
        generated_at: datetime,
        student_request: StudentLearningRequestV01 | None = None,
    ) -> StoredCourseTeachingTraceV01:
        """
        Execute a new request once, or recover a committed Trace.

        A duplicate reservation with no Trace is an ambiguous
        outcome and is never automatically regenerated.
        """

        for name, value in (
            ("trace_id", trace_id),
            ("student_id", student_id),
            ("course_id", course_id),
            ("objective_id", objective_id),
            ("decision_id", decision_id),
        ):
            self._identifier(value, name)

        self._utc(requested_at)
        self._utc(generated_at)

        if (
            objective_state.student_id != student_id
            or objective_state.course_id != course_id
            or objective_state.objective_id != objective_id
        ):
            raise ValueError("Student State identity or scope mismatch.")

        if (
            student_request is not None
            and student_request.objective_id != objective_id
        ):
            raise ValueError("Student request objective scope mismatch.")

        # Revalidate the serialized Pack, including all source
        # digests, before accepting either a first call or retry.
        validated_pack = CoursePackV01.model_validate(
            pack.model_dump(mode="json")
        )

        resolve_course_knowledge_v01(
            pack=validated_pack,
            course_id=course_id,
            objective_id=objective_id,
            expected_pack_revision=expected_pack_revision,
        )

        fingerprint = self._fingerprint(
            trace_id=trace_id,
            student_id=student_id,
            course_id=course_id,
            objective_id=objective_id,
            decision_id=decision_id,
            requested_at=requested_at,
            objective_state=objective_state,
            pack=validated_pack,
            student_request=student_request,
        )

        expected = {
            "trace_id": trace_id,
            "student_id": student_id,
            "course_id": course_id,
            "objective_id": objective_id,
            "decision_id": decision_id,
            "pack_id": validated_pack.pack_id,
            "pack_revision": validated_pack.pack_revision,
            "request_fingerprint": fingerprint,
        }

        # The INSERT reservation is committed BEFORE any Agent
        # call. The database's uniqueness constraints arbitrate
        # repeated requests, including overlapping processes.
        with self._session_factory() as session:
            with session.begin():
                insertion = session.execute(
                    insert(course_teaching_turn_intents_v01)
                    .prefix_with("OR IGNORE")
                    .values(**expected, status="reserved")
                )
                claimed = insertion.rowcount == 1

                existing = session.execute(
                    select(course_teaching_turn_intents_v01)
                    .where(
                        course_teaching_turn_intents_v01.c.trace_id
                        == trace_id
                    )
                ).mappings().one_or_none()

                if existing is None:
                    raise ValueError(
                        "Teaching decision is already reserved "
                        "under another Trace ID."
                    )

                if any(
                    existing[name] != value
                    for name, value in expected.items()
                ):
                    raise ValueError(
                        "Teaching retry does not match the "
                        "original reserved request."
                    )

        if not claimed:
            try:
                recovered = self._traces.load(
                    trace_id=trace_id,
                    student_id=student_id,
                    course_id=course_id,
                    objective_id=objective_id,
                )
            except LookupError as exc:
                raise TeachingTurnRecoveryRequiredV01(
                    "Teaching turn was reserved but has no "
                    "durable generated Trace. Do not regenerate "
                    "automatically; its outcome is unknown."
                ) from exc

            if (
                recovered.decision_id != decision_id
                or recovered.result.pack_id
                != validated_pack.pack_id
                or recovered.result.pack_revision
                != validated_pack.pack_revision
            ):
                raise ValueError(
                    "Recovered Teaching Trace does not match "
                    "the reserved request."
                )

            self._finish_reservation(trace_id)
            return recovered

        # Only the process that successfully inserted a NEW
        # reservation is allowed to call the Professor.
        result = self._harness.run_professor_turn(
            objective_state,
            pack=validated_pack,
            course_id=course_id,
            objective_id=objective_id,
            expected_pack_revision=expected_pack_revision,
            decision_id=decision_id,
            requested_at=requested_at,
            student_request=student_request,
        )

        stored = self._traces.save_generated(
            result,
            trace_id=trace_id,
            student_id=student_id,
            generated_at=generated_at,
        )

        self._finish_reservation(trace_id)

        return stored
