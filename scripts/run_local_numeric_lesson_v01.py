#!/usr/bin/env python3
"""
URPP Implementation 13E-3C.

An executable, local-only Numeric Teaching CLI.

This is a deliberately limited demonstration application:
- one synthetic arithmetic Objective;
- one synthetic, pre-aligned Assessment Item;
- one student/session scoped to a NEW demo database;
- static teaching content, not an external LLM;
- actual terminal output through the Presentation Service;
- real SQLite Assignment, Attempt, Assistance Event,
  Student State recovery, and next-turn decision.

This is not a production API or authenticated application.

The CLI refuses to open an existing database. It cannot
be used to modify a real student's stored records.
"""

import argparse
import os
import sys

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


PROJECT_ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(
    0,
    str(PROJECT_ROOT / "backend"),
)


from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.repositories.assessment_records_v02 import (
    AssessmentRecordRepositoryV02,
    Base,
)

from app.repositories.numeric_assignment_v01 import (
    NumericAssignmentRepositoryV01,
)

from app.repositories.numeric_session_records_v01 import (
    NumericSessionRecordRepositoryV01,
)

from app.repositories.assessment_assistance_log_v01 import (
    AssessmentAssistanceKindV01,
    AssessmentAssistanceLogRepositoryV01,
)

from app.services.assessment.models_v02 import (
    AssessmentItemV02,
    NumericRubricV02,
)

from app.services.decision.assessment_assistance_presentation_v01 import (
    AssessmentAssistancePresentationServiceV01,
    AssistancePresentationFailedV01,
    AssistancePresentationUnloggedV01,
)

from app.services.decision.evidence_driven_turn_wiring_v01 import (
    create_evidence_driven_personalized_turn_v01,
)

from app.services.decision.personalized_numeric_session_adapter_v01 import (
    create_personalized_recoverable_numeric_session_v01,
)


STUDENT_ID = "local-demo-student"
COURSE_ID = "local-demo-arithmetic"
OBJECTIVE_ID = "local-demo-addition"

QUESTION = "What is 2 + 3?"

HINT_CONTENT = (
    "Start at 2 and count three more: "
    "one step, two steps, three steps."
)

SOLUTION_CONTENT = (
    "2 + 3 = 5."
)


def now_utc():
    return datetime.now(timezone.utc)


def output(message):
    """
    Write and flush content to the actual CLI output.

    A successful flush establishes that this process
    handed content to its output stream. It does not
    prove that a person read or understood the content.
    """

    sys.stdout.write(message + "\n")
    sys.stdout.flush()


class TerminalAssistancePresenterV01:
    """
    Application-owned terminal presentation implementation.

    Unlike a test double, this presenter performs the
    actual output operation used by the local CLI.
    """

    def present(
        self,
        *,
        assignment_id,
        student_id,
        session_id,
        kind,
        content,
    ):
        if not isinstance(
            kind,
            AssessmentAssistanceKindV01,
        ):
            return False

        output(
            f"\n[{kind.value.upper()}]"
        )

        output(content)

        return True


class StaticDemoAgentV01:
    """
    Static teaching content for this local demonstration.

    Generated Agent content is not a student response
    and must not be recorded as mastery evidence.
    """

    def __init__(self, content):
        self.content = content

    def produce(
        self,
        *,
        context,
        decision,
    ):
        return self.content


def create_new_demo_database(database_path):
    """
    Create a new, private SQLite file.

    Existing files are rejected without being opened.

    This CLI intentionally uses Base.metadata.create_all()
    only for a brand-new, explicitly named demo database.
    It does not run migrations on an existing database.
    """

    database_path = Path(
        database_path
    ).expanduser().resolve()

    if not database_path.parent.is_dir():
        raise ValueError(
            "The database parent directory does not exist."
        )

    if database_path.exists():
        raise FileExistsError(
            "Refusing to open an existing database. "
            "Provide a new filename dedicated to this demo."
        )

    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY

    descriptor = os.open(
        database_path,
        flags,
        0o600,
    )

    os.close(descriptor)

    engine = create_engine(
        f"sqlite+pysqlite:///{database_path}"
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        cursor = connection.cursor()

        cursor.execute(
            "PRAGMA foreign_keys=ON"
        )

        cursor.close()

    try:
        Base.metadata.create_all(engine)

    except Exception:
        engine.dispose()
        raise

    return database_path, engine


def build_demo(
    engine,
    *,
    session_id,
):
    """
    Compose the existing URPP services.

    No fake Student State is supplied. The teaching
    session will reconstruct it from the database.
    """

    session_factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    assessments = AssessmentRecordRepositoryV02(
        session_factory
    )

    assignments = NumericAssignmentRepositoryV01(
        assessments,
        clock=now_utc,
    )

    sessions = NumericSessionRecordRepositoryV01(
        assessments
    )

    assistance_log = AssessmentAssistanceLogRepositoryV01(
        session_factory,
        clock=now_utc,
    )

    presenter = TerminalAssistancePresenterV01()

    presentation_service = (
        AssessmentAssistancePresentationServiceV01(
            session_factory=session_factory,
            assistance_log=assistance_log,
            presenter=presenter,
        )
    )

    orchestrator = (
        create_evidence_driven_personalized_turn_v01(
            professor_agent=StaticDemoAgentV01(
                "Review: addition combines quantities. "
                "For 2 + 3, begin at 2 and count three more."
            ),
            assessment_agent=StaticDemoAgentV01(
                "Demo assessment-agent output. "
                "The stored Assessment Item supplies "
                "the actual question."
            ),
        )
    )

    numeric_session = (
        create_personalized_recoverable_numeric_session_v01(
            assessment_repository=assessments,
            assignment_repository=assignments,
            session_repository=sessions,
            personalized_turn_orchestrator=orchestrator,
            student_id=STUDENT_ID,
            course_id=COURSE_ID,
            objective_id=OBJECTIVE_ID,
            session_id=session_id,
        )
    )

    return (
        assessments,
        assistance_log,
        presentation_service,
        orchestrator,
        numeric_session,
    )


def run_lesson(database_path):
    """
    Execute one real local terminal teaching session.

    Help is reported only through the Presenter and
    Assistance Log; no independent-performance claim
    is derived from an empty or nonempty event log.
    """

    database_path, engine = create_new_demo_database(
        database_path
    )

    try:
        session_id = (
            "local-demo-session-"
            + uuid4().hex
        )

        item_id = (
            "local-demo-item-"
            + uuid4().hex
        )

        (
            assessments,
            assistance_log,
            presentation_service,
            orchestrator,
            numeric_session,
        ) = build_demo(
            engine,
            session_id=session_id,
        )

        # This synthetic arithmetic item is authored and
        # aligned solely for the isolated local demo.
        # Its verified alignment must not be copied to
        # an unreviewed real assessment.
        item = AssessmentItemV02(
            assessment_item_id=item_id,
            course_id=COURSE_ID,
            objective_id=OBJECTIVE_ID,
            prompt=QUESTION,
            rubric=NumericRubricV02(
                expected_value=5.0,
                absolute_tolerance=0.0,
                rubric_version="local-demo-numeric-v1",
            ),
            alignment_verified=True,
        )

        assessments.save_item(
            item,
            revision=1,
        )

        initial = numeric_session.start(
            started_at=now_utc(),
        )

        delivery = numeric_session.deliver_numeric_assessment(
            assessment_item_id=item_id,
            item_revision=1,
            decision_id="local-demo-first-" + uuid4().hex,
            requested_at=now_utc(),
        )

        output("\n=== URPP LOCAL TEACHING DEMO ===")
        output(
            "This is a synthetic, local-only lesson."
        )
        output(
            f"Database: {database_path}"
        )
        output(
            f"Initial Student State: "
            f"{initial.state.state.value}"
        )
        output(
            f"Assessment Action: "
            f"{delivery.selected_action.value}"
        )
        output(
            f"Question: {delivery.prompt}"
        )

        output(
            "\nType hint, solution, a numeric answer, "
            "or quit."
        )

        while True:
            try:
                user_input = input(
                    "\nYour input > "
                ).strip()

            except EOFError:
                output(
                    "\nInput closed. Assignment remains "
                    "pending in the demo database."
                )
                return

            if user_input.lower() == "quit":
                output(
                    "Lesson ended. Assignment remains "
                    "pending in the demo database."
                )
                return

            if user_input.lower() in {
                "hint",
                "solution",
            }:
                is_hint = (
                    user_input.lower() == "hint"
                )

                kind = (
                    AssessmentAssistanceKindV01.HINT
                    if is_hint
                    else AssessmentAssistanceKindV01.SOLUTION
                )

                content = (
                    HINT_CONTENT
                    if is_hint
                    else SOLUTION_CONTENT
                )

                try:
                    record = (
                        presentation_service.present_assistance(
                            assignment_id=delivery.assignment_id,
                            student_id=STUDENT_ID,
                            session_id=session_id,
                            kind=kind,
                            content=content,
                        )
                    )

                except AssistancePresentationFailedV01:
                    output(
                        "Assistance presentation failed. "
                        "No assistance event was written."
                    )
                    continue

                except AssistancePresentationUnloggedV01:
                    output(
                        "STOP: Assistance may have been "
                        "provided, but logging failed. "
                        "This attempt's assistance "
                        "provenance is unresolved."
                    )
                    return

                output(
                    "Assistance event recorded: "
                    f"{record.kind.value}, "
                    f"source={record.source}"
                )

                continue

            if not user_input:
                output(
                    "Enter a numeric answer, hint, "
                    "solution, or quit."
                )
                continue

            try:
                completed = numeric_session.submit_numeric_answer(
                    assignment_id=delivery.assignment_id,
                    response_text=user_input,
                    as_of=now_utc(),
                )

            except ValueError as exc:
                # The Attempt may already be committed when
                # the requested state-estimation time precedes
                # the Repository's actual submission timestamp.
                #
                # Recover the committed result. Never submit
                # the same answer a second time.
                if (
                    "State-estimation time precedes submission."
                    in str(exc)
                ):
                    from datetime import timedelta

                    # The response has already been committed.
                    # A fresh timestamp is now later than the
                    # submission; no future-dated snapshot is
                    # needed and the answer is not resubmitted.
                    completed = numeric_session.resume(
                        as_of=now_utc(),
                    )
                else:
                    output(
                        f"Answer was not accepted: {exc}"
                    )
                    continue

            output(
                "\n=== RECOVERED STUDENT STATE ==="
            )

            output(
                f"State: {completed.state.state.value}"
            )

            output(
                "Included Evidence: "
                f"{len(completed.state.included_evidence_ids)}"
            )

            output(
                "Independent Successes: "
                f"{completed.state.independent_success_count}"
            )

            output(
                "Excluded Evidence Reasons: "
                f"{completed.state.exclusion_reasons}"
            )

            recorded_help = (
                assistance_log.list_assistance_for_assignment(
                    assignment_id=delivery.assignment_id,
                    student_id=STUDENT_ID,
                    session_id=session_id,
                )
            )

            output(
                "Application-reported Assistance Events: "
                f"{len(recorded_help)}"
            )

            # The next decision must not precede the exact
            # Student State snapshot it uses. The recovered
            # snapshot supplies the decision's earliest
            # permissible timestamp.
            next_turn = orchestrator.run_turn(
                completed.state,
                decision_id="local-demo-next-" + uuid4().hex,
                requested_at=completed.state.as_of,
            )

            output(
                "\n=== NEXT AUTOMATIC TEACHING TURN ==="
            )

            output(
                "Next Action: "
                f"{next_turn.decision.decision.selected_action.value}"
            )

            output(
                f"Agent Kind: {next_turn.agent_kind}"
            )

            output(
                f"Teaching Content: {next_turn.content}"
            )

            output(
                "\nDemo complete. A correct answer and "
                "an application-reported Hint do not "
                "prove independent performance."
            )

            return

    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Run one isolated URPP local teaching "
            "demonstration using a NEW SQLite database."
        )
    )

    parser.add_argument(
        "--database",
        required=True,
        help=(
            "Path to a new, nonexistent SQLite file. "
            "Existing databases are never opened."
        ),
    )

    args = parser.parse_args()

    try:
        run_lesson(
            args.database
        )

    except (
        FileExistsError,
        ValueError,
    ) as exc:
        print(
            f"URPP local demo refused to start: {exc}",
            file=sys.stderr,
        )
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
