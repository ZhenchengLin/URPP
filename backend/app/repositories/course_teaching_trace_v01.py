"""
URPP Implementation 14B-2A.

Durable storage for generated course-grounded Professor turns.

Uses an externally supplied SQLAlchemy sessionmaker.
It does not create an Engine, database, or production schema.

A generated Trace:
- records the result of an already completed Professor call;
- can be recovered using its trace ID and expected scope;
- is not proof of presentation, reading, learning, or mastery;
- does not update Student State or Assessment Evidence.

The caller supplies student identity and is responsible for
authentication and authorization. Scope checks here do not
authenticate the caller.

Exactly-once generation, crash-safe retries of the entire
teaching turn, delivery acknowledgement, and production schema
migration are outside 14B-2A.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from pydantic import ValidationError

from sqlalchemy import (
    JSON,
    Column,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    insert,
    select,
)

from sqlalchemy.orm import sessionmaker

from app.services.course_knowledge.models_v01 import (
    CourseKnowledgeContextV01,
    CourseSourceRefV01,
)

from app.services.course_knowledge.teaching_harness_v01 import (
    CourseGroundedTeachingResultV01,
)

from app.services.decision.personalized_turn_orchestrator_v01 import (
    PersonalizedTeachingTurnResultV01,
)

from app.services.decision.turn_orchestrator_v01 import (
    PROFESSOR_ACTIONS,
)


# This metadata is intentionally separate from the existing
# Numeric Base.metadata. Importing this module must not
# silently add a new table to Numeric test initialization
# or alter the Numeric schema-readiness contract.
_teaching_trace_metadata_v01 = MetaData()


course_teaching_traces_v01 = Table(
    "course_teaching_traces_v01",
    _teaching_trace_metadata_v01,

    Column(
        "trace_id",
        String(128),
        primary_key=True,
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
        "decision_id",
        String(128),
        nullable=False,
    ),
    Column(
        "pack_id",
        String(128),
        nullable=False,
    ),
    Column(
        "pack_revision",
        String(128),
        nullable=False,
    ),
    Column(
        "generated_at_utc",
        String(48),
        nullable=False,
    ),
    Column(
        "payload",
        JSON,
        nullable=False,
    ),

    UniqueConstraint(
        "student_id",
        "course_id",
        "objective_id",
        "decision_id",
        name="course_teaching_trace_decision_unique_v01",
    ),
)


@dataclass(frozen=True)
class StoredCourseTeachingTraceV01:
    """
    One recovered generated Professor turn.

    The result contains the original decision, generated
    content, validated course context, and Source References.

    generated_at is a storage timestamp, not a delivery time.
    """

    trace_id: str
    student_id: str
    course_id: str
    objective_id: str
    decision_id: str
    generated_at: datetime

    result: CourseGroundedTeachingResultV01

    execution_status: str = "generated"


class CourseTeachingTraceRepositoryV01:
    """
    Store and retrieve course-grounded teaching results.

    The owner of session_factory also owns its Engine,
    connection policy, database provisioning, and disposal.

    This repository never creates its table automatically.
    """

    def __init__(
        self,
        session_factory: sessionmaker,
    ) -> None:
        if not isinstance(
            session_factory,
            sessionmaker,
        ):
            raise TypeError(
                "session_factory must be a SQLAlchemy sessionmaker."
            )

        self._session_factory = session_factory

    @staticmethod
    def _identifier(
        value: str,
        name: str,
    ) -> str:
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
    def _aware_utc(
        value: datetime,
    ) -> datetime:
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValueError(
                "generated_at must be timezone-aware."
            )

        return value.astimezone(timezone.utc)

    @staticmethod
    def _validate_result(
        result: CourseGroundedTeachingResultV01,
    ) -> CourseGroundedTeachingResultV01:
        """
        Revalidate both Pydantic models before storing.

        This also detects invalid changes introduced through
        model_copy(update=...), which can bypass validators.
        """

        if not isinstance(
            result,
            CourseGroundedTeachingResultV01,
        ):
            raise TypeError(
                "result must be a CourseGroundedTeachingResultV01."
            )

        completed = (
            PersonalizedTeachingTurnResultV01.model_validate(
                result.completed_turn.model_dump(mode="json")
            )
        )

        knowledge = (
            CourseKnowledgeContextV01.model_validate(
                result.course_knowledge.model_dump(mode="json")
            )
        )

        if result.execution_status != "generated":
            raise ValueError(
                "Only generated Professor results can be stored."
            )

        if (
            completed.agent_kind != "professor"
            or completed.decision.decision.selected_action
            not in PROFESSOR_ACTIONS
        ):
            raise ValueError(
                "Teaching Trace requires a Professor action."
            )

        if (
            result.source_refs
            != knowledge.objective.source_refs
        ):
            raise ValueError(
                "Teaching Trace source references do not "
                "match the validated Course Knowledge Context."
            )

        for name, value in (
            ("pack_id", result.pack_id),
            ("pack_revision", result.pack_revision),
        ):
            CourseTeachingTraceRepositoryV01._identifier(
                value,
                name,
            )

        return CourseGroundedTeachingResultV01(
            completed_turn=completed,
            course_knowledge=knowledge,
            pack_id=result.pack_id,
            pack_revision=result.pack_revision,
            source_refs=knowledge.objective.source_refs,
        )

    @staticmethod
    def _payload(
        result: CourseGroundedTeachingResultV01,
    ) -> dict:
        return {
            "completed_turn": (
                result.completed_turn.model_dump(
                    mode="json"
                )
            ),
            "course_knowledge": (
                result.course_knowledge.model_dump(
                    mode="json"
                )
            ),
            "pack_id": result.pack_id,
            "pack_revision": result.pack_revision,
            "source_refs": [
                reference.model_dump(mode="json")
                for reference in result.source_refs
            ],
            "execution_status": "generated",
        }

    @classmethod
    def _decode(
        cls,
        row,
    ) -> StoredCourseTeachingTraceV01:
        """
        Reconstruct and validate the stored payload.

        Do not silently trust JSON or duplicate scope fields
        merely because they came from a database row.
        """

        payload = row["payload"]

        if not isinstance(payload, dict):
            raise ValueError(
                "Stored Teaching Trace payload is invalid."
            )

        completed = (
            PersonalizedTeachingTurnResultV01.model_validate(
                payload["completed_turn"]
            )
        )

        knowledge = (
            CourseKnowledgeContextV01.model_validate(
                payload["course_knowledge"]
            )
        )

        source_refs = tuple(
            CourseSourceRefV01.model_validate(value)
            for value in payload["source_refs"]
        )

        result = cls._validate_result(
            CourseGroundedTeachingResultV01(
                completed_turn=completed,
                course_knowledge=knowledge,
                pack_id=payload["pack_id"],
                pack_revision=payload["pack_revision"],
                source_refs=source_refs,
                execution_status=payload["execution_status"],
            )
        )

        decision_id = (
            result.completed_turn.decision.decision.decision_id
        )

        if (
            row["course_id"] != result.course_knowledge.course_id
            or row["objective_id"]
            != result.course_knowledge.objective_id
            or row["decision_id"] != decision_id
            or row["pack_id"] != result.pack_id
            or row["pack_revision"] != result.pack_revision
        ):
            raise ValueError(
                "Stored Teaching Trace metadata "
                "does not match its validated payload."
            )

        generated_at = datetime.fromisoformat(
            row["generated_at_utc"]
        )

        cls._aware_utc(generated_at)

        return StoredCourseTeachingTraceV01(
            trace_id=row["trace_id"],
            student_id=row["student_id"],
            course_id=row["course_id"],
            objective_id=row["objective_id"],
            decision_id=row["decision_id"],
            generated_at=generated_at,
            result=result,
        )

    def save_generated(
        self,
        result: CourseGroundedTeachingResultV01,
        *,
        trace_id: str,
        student_id: str,
        generated_at: datetime,
    ) -> StoredCourseTeachingTraceV01:
        """
        Insert one completed generated turn.

        A repeated trace ID or repeated decision within the
        same student/course/objective scope is rejected.

        This prevents overwriting stored content. It does NOT
        prevent an Agent from being called twice before save;
        safe whole-turn retry belongs to 14B-2B.
        """

        self._identifier(trace_id, "trace_id")
        self._identifier(student_id, "student_id")

        generated_at_utc = self._aware_utc(
            generated_at
        ).isoformat()

        validated = self._validate_result(result)

        knowledge = validated.course_knowledge

        decision_id = (
            validated.completed_turn.decision.decision.decision_id
        )

        self._identifier(
            knowledge.course_id,
            "course_id",
        )
        self._identifier(
            knowledge.objective_id,
            "objective_id",
        )
        self._identifier(
            decision_id,
            "decision_id",
        )

        with self._session_factory() as session:
            with session.begin():
                existing_trace = session.execute(
                    select(
                        course_teaching_traces_v01.c.trace_id
                    ).where(
                        course_teaching_traces_v01.c.trace_id
                        == trace_id
                    )
                ).first()

                if existing_trace is not None:
                    raise ValueError(
                        "Teaching Trace ID already exists."
                    )

                existing_decision = session.execute(
                    select(
                        course_teaching_traces_v01.c.trace_id
                    ).where(
                        course_teaching_traces_v01.c.student_id
                        == student_id,
                        course_teaching_traces_v01.c.course_id
                        == knowledge.course_id,
                        course_teaching_traces_v01.c.objective_id
                        == knowledge.objective_id,
                        course_teaching_traces_v01.c.decision_id
                        == decision_id,
                    )
                ).first()

                if existing_decision is not None:
                    raise ValueError(
                        "Teaching Trace decision already exists "
                        "for this student/course/objective."
                    )

                session.execute(
                    insert(course_teaching_traces_v01).values(
                        trace_id=trace_id,
                        student_id=student_id,
                        course_id=knowledge.course_id,
                        objective_id=knowledge.objective_id,
                        decision_id=decision_id,
                        pack_id=validated.pack_id,
                        pack_revision=validated.pack_revision,
                        generated_at_utc=generated_at_utc,
                        payload=self._payload(validated),
                    )
                )

        # Read back from the durable record, rather than
        # returning an unverified in-memory copy.
        return self.load(
            trace_id=trace_id,
            student_id=student_id,
            course_id=knowledge.course_id,
            objective_id=knowledge.objective_id,
        )

    def load(
        self,
        *,
        trace_id: str,
        student_id: str,
        course_id: str,
        objective_id: str,
    ) -> StoredCourseTeachingTraceV01:
        """
        Load one Trace under an explicit expected scope.

        Matching IDs are not proof of caller authorization.
        A trusted application layer must authenticate access.
        """

        for name, value in (
            ("trace_id", trace_id),
            ("student_id", student_id),
            ("course_id", course_id),
            ("objective_id", objective_id),
        ):
            self._identifier(value, name)

        with self._session_factory() as session:
            row = session.execute(
                select(
                    course_teaching_traces_v01
                ).where(
                    course_teaching_traces_v01.c.trace_id
                    == trace_id
                )
            ).mappings().one_or_none()

        if row is None:
            raise LookupError(
                "Teaching Trace was not found."
            )

        if (
            row["student_id"] != student_id
            or row["course_id"] != course_id
            or row["objective_id"] != objective_id
        ):
            raise ValueError(
                "Teaching Trace scope mismatch."
            )

        return self._decode(row)
