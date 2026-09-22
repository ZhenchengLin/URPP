"""
URPP Implementation 14B-3-1: integrated local teaching demo.

SYNTHETIC COURSE MATERIAL ONLY.

Run from backend/:
    python3 scripts/course_teaching_demo_v01.py init --database PATH
    python3 scripts/course_teaching_demo_v01.py teach --database PATH
    python3 scripts/course_teaching_demo_v01.py present --database PATH
    python3 scripts/course_teaching_demo_v01.py status --database PATH

The database filename must be urpp-course-teaching-demo.sqlite.

This script does not use or migrate URPP's production database,
authenticate students, issue assessments, or create mastery evidence.

A presentation event records this CLI's report of display. It
cannot establish that a student actually read or understood text.
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker


# Permit execution as a script from the backend directory.
BACKEND = Path(__file__).resolve().parents[1]

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


from app.domain.learning.models import ObjectiveStateLabel

from app.repositories.course_teaching_presentation_v01 import (
    CourseTeachingPresentationRepositoryV01,
    course_teaching_presentations_v01,
)

from app.repositories.course_teaching_trace_v01 import (
    course_teaching_traces_v01,
)

from app.services.course_knowledge.course_pack_v01 import (
    CoursePackV01,
)

from app.services.course_knowledge.durable_teaching_turn_v01 import (
    DurableCourseTeachingTurnV01,
    course_teaching_turn_intents_v01,
)

from app.services.course_knowledge.models_v01 import (
    CourseLearningObjectiveV01,
    CourseSourceV01,
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


DEMO_MARKER = "urpp-course-teaching-demo-v0.1"
DEMO_FILENAME = "urpp-course-teaching-demo.sqlite"

STUDENT_ID = "synthetic-student-001"
COURSE_ID = "synthetic-course-001"
OBJECTIVE_ID = "synthetic-objective-001"

PACK_ID = "synthetic-pack-001"
PACK_REVISION = "synthetic-pack-revision-001"

TRACE_ID = "synthetic-trace-001"
DECISION_ID = "synthetic-decision-001"
PRESENTATION_ID = "synthetic-presentation-001"

REQUESTED_AT = datetime(
    2026,
    9,
    22,
    tzinfo=timezone.utc,
)


def emit(**values):
    print(
        json.dumps(
            values,
            ensure_ascii=False,
            sort_keys=True,
        ),
        flush=True,
    )


def validate_path(value):
    path = Path(value).expanduser().absolute()

    if path.name != DEMO_FILENAME:
        raise ValueError(
            "Demo database filename must be "
            f"{DEMO_FILENAME}."
        )

    if path.is_symlink():
        raise ValueError(
            "Refusing a symbolic-link demo database."
        )

    if not path.parent.is_dir():
        raise ValueError(
            "Demo database parent directory does not exist."
        )

    return path


def attach_foreign_key_policy(engine):
    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

        actual = connection.execute(
            "PRAGMA foreign_keys"
        ).fetchone()

        if actual is None or actual[0] != 1:
            raise RuntimeError(
                "SQLite foreign-key enforcement is required."
            )

    return engine


def initialize_database(path):
    """
    Explicitly create a NEW demo-only database.

    Refuse existing files. Never run create_all() against an
    existing URPP database or its Numeric Base.metadata.
    """

    if path.exists():
        raise ValueError(
            "Demo database already exists. "
            "Use teach, present, or status."
        )

    engine = attach_foreign_key_policy(
        create_engine(
            f"sqlite+pysqlite:///{path}"
        )
    )

    try:
        course_teaching_traces_v01.create(
            engine,
            checkfirst=False,
        )

        course_teaching_turn_intents_v01.create(
            engine,
            checkfirst=False,
        )

        course_teaching_presentations_v01.create(
            engine,
            checkfirst=False,
        )

        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE urpp_demo_identity_v01 "
                "(identity TEXT NOT NULL)"
            )

            connection.execute(
                text(
                    "INSERT INTO urpp_demo_identity_v01 "
                    "(identity) VALUES (:identity)"
                ),
                {"identity": DEMO_MARKER},
            )

    finally:
        engine.dispose()

    emit(
        status="initialized",
        database=str(path),
        course_type="synthetic_demo_only",
    )


def open_verified_demo(path):
    """
    Open an existing SQLite file without silently creating it.

    Refuse files without the expected demo identity marker.
    """

    if not path.is_file():
        raise ValueError(
            "Demo database does not exist. Run init first."
        )

    database_uri = path.as_uri() + "?mode=rw"

    def open_existing():
        return sqlite3.connect(
            database_uri,
            uri=True,
            timeout=5.0,
        )

    engine = attach_foreign_key_policy(
        create_engine(
            "sqlite+pysqlite://",
            creator=open_existing,
        )
    )

    try:
        with engine.connect() as connection:
            marker = connection.execute(
                text(
                    "SELECT identity "
                    "FROM urpp_demo_identity_v01"
                )
            ).scalar_one()

            if marker != DEMO_MARKER:
                raise ValueError(
                    "Database is not a verified URPP demo."
                )

    except Exception:
        engine.dispose()
        raise

    return engine


def make_pack():
    content = (
        "SYNTHETIC DEMO MATERIAL: "
        "A matrix can be represented by a decomposition. "
        "This is a test fixture, not an approved course excerpt."
    )

    source = CourseSourceV01(
        course_id=COURSE_ID,
        source_id="synthetic-source-001",
        source_revision="synthetic-source-revision-001",
        source_locator="synthetic-fixture:section-1",
        content=content,
        content_sha256=sha256(
            content.encode("utf-8")
        ).hexdigest(),
        visibility="student_visible",
        use_permission="approved_for_local_teaching",
        review_status="approved",
    )

    objective = CourseLearningObjectiveV01(
        course_id=COURSE_ID,
        objective_id=OBJECTIVE_ID,
        description=(
            "Explain the synthetic decomposition fixture."
        ),
        review_status="approved",
        source_refs=(source.reference(),),
    )

    return CoursePackV01(
        course_id=COURSE_ID,
        pack_id=PACK_ID,
        pack_revision=PACK_REVISION,
        objectives=(objective,),
        sources=(source,),
    )


def make_state():
    state = estimate_objective_state(
        [],
        student_id=STUDENT_ID,
        course_id=COURSE_ID,
        objective_id=OBJECTIVE_ID,
        as_of=REQUESTED_AT,
    )

    # Synthetic routing fixture ONLY.
    # This is not assessment-backed student mastery.
    return state.model_copy(
        update={"state": ObjectiveStateLabel.STRONG}
    )


def make_request():
    return StudentLearningRequestV01(
        objective_id=OBJECTIVE_ID,
        request_kind=(
            StudentLearningRequestKindV01.REQUEST_EXPLANATION
        ),
        requested_at=REQUESTED_AT,
    )


class FakeCourseProfessor:
    def produce(
        self,
        *,
        context,
        decision,
        course_knowledge,
    ):
        source = course_knowledge.sources[0]

        return (
            "SYNTHETIC DEMO — Fake Professor\n"
            f"Source: {source.source_locator}\n"
            f"Objective: {course_knowledge.objective.description}\n"
            "This is an example explanation, not verified "
            "instruction from a real course.\n"
            f"Generation token: {uuid4().hex}"
        )


def load_delivery_state(factory):
    return CourseTeachingPresentationRepositoryV01(
        factory
    ).load_state(
        trace_id=TRACE_ID,
        student_id=STUDENT_ID,
        course_id=COURSE_ID,
        objective_id=OBJECTIVE_ID,
    )


def run_teach(factory):
    service = DurableCourseTeachingTurnV01(
        session_factory=factory,
        decision_engine=PersonalizedDecisionEngineV01(),
        professor_agent=FakeCourseProfessor(),
    )

    trace = service.run_or_resume(
        make_state(),
        pack=make_pack(),
        trace_id=TRACE_ID,
        student_id=STUDENT_ID,
        course_id=COURSE_ID,
        objective_id=OBJECTIVE_ID,
        expected_pack_revision=PACK_REVISION,
        decision_id=DECISION_ID,
        requested_at=REQUESTED_AT,
        generated_at=datetime.now(timezone.utc),
        student_request=make_request(),
    )

    delivery = load_delivery_state(factory)

    emit(
        status=delivery.status,
        trace_id=trace.trace_id,
        decision_id=trace.decision_id,
        pack_id=trace.result.pack_id,
        pack_revision=trace.result.pack_revision,
        source_locators=[
            ref.source_locator
            for ref in trace.result.source_refs
        ],
        content=trace.result.completed_turn.content,
    )


def run_status(factory):
    try:
        delivery = load_delivery_state(factory)

    except LookupError:
        emit(
            status="not_generated",
            trace_id=TRACE_ID,
        )
        return

    emit(
        status=delivery.status,
        trace_id=delivery.trace.trace_id,
        decision_id=delivery.trace.decision_id,
        content=delivery.trace.result.completed_turn.content,
        presentation_event_id=(
            None
            if delivery.presentation is None
            else delivery.presentation.event_id
        ),
    )


def run_present(factory):
    repository = CourseTeachingPresentationRepositoryV01(
        factory
    )

    delivery = load_delivery_state(factory)

    if delivery.status == "presentation_reported":
        emit(
            status="presentation_reported",
            trace_id=TRACE_ID,
            presentation_event_id=delivery.presentation.event_id,
            already_reported=True,
        )
        return

    # Print the STORED content before reporting presentation.
    # If the output operation fails, do not insert an event.
    emit(
        display_content=(
            delivery.trace.result.completed_turn.content
        ),
        trace_id=TRACE_ID,
    )

    report = repository.record_presentation(
        trace_id=TRACE_ID,
        student_id=STUDENT_ID,
        course_id=COURSE_ID,
        objective_id=OBJECTIVE_ID,
        event_id=PRESENTATION_ID,
        reported_at=datetime.now(timezone.utc),
        surface="synthetic_local_cli_demo",
    )

    emit(
        status=report.status,
        trace_id=TRACE_ID,
        presentation_event_id=report.presentation.event_id,
        already_reported=False,
    )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "URPP synthetic course-grounded teaching demo."
        )
    )

    parser.add_argument(
        "action",
        choices=[
            "init",
            "teach",
            "present",
            "status",
        ],
    )

    parser.add_argument(
        "--database",
        required=True,
    )

    args = parser.parse_args()

    path = validate_path(args.database)

    if args.action == "init":
        initialize_database(path)
        return

    engine = open_verified_demo(path)

    try:
        factory = sessionmaker(
            bind=engine,
            expire_on_commit=False,
        )

        if args.action == "teach":
            run_teach(factory)

        elif args.action == "present":
            run_present(factory)

        else:
            run_status(factory)

    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
