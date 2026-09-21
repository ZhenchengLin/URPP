"""
URPP Implementation 13E-4C-2.

Read-only Teaching Observation Context.

This component summarizes Learning Observations without
estimating mastery or selecting a teaching action.
"""

from dataclasses import dataclass

from app.services.assessment.learning_observation_shadow_v01 import (
    LearningObservationShadowV01,
)


CONTEXT_VERSION = "teaching-observation-context-v0.1"


@dataclass(frozen=True)
class TeachingObservationContextV01:
    """
    An immutable collection of observations for one
    Student, Course and Objective.

    Input order is preserved. It is not assumed to be
    chronological.
    """

    student_id: str
    course_id: str
    objective_id: str

    observations: tuple[LearningObservationShadowV01, ...]

    version: str = CONTEXT_VERSION

    def __post_init__(self) -> None:

        # Validate the declared scope.

        if not all(
            isinstance(value, str) and value.strip()
            for value in (
                self.student_id,
                self.course_id,
                self.objective_id,
            )
        ):
            raise ValueError(
                "Student, Course and Objective IDs are required."
            )

        if not isinstance(self.observations, tuple):
            raise TypeError(
                "observations must be a tuple."
            )

        seen_attempts = set()
        seen_assignments = set()

        for observation in self.observations:

            if not isinstance(
                observation,
                LearningObservationShadowV01,
            ):
                raise TypeError(
                    "Every entry must be a Learning Observation."
                )

            # Different Sessions are allowed, provided
            # the Student, Course and Objective match.

            if (
                observation.student_id != self.student_id
                or observation.course_id != self.course_id
                or observation.objective_id != self.objective_id
            ):
                raise ValueError(
                    "Learning Observation scope mismatch."
                )

            if observation.attempt_id in seen_attempts:
                raise ValueError(
                    "Duplicate Attempt in Observation Context."
                )

            if observation.assignment_id in seen_assignments:
                raise ValueError(
                    "Duplicate Assignment in Observation Context."
                )

            seen_attempts.add(observation.attempt_id)
            seen_assignments.add(observation.assignment_id)

            # A derived observation is not approved evidence.
            # Reject a modified object that claims otherwise.

            if (
                observation.correctness_status != "not_evaluated"
                or observation.external_help_status != "unknown"
                or observation.verified_independence is not False
                or observation.mastery_eligible is not False
            ):
                raise ValueError(
                    "Observation cannot establish Mastery "
                    "or verified independence."
                )

            hint_count = observation.reported_hint_count
            solution_count = observation.reported_solution_count

            if (
                not isinstance(hint_count, int)
                or isinstance(hint_count, bool)
                or hint_count < 0
                or not isinstance(solution_count, int)
                or isinstance(solution_count, bool)
                or solution_count < 0
            ):
                raise ValueError(
                    "Invalid reported assistance counts."
                )

            if (
                len(observation.source_assistance_event_ids)
                != hint_count + solution_count
            ):
                raise ValueError(
                    "Assistance event count mismatch."
                )

            expected_context = (
                "app_solution_reported"
                if solution_count
                else (
                    "app_hint_reported"
                    if hint_count
                    else "no_app_report"
                )
            )

            if observation.app_assistance_context != expected_context:
                raise ValueError(
                    "Assistance context does not match event counts."
                )

    @property
    def observed_attempt_count(self) -> int:
        """Number of distinct observed Attempts."""

        return len(self.observations)

    @property
    def source_attempt_ids(self) -> tuple[str, ...]:
        """Preserve caller-supplied order without claiming recency."""

        return tuple(
            observation.attempt_id
            for observation in self.observations
        )

    @property
    def app_hint_attempt_count(self) -> int:
        """Attempts with at least one reported Hint."""

        return sum(
            observation.reported_hint_count > 0
            for observation in self.observations
        )

    @property
    def app_solution_attempt_count(self) -> int:
        """Attempts with at least one reported Solution."""

        return sum(
            observation.reported_solution_count > 0
            for observation in self.observations
        )

    @property
    def no_app_report_attempt_count(self) -> int:
        """
        Attempts without recorded application help.

        This does not imply independence.
        """

        return sum(
            observation.app_assistance_context == "no_app_report"
            for observation in self.observations
        )
