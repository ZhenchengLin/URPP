"""
URPP Implementation 13E-3B.

Assessment Assistance Presentation Service V0.1.

Coordinate an application's reported content-presentation
operation with the existing assignment-scoped Assistance
Event Log.

The presenter is an application-supplied integration port,
not a verified browser or student-attention signal.

This service does not authenticate callers, prove that the
student saw the content, or infer independent performance.
"""

from typing import Protocol

from sqlalchemy.orm import Session

from app.repositories.assessment_assistance_log_v01 import (
    AssessmentAssistanceKindV01,
    AssessmentAssistanceLogRepositoryV01,
    RecordedAssessmentAssistanceV01,
)

from app.repositories.numeric_assignment_v01 import (
    NumericAssignmentRow,
)


class AssessmentAssistancePresenterV01(Protocol):
    """
    Application-controlled synchronous presentation port.

    Return exactly True only when the application reports
    that it successfully provided the requested content.

    Returning False, returning another value, or raising
    an exception does not authorize an assistance log write.

    A successful return is still only an application report.
    It is not proof of student attention or comprehension.
    """

    def present(
        self,
        *,
        assignment_id: str,
        student_id: str,
        session_id: str,
        kind: AssessmentAssistanceKindV01,
        content: str,
    ) -> bool:
        ...


class AssistancePresentationFailedV01(RuntimeError):
    """
    The presenter did not report successful provision.

    No assistance event is written by this service.
    """


class AssistancePresentationUnloggedV01(RuntimeError):
    """
    Presentation was reported successful, but the event
    could not be persisted afterward.

    The application must treat this as a partial operation:
    assistance may have been provided without a durable log.

    Do not automatically replay the presentation.
    """


class AssessmentAssistancePresentationServiceV01:
    """
    Coordinate pending-assignment validation, the
    application presentation port, and assistance logging.

    Not a public API or an authentication boundary.
    """

    def __init__(
        self,
        *,
        session_factory,
        assistance_log: AssessmentAssistanceLogRepositoryV01,
        presenter: AssessmentAssistancePresenterV01,
    ) -> None:
        self._session_factory = session_factory
        self._assistance_log = assistance_log
        self._presenter = presenter

    @staticmethod
    def _require_identifier(
        value: str,
        *,
        name: str,
    ) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"{name} must be a nonempty string."
            )

        return value

    def _require_pending_assignment(
        self,
        *,
        assignment_id: str,
        student_id: str,
        session_id: str,
    ) -> None:
        """
        Reject invalid scope or a completed Assignment
        before invoking the external presentation operation.

        The Assistance Log Repository independently checks
        pending status again before committing an event.
        """

        with self._session_factory() as session:
            assert isinstance(session, Session)

            assignment = session.get(
                NumericAssignmentRow,
                assignment_id,
            )

            if assignment is None:
                raise LookupError(
                    "Numeric Assignment was not found."
                )

            if (
                assignment.student_id != student_id
                or assignment.session_id != session_id
            ):
                raise ValueError(
                    "Assistance presentation does not match "
                    "the Assignment student and session."
                )

            if (
                assignment.status != "pending"
                or assignment.completed_attempt_id is not None
            ):
                raise ValueError(
                    "Assistance cannot be presented "
                    "after Assignment completion."
                )

    def present_assistance(
        self,
        *,
        assignment_id: str,
        student_id: str,
        session_id: str,
        kind: AssessmentAssistanceKindV01,
        content: str,
    ) -> RecordedAssessmentAssistanceV01:
        """
        Invoke the application presenter once, then record
        its successful application-reported assistance.

        No eligible student-performance evidence is created.

        Because presentation and database persistence are
        separate operations, a successful presentation can
        still be followed by a logging failure. Such a
        failure is surfaced explicitly, not silently ignored.
        """

        assignment_id = self._require_identifier(
            assignment_id,
            name="assignment_id",
        )

        student_id = self._require_identifier(
            student_id,
            name="student_id",
        )

        session_id = self._require_identifier(
            session_id,
            name="session_id",
        )

        if not isinstance(
            kind,
            AssessmentAssistanceKindV01,
        ):
            raise TypeError(
                "kind must be AssessmentAssistanceKindV01."
            )

        if not isinstance(content, str) or not content.strip():
            raise ValueError(
                "Assistance content must be a nonempty string."
            )

        self._require_pending_assignment(
            assignment_id=assignment_id,
            student_id=student_id,
            session_id=session_id,
        )

        try:
            reported_success = self._presenter.present(
                assignment_id=assignment_id,
                student_id=student_id,
                session_id=session_id,
                kind=kind,
                content=content,
            )

        except Exception as exc:
            raise AssistancePresentationFailedV01(
                "The application presenter raised an "
                "exception. No assistance event was written."
            ) from exc

        if reported_success is not True:
            raise AssistancePresentationFailedV01(
                "The application presenter did not report "
                "successful provision. No assistance event "
                "was written."
            )

        try:
            return self._assistance_log.record_application_assistance(
                assignment_id=assignment_id,
                student_id=student_id,
                session_id=session_id,
                kind=kind,
                content=content,
            )

        except Exception as exc:
            raise AssistancePresentationUnloggedV01(
                "The application reported successful "
                "assistance presentation, but the event "
                "could not be recorded. Assistance may "
                "have been provided without a durable log. "
                "Do not automatically replay the "
                "presentation."
            ) from exc
