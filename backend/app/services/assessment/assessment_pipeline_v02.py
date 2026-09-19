"""
URPP Design 01C — Internal Assessment Processing Pipeline V0.2.

Application-layer entry point for processing assessment records.

This is NOT an HTTP endpoint or an authentication system.

Production callers must load authoritative assessment records
and reviewer verification keys from trusted server-side sources.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from app.domain.learning.state_v02 import ObjectiveStateV02

from app.services.assessment.models_v02 import (
    AssessmentItemV02,
    StudentAttemptV02,
)

from app.services.assessment.numeric_scoring_v02 import (
    score_numeric_attempt,
)

from app.services.assessment.open_response_models_v02 import (
    OpenResponseAssessmentItemV02,
    OpenResponseReviewV02,
)

from app.services.assessment.review_approval_v02 import (
    ReviewApprovalV02,
    finalize_approved_review,
)

from app.services.student_model.state_update_v02 import (
    estimate_objective_state,
)


@dataclass(frozen=True)
class NumericSubmissionV02:
    """A numeric item paired with its student attempt."""

    item: AssessmentItemV02
    attempt: StudentAttemptV02


@dataclass(frozen=True)
class ApprovedOpenResponseSubmissionV02:
    """An open-response assessment with its signed review."""

    item: OpenResponseAssessmentItemV02
    attempt: StudentAttemptV02
    review: OpenResponseReviewV02
    approval: ReviewApprovalV02


AssessmentSubmissionV02 = (
    NumericSubmissionV02
    | ApprovedOpenResponseSubmissionV02
)


class AssessmentPipelineV02:
    """
    Process assessment artifacts before estimating student state.

    This class deliberately does not accept preconstructed
    EvidenceEventV02 objects as input.

    This restriction protects this entry point only. The underlying
    State Update Engine remains independently callable.
    """

    def __init__(
        self,
        *,
        verification_key: bytes | None = None,
    ) -> None:
        if verification_key is not None:
            if (
                not isinstance(verification_key, bytes)
                or len(verification_key) < 32
            ):
                raise ValueError(
                    "Verification key must be at least 32 bytes."
                )

        self._verification_key = verification_key

    def estimate_from_assessments(
        self,
        submissions: Sequence[AssessmentSubmissionV02],
        *,
        student_id: str,
        course_id: str,
        objective_id: str,
        as_of: datetime,
    ) -> ObjectiveStateV02:
        """
        Score supplied assessments, then calculate objective state.

        The caller must supply authoritative item and attempt data.
        This method does not authenticate or authorize the caller.
        """

        if not submissions:
            raise ValueError(
                "At least one assessment submission is required."
            )

        evidence_events = []

        for submission in submissions:
            if isinstance(
                submission,
                NumericSubmissionV02,
            ):
                evidence = score_numeric_attempt(
                    submission.item,
                    submission.attempt,
                )

            elif isinstance(
                submission,
                ApprovedOpenResponseSubmissionV02,
            ):
                if self._verification_key is None:
                    raise ValueError(
                        "Open-response evidence requires "
                        "a server-side verification key."
                    )

                evidence = finalize_approved_review(
                    submission.item,
                    submission.attempt,
                    submission.review,
                    submission.approval,
                    verification_key=self._verification_key,
                )

            else:
                raise TypeError(
                    "Only supported assessment submissions "
                    "can enter this processing pipeline."
                )

            evidence_events.append(evidence)

        return estimate_objective_state(
            evidence_events,
            student_id=student_id,
            course_id=course_id,
            objective_id=objective_id,
            as_of=as_of,
        )
