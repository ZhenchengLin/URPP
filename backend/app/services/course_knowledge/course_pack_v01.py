"""
URPP Implementation 14A-2.

Local Course Pack loading and deterministic Source Lookup.

This module does not authenticate the person who supplied
a pack, verify copyright permissions, or establish that
an approval statement came from an authorized reviewer.

Only CourseKnowledgeContextV01 is returned for teaching.
No Student State or Assessment Evidence is modified.
"""

from pathlib import Path

from pydantic import (
    Field,
    field_validator,
    model_validator,
)

from app.services.course_knowledge.models_v01 import (
    CourseContractBaseV01,
    CourseKnowledgeContextV01,
    CourseLearningObjectiveV01,
    CourseSourceV01,
)


class CoursePackV01(CourseContractBaseV01):
    """
    One versioned collection of local course materials.

    A pack may contain material unavailable for teaching.
    The lookup operation must never return such material
    in CourseKnowledgeContextV01.
    """

    course_id: str = Field(min_length=1)
    pack_id: str = Field(min_length=1)
    pack_revision: str = Field(min_length=1)

    objectives: tuple[
        CourseLearningObjectiveV01,
        ...
    ] = Field(min_length=1)

    sources: tuple[
        CourseSourceV01,
        ...
    ] = Field(min_length=1)

    @field_validator(
        "course_id",
        "pack_id",
        "pack_revision",
    )
    @classmethod
    def reject_blank_identifiers(
        cls,
        value: str,
    ) -> str:
        if not value.strip():
            raise ValueError(
                "Course Pack identifiers cannot be blank."
            )

        return value

    @model_validator(mode="after")
    def validate_pack_scope_and_uniqueness(self):
        objective_ids = set()

        for objective in self.objectives:
            if objective.course_id != self.course_id:
                raise ValueError(
                    "Objective belongs to a different course."
                )

            if objective.objective_id in objective_ids:
                raise ValueError(
                    "Duplicate objective ID in Course Pack."
                )

            objective_ids.add(objective.objective_id)

        source_ids = set()

        for source in self.sources:
            if source.course_id != self.course_id:
                raise ValueError(
                    "Source belongs to a different course."
                )

            if source.source_id in source_ids:
                raise ValueError(
                    "Duplicate source ID in Course Pack."
                )

            source_ids.add(source.source_id)

        return self


def load_course_pack_v01(
    path: Path,
) -> CoursePackV01:
    """
    Load a local JSON Course Pack from an explicit path.

    The caller is responsible for selecting a permissible
    local file. Loading does not grant teaching permission.
    """

    content = Path(path).read_text(encoding="utf-8")

    return CoursePackV01.model_validate_json(content)


def resolve_course_knowledge_v01(
    *,
    pack: CoursePackV01,
    course_id: str,
    objective_id: str,
    expected_pack_revision: str,
) -> CourseKnowledgeContextV01:
    """
    Resolve exactly one Objective's explicitly referenced
    sources from a specific Course Pack revision.

    Never fall back to an unrelated Objective, an older
    revision, or a partially available set of sources.

    This is a teaching-context lookup, not a student
    authentication or Mastery Evidence operation.
    """

    if not course_id.strip():
        raise ValueError("Requested course ID is blank.")

    if not objective_id.strip():
        raise ValueError("Requested objective ID is blank.")

    if not expected_pack_revision.strip():
        raise ValueError(
            "Expected Course Pack revision is blank."
        )

    if pack.course_id != course_id:
        raise ValueError(
            "Requested course does not match Course Pack."
        )

    if pack.pack_revision != expected_pack_revision:
        raise ValueError(
            "Course Pack revision mismatch."
        )

    objectives = {
        item.objective_id: item
        for item in pack.objectives
    }

    objective = objectives.get(objective_id)

    if objective is None:
        raise ValueError(
            "Requested Learning Objective was not found."
        )

    sources = {
        item.source_id: item
        for item in pack.sources
    }

    selected_sources = []

    for reference in objective.source_refs:
        source = sources.get(reference.source_id)

        if source is None:
            raise ValueError(
                "Required Course Source was not found."
            )

        selected_sources.append(source)

    # The existing 14A-1 Contract verifies objective
    # approval, source permissions, course scope,
    # content digests, locators and exact revisions.
    return CourseKnowledgeContextV01(
        course_id=course_id,
        objective_id=objective_id,
        objective=objective,
        sources=tuple(selected_sources),
    )
