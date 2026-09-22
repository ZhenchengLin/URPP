"""URPP 14A-3: opt-in local, one-objective, source-bound course pilot.

The --pack file is supplied locally; source material is never downloaded,
published, or silently substituted.  This pilot echoes validated course
excerpts via a deterministic adapter.  It is NOT a real LLM Professor,
student authentication, teaching-quality proof, or assessment/mastery engine.

Run from backend/:
    python3 scripts/real_course_pilot_v01.py init --database PATH --pack PACK.json
    python3 scripts/real_course_pilot_v01.py teach --database PATH --pack PACK.json
    python3 scripts/real_course_pilot_v01.py present --database PATH --pack PACK.json
    python3 scripts/real_course_pilot_v01.py status --database PATH --pack PACK.json

Only init creates a fresh standalone database; other actions open existing
files in rw mode and verify the pilot identity + exact Course Pack content.
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.domain.learning.models import ObjectiveStateLabel
from app.repositories.course_teaching_presentation_v01 import (
    CourseTeachingPresentationRepositoryV01,
    course_teaching_presentations_v01,
)
from app.repositories.course_teaching_trace_v01 import course_teaching_traces_v01
from app.services.course_knowledge.course_pack_v01 import (
    load_course_pack_v01,
    resolve_course_knowledge_v01,
)
from app.services.course_knowledge.durable_teaching_turn_v01 import (
    DurableCourseTeachingTurnV01,
    course_teaching_turn_intents_v01,
)
from app.services.decision.personalized_engine_v01 import PersonalizedDecisionEngineV01
from app.services.decision.student_request_v01 import (
    StudentLearningRequestKindV01,
    StudentLearningRequestV01,
)
from app.services.student_model.state_update_v02 import estimate_objective_state


DATABASE_FILENAME = "urpp-real-course-pilot.sqlite"
IDENTITY = "urpp-real-course-pilot-v0.1"
STUDENT_ID = "local-pilot-student-001"  # Test label, NOT an authenticated person.
TRACE_ID = "local-pilot-trace-001"
DECISION_ID = "local-pilot-decision-001"
PRESENTATION_ID = "local-pilot-presentation-001"
IDENTITY_TABLE = "urpp_real_course_pilot_identity_v01"


def emit(**values):
    print(json.dumps(values, ensure_ascii=False, sort_keys=True), flush=True)


def validated_database_path(value):
    path = Path(value).expanduser().absolute()
    if path.name != DATABASE_FILENAME:
        raise ValueError(f"Pilot database filename must be {DATABASE_FILENAME}.")
    if path.is_symlink():
        raise ValueError("Refusing a symlink pilot database.")
    if not path.parent.is_dir():
        raise ValueError("Pilot database parent directory does not exist.")
    return path


def load_pilot_pack(value):
    pack = load_course_pack_v01(Path(value).expanduser())
    if len(pack.objectives) != 1:
        raise ValueError("Pilot v0.1 requires exactly one Learning Objective.")
    objective = pack.objectives[0]
    # The resolver checks approval assertions, visibility, reference and
    # exact source digests. The pack file does NOT prove who approved it.
    resolve_course_knowledge_v01(
        pack=pack,
        course_id=pack.course_id,
        objective_id=objective.objective_id,
        expected_pack_revision=pack.pack_revision,
    )
    canonical = json.dumps(
        pack.model_dump(mode="json"),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return pack, objective, sha256(canonical).hexdigest()


def attach_foreign_keys(engine):
    @event.listens_for(engine, "connect")
    def _foreign_keys(dbapi_connection, _):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")
        enabled = dbapi_connection.execute("PRAGMA foreign_keys").fetchone()
        if enabled is None or enabled[0] != 1:
            raise RuntimeError("SQLite foreign keys must be enabled.")
    return engine


def initialize(path, pack, objective, pack_digest):
    if path.exists():
        raise ValueError("Pilot database already exists; init never overwrites it.")
    engine = attach_foreign_keys(create_engine(f"sqlite+pysqlite:///{path}"))
    try:
        # Explicit isolated pilot schema; never Numeric Base.metadata.create_all().
        course_teaching_traces_v01.create(engine, checkfirst=False)
        course_teaching_turn_intents_v01.create(engine, checkfirst=False)
        course_teaching_presentations_v01.create(engine, checkfirst=False)
        with engine.begin() as connection:
            connection.exec_driver_sql(
                f"CREATE TABLE {IDENTITY_TABLE} ("
                "marker TEXT NOT NULL, "
                "course_id TEXT NOT NULL, "
                "objective_id TEXT NOT NULL, "
                "pack_id TEXT NOT NULL, "
                "pack_revision TEXT NOT NULL, "
                "pack_digest TEXT NOT NULL, "
                "requested_at_utc TEXT NOT NULL)"
            )
            connection.execute(
                text(
                    f"INSERT INTO {IDENTITY_TABLE} "
                    "(marker, course_id, objective_id, pack_id, pack_revision, "
                    "pack_digest, requested_at_utc) "
                    "VALUES (:marker, :course_id, :objective_id, :pack_id, "
                    ":pack_revision, :pack_digest, :requested_at_utc)"
                ),
                {
                    "marker": IDENTITY,
                    "course_id": pack.course_id,
                    "objective_id": objective.objective_id,
                    "pack_id": pack.pack_id,
                    "pack_revision": pack.pack_revision,
                    "pack_digest": pack_digest,
                    "requested_at_utc": datetime.now(timezone.utc).isoformat(),
                },
            )
    finally:
        engine.dispose()
    emit(status="initialized", course_id=pack.course_id,
         objective_id=objective.objective_id, pack_revision=pack.pack_revision,
         database=str(path), agent_kind="deterministic_source_echo")


def open_verified(path, pack, objective, pack_digest):
    if not path.is_file():
        raise ValueError("Pilot database does not exist. Run init first.")
    uri = path.as_uri() + "?mode=rw"
    engine = attach_foreign_keys(create_engine(
        "sqlite+pysqlite://",
        creator=lambda: sqlite3.connect(uri, uri=True, timeout=5.0),
    ))
    try:
        with engine.connect() as connection:
            record = connection.execute(text(f"SELECT * FROM {IDENTITY_TABLE}"))
            row = record.mappings().one()
            expected = {
                "marker": IDENTITY,
                "course_id": pack.course_id,
                "objective_id": objective.objective_id,
                "pack_id": pack.pack_id,
                "pack_revision": pack.pack_revision,
                "pack_digest": pack_digest,
            }
            if any(row[name] != value for name, value in expected.items()):
                raise ValueError("Pilot database identity or Course Pack mismatch.")
            requested_at = datetime.fromisoformat(row["requested_at_utc"])
            if requested_at.tzinfo is None or requested_at.utcoffset() is None:
                raise ValueError("Pilot database has an invalid request timestamp.")
    except Exception:
        engine.dispose()
        raise
    return engine, requested_at


class SourceBoundProfessor:
    """Present only reviewed source excerpts; no LLM or grading."""

    def produce(self, *, context, decision, course_knowledge):
        excerpts = "\n\n".join(
            f"Source: {source.source_locator}\n"
            f"Excerpt: {source.content}"
            for source in course_knowledge.sources
        )
        return (
            "REAL COURSE PILOT — VERIFIED LOCAL SOURCE EXCERPT; "
            "NOT AI-GENERATED TEACHING\n"
            f"Learning objective: {course_knowledge.objective.description}\n\n"
            f"{excerpts}\n\n"
            "Practice: explain the objective using the cited excerpt. "
            "This prompt is not a graded assessment."
        )


def delivery(factory, pack, objective):
    return CourseTeachingPresentationRepositoryV01(factory).load_state(
        trace_id=TRACE_ID, student_id=STUDENT_ID,
        course_id=pack.course_id, objective_id=objective.objective_id,
    )


def teach(factory, pack, objective, requested_at):
    # Explicit synthetic routing state exercises the Professor path only.
    # The absence of assessment evidence does NOT establish strong mastery.
    state = estimate_objective_state(
        [], student_id=STUDENT_ID, course_id=pack.course_id,
        objective_id=objective.objective_id, as_of=requested_at,
    ).model_copy(update={"state": ObjectiveStateLabel.STRONG})
    request = StudentLearningRequestV01(
        objective_id=objective.objective_id,
        request_kind=StudentLearningRequestKindV01.REQUEST_EXPLANATION,
        requested_at=requested_at,
    )
    service = DurableCourseTeachingTurnV01(
        session_factory=factory,
        decision_engine=PersonalizedDecisionEngineV01(),
        professor_agent=SourceBoundProfessor(),
    )
    trace = service.run_or_resume(
        state, pack=pack, trace_id=TRACE_ID, student_id=STUDENT_ID,
        course_id=pack.course_id, objective_id=objective.objective_id,
        expected_pack_revision=pack.pack_revision,
        decision_id=DECISION_ID, requested_at=requested_at,
        generated_at=datetime.now(timezone.utc), student_request=request,
    )
    saved = delivery(factory, pack, objective)
    emit(status=saved.status, trace_id=trace.trace_id,
         pack_revision=trace.result.pack_revision,
         source_locators=[ref.source_locator for ref in trace.result.source_refs],
         content=trace.result.completed_turn.content,
         agent_kind="deterministic_source_echo")


def status(factory, pack, objective):
    try:
        saved = delivery(factory, pack, objective)
    except LookupError:
        emit(status="not_generated", trace_id=TRACE_ID)
        return
    emit(status=saved.status, trace_id=saved.trace.trace_id,
         content=saved.trace.result.completed_turn.content,
         presentation_event_id=(None if saved.presentation is None
                                else saved.presentation.event_id))


def present(factory, pack, objective):
    repo = CourseTeachingPresentationRepositoryV01(factory)
    saved = delivery(factory, pack, objective)
    if saved.status == "presentation_reported":
        emit(status="presentation_reported", trace_id=TRACE_ID,
             presentation_event_id=saved.presentation.event_id,
             already_reported=True)
        return
    # Report the presentation attempt only after printing the STORED content.
    emit(display_content=saved.trace.result.completed_turn.content,
         trace_id=TRACE_ID)
    reported = repo.record_presentation(
        trace_id=TRACE_ID, student_id=STUDENT_ID,
        course_id=pack.course_id, objective_id=objective.objective_id,
        event_id=PRESENTATION_ID, reported_at=datetime.now(timezone.utc),
        surface="real_course_local_pilot_cli",
    )
    emit(status=reported.status, trace_id=TRACE_ID,
         presentation_event_id=reported.presentation.event_id,
         already_reported=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("init", "teach", "present", "status"))
    parser.add_argument("--database", required=True)
    parser.add_argument("--pack", required=True)
    args = parser.parse_args()
    path = validated_database_path(args.database)
    pack, objective, pack_digest = load_pilot_pack(args.pack)
    if args.action == "init":
        initialize(path, pack, objective, pack_digest)
        return
    engine, requested_at = open_verified(path, pack, objective, pack_digest)
    try:
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        if args.action == "teach":
            teach(factory, pack, objective, requested_at)
        elif args.action == "present":
            present(factory, pack, objective)
        else:
            status(factory, pack, objective)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
