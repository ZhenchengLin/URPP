"""
URPP Design 01C — Persisted Numeric Assessment Pipeline V0.2.

Loads student attempts and their original assessment-item revisions
from the repository, then delegates scoring and state estimation
to the existing AssessmentPipelineV02.

This is an INTERNAL application service.

It does not authenticate a student, authorize access to records,
or establish that repository contents came from trusted sources.
"""

from datetime import datetime
from typing import Sequence

from app.domain.learning.state_v02 import ObjectiveStateV02

from app.repositories.assessment_records_v02 import (
    AssessmentRecordRepositoryV02,
)

from app.services.assessment.assessment_pipeline_v02 import (
    AssessmentPipelineV02,
    NumericSubmissionV02,
)

from app.services.assessment.models_v02 import AssessmentItemV02


class PersistedNumericAssessmentServiceV02:
    """
    Estimate student state using previously stored numeric attempts.

    The repository determines the assessment revision associated
    with each attempt. The caller cannot replace its historical
    rubric with the latest item revision.
    """

    def __init__(
        self,
        repository: AssessmentRecordRepositoryV02,
    ) -> None:
        self._repository = repository
        self._pipeline = AssessmentPipelineV02()

    def estimate_from_attempt_ids(
        self,
        attempt_ids: Sequence[str],
        *,
        student_id: str,
        course_id: str,
        objective_id: str,
        as_of: datetime,
    ) -> ObjectiveStateV02:
        """
        Load stored attempts and estimate state for one objective.

        In a future API, student_id and record access must come
        from an authenticated and authorized server-side context.
        """

        if isinstance(attempt_ids, (str, bytes)):
            raise TypeError(
                "attempt_ids must be a sequence of attempt IDs."
            )

        if not attempt_ids:
            raise ValueError(
                "At least one stored attempt is required."
            )

        submissions = []
        seen_attempt_ids = set()

        for attempt_id in attempt_ids:
            if (
                not isinstance(attempt_id, str)
                or not attempt_id.strip()
            ):
                raise ValueError(
                    "Every attempt ID must be a non-empty string."
                )

            if attempt_id in seen_attempt_ids:
                raise ValueError(
                    "Duplicate attempt IDs are not allowed."
                )

            seen_attempt_ids.add(attempt_id)

            attempt, item_revision = self._repository.load_attempt(
                attempt_id
            )

            if (
                attempt.student_id != student_id
                or attempt.course_id != course_id
                or attempt.objective_id != objective_id
            ):
                raise ValueError(
                    "Stored attempt does not match the requested "
                    "student, course, and objective."
                )

            item = self._repository.load_item(
                attempt.assessment_item_id,
                revision=item_revision,
            )

            if not isinstance(item, AssessmentItemV02):
                raise TypeError(
                    "This service supports stored numeric "
                    "assessment items only."
                )

            submissions.append(
                NumericSubmissionV02(
                    item=item,
                    attempt=attempt,
                )
            )

        return self._pipeline.estimate_from_assessments(
            submissions,
            student_id=student_id,
            course_id=course_id,
            objective_id=objective_id,
            as_of=as_of,
        )
