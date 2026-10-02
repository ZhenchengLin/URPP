"""
URPP Implementation 14A-1.

A minimal, immutable Course Knowledge Contract.

This module does not:
- authenticate students or reviewers;
- ingest arbitrary course files;
- authorize access to external course platforms;
- generate teaching content;
- modify Student State or mastery evidence.

Review and permission fields are metadata supplied by a
controlled application boundary, not authentication proofs.
"""

from hashlib import sha256
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


SourceVisibilityV01 = Literal[
    "student_visible",
    "restricted",
]

SourceUsePermissionV01 = Literal[
    "approved_for_local_teaching",
    "not_authorized",
]

SourceReviewStatusV01 = Literal[
    "approved",
    "proposed",
    "revoked",
]

ObjectiveReviewStatusV01 = Literal[
    "approved",
    "proposed",
]


class CourseContractBaseV01(BaseModel):
    """
    Shared validation settings for course knowledge records.

    Frozen models prevent normal field assignment.
    They are not authorization or tamper-proofing mechanisms.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )


class CourseSourceRefV01(CourseContractBaseV01):
    """
    Identifies one exact revision of one course excerpt.

    The digest supports content consistency checking.
    It is not a signature or proof of source authorization.
    """

    source_id: str = Field(min_length=1)
    source_revision: str = Field(min_length=1)
    source_locator: str = Field(min_length=1)

    content_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$",
    )

    @field_validator(
        "source_id",
        "source_revision",
        "source_locator",
    )
    @classmethod
    def reject_blank_reference_fields(
        cls,
        value: str,
    ) -> str:
        if not value.strip():
            raise ValueError(
                "Source reference fields cannot be blank."
            )

        return value


class CourseSourceV01(CourseContractBaseV01):
    """
    One explicitly selected course excerpt.

    source_locator must point to the original material,
    such as a document section or page.

    The supplied approval fields are assertions made by
    the application providing this record. This model
    cannot independently establish who approved the source.
    """

    course_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)

    source_revision: str = Field(min_length=1)
    source_locator: str = Field(min_length=1)

    content: str = Field(min_length=1)

    content_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$",
    )

    visibility: SourceVisibilityV01

    use_permission: SourceUsePermissionV01

    review_status: SourceReviewStatusV01

    @field_validator(
        "course_id",
        "source_id",
        "source_revision",
        "source_locator",
        "content",
    )
    @classmethod
    def reject_blank_source_fields(
        cls,
        value: str,
    ) -> str:
        if not value.strip():
            raise ValueError(
                "Course source fields cannot be blank."
            )

        return value

    @model_validator(mode="after")
    def verify_content_digest(self):
        actual_digest = sha256(
            self.content.encode("utf-8")
        ).hexdigest()

        if self.content_sha256 != actual_digest:
            raise ValueError(
                "Course source content digest mismatch."
            )

        return self

    def reference(self) -> CourseSourceRefV01:
        """Return a reference bound to this exact excerpt."""

        return CourseSourceRefV01(
            source_id=self.source_id,
            source_revision=self.source_revision,
            source_locator=self.source_locator,
            content_sha256=self.content_sha256,
        )


class CourseLearningObjectiveV01(
    CourseContractBaseV01
):
    """
    One explicitly defined course learning objective.

    An approved review_status is metadata supplied by
    the application. This model does not verify reviewer
    identity or establish production authorization.
    """

    course_id: str = Field(min_length=1)
    objective_id: str = Field(min_length=1)

    description: str = Field(min_length=1)

    review_status: ObjectiveReviewStatusV01

    source_refs: tuple[
        CourseSourceRefV01,
        ...
    ] = Field(min_length=1)

    @field_validator(
        "course_id",
        "objective_id",
        "description",
    )
    @classmethod
    def reject_blank_objective_fields(
        cls,
        value: str,
    ) -> str:
        if not value.strip():
            raise ValueError(
                "Course objective fields cannot be blank."
            )

        return value

    @model_validator(mode="after")
    def reject_duplicate_source_references(self):
        source_ids = [
            ref.source_id
            for ref in self.source_refs
        ]

        if len(source_ids) != len(set(source_ids)):
            raise ValueError(
                "Objective contains duplicate source IDs."
            )

        return self


class CourseKnowledgeContextV01(
    CourseContractBaseV01
):
    """
    Course-grounded input for one requested objective.

    This is teaching context only.

    It is not an assessment result, learning observation,
    student-state update, or mastery-eligible evidence.
    """

    course_id: str = Field(min_length=1)
    objective_id: str = Field(min_length=1)

    objective: CourseLearningObjectiveV01

    sources: tuple[
        CourseSourceV01,
        ...
    ] = Field(min_length=1)

    @field_validator(
        "course_id",
        "objective_id",
    )
    @classmethod
    def reject_blank_context_ids(
        cls,
        value: str,
    ) -> str:
        if not value.strip():
            raise ValueError(
                "Knowledge context IDs cannot be blank."
            )

        return value

    @model_validator(mode="after")
    def validate_course_knowledge_scope(self):
        """
        Validate all relationships before allowing the
        context to be used as a teaching input.
        """

        objective = self.objective

        if objective.course_id != self.course_id:
            raise ValueError(
                "Objective belongs to a different course."
            )

        if objective.objective_id != self.objective_id:
            raise ValueError(
                "Objective does not match requested objective."
            )

        if objective.review_status != "approved":
            raise ValueError(
                "Course objective is not approved."
            )

        expected = {
            ref.source_id: ref
            for ref in objective.source_refs
        }

        if len(expected) != len(
            objective.source_refs
        ):
            raise ValueError(
                "Duplicate objective source references."
            )

        actual = {}

        for source in self.sources:
            if source.source_id in actual:
                raise ValueError(
                    "Duplicate course source ID."
                )

            actual[source.source_id] = source

            if source.course_id != self.course_id:
                raise ValueError(
                    "Source belongs to a different course."
                )

            if source.visibility != "student_visible":
                raise ValueError(
                    "Source is not student-visible."
                )

            if (
                source.use_permission
                != "approved_for_local_teaching"
            ):
                raise ValueError(
                    "Source is not approved for local teaching."
                )

            if source.review_status != "approved":
                raise ValueError(
                    "Source is not approved."
                )

            # Check again at the context boundary. A model
            # copied through model_copy(update=...) may have
            # bypassed ordinary Pydantic field validation.
            actual_digest = sha256(
                source.content.encode("utf-8")
            ).hexdigest()

            if actual_digest != source.content_sha256:
                raise ValueError(
                    "Source content digest mismatch."
                )

            ref = expected.get(source.source_id)

            if ref is None:
                raise ValueError(
                    "Unreferenced source supplied to context."
                )

            if source.reference() != ref:
                raise ValueError(
                    "Source reference or revision mismatch."
                )

        if set(actual) != set(expected):
            raise ValueError(
                "Required course source is missing."
            )

        return self
